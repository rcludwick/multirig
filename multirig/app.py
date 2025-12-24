from __future__ import annotations

import asyncio
import os
import re
import socket
import subprocess
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

import yaml
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, Response
from fastapi.responses import HTMLResponse, JSONResponse
try:
    import orjson
    from fastapi.responses import ORJSONResponse
except ImportError:
    ORJSONResponse = JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.gzip import GZipMiddleware

from .config import AppConfig, load_config, save_config
from .rig import RigClient
from .service import SyncService
from .rigctl_tcp import RigctlServer, RigctlServerConfig
from .debug_log import DebugStore


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


class ProfileManager:
    """Encapsulates profile storage and management logic."""
    def __init__(self, config_path: Path, test_mode: bool = False):
        self.config_path = config_path
        self.test_mode = test_mode
        self.profiles_dir = config_path.parent / "multirig.config.profiles"
        self.active_profile_path = config_path.parent / "multirig.config.active_profile"
        self._memory_store: Dict[str, Dict[str, Any]] = {}

    def persist_active_name(self, name: str) -> None:
        """Persist the active profile name to disk.

        Args:
            name: The name of the profile to save as active.
        """
        if self.test_mode: return
        try:
            if not name:
                if self.active_profile_path.exists(): self.active_profile_path.unlink()
                return
            self.active_profile_path.write_text(name)
        except Exception: pass

    def get_active_name(self) -> str:
        """Retrieve the currently active profile name.

        Returns:
            The name of the active profile, or an empty string if none is set.
        """
        try:
            if self.active_profile_path.exists():
                return self.active_profile_path.read_text().strip()
        except Exception: pass
        return ""

    def list_names(self) -> List[str]:
        """List all available profile names.

        Returns:
            A sorted list of profile names available in storage.
        """
        if self.test_mode: return sorted(list(self._memory_store.keys()))
        if not self.profiles_dir.exists(): return []
        names = {p.stem for p in self.profiles_dir.glob("*.y*ml") if p.is_file()}
        return sorted(list(names))

    def exists(self, name: str) -> bool:
        """Check if a profile exists.

        Args:
            name: The name of the profile to check.

        Returns:
            True if the profile exists, False otherwise.
        """
        if self.test_mode: return name in self._memory_store
        return (self.profiles_dir / f"{name}.yaml").exists() or (self.profiles_dir / f"{name}.yml").exists()

    def load_data(self, name: str) -> Dict[str, Any]:
        """Load profile data by name.

        Args:
            name: The name of the profile to load.

        Returns:
            A dictionary containing the profile configuration.

        Raises:
            FileNotFoundError: If the profile does not exist.
            ValueError: If the profile data is invalid.
        """
        if self.test_mode:
            if name not in self._memory_store: raise FileNotFoundError(name)
            return self._memory_store[name]
        p1, p2 = self.profiles_dir / f"{name}.yaml", self.profiles_dir / f"{name}.yml"
        path = p1 if p1.exists() else p2
        if not path.exists(): raise FileNotFoundError(name)
        raw = yaml.safe_load(path.read_text()) or {}
        if not isinstance(raw, dict): raise ValueError("invalid profile")
        return raw

    def save_data(self, name: str, data: Dict[str, Any]) -> None:
        """Save configuration data to a profile.

        Args:
            name: The name of the profile.
            data: The configuration dictionary to save.
        """
        if self.test_mode:
            self._memory_store[name] = data
            return
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        (self.profiles_dir / f"{name}.yaml").write_text(yaml.safe_dump(data, sort_keys=False))

    def delete(self, name: str) -> bool:
        """Delete a profile.

        Args:
            name: The name of the profile to delete.

        Returns:
            True if the profile was deleted, False if it was not found.
        """
        if self.test_mode:
            if name in self._memory_store:
                del self._memory_store[name]
                return True
            return False
        removed = False
        for ext in ("yaml", "yml"):
            p = self.profiles_dir / f"{name}.{ext}"
            if p.exists():
                try:
                    p.unlink()
                    removed = True
                except Exception: pass
        return removed

    def rename(self, old_name: str, new_name: str) -> None:
        if self.test_mode:
            if old_name not in self._memory_store: raise FileNotFoundError(old_name)
            if new_name in self._memory_store: raise FileExistsError(new_name)
            self._memory_store[new_name] = self._memory_store.pop(old_name)
            return
        p1, p2 = self.profiles_dir / f"{old_name}.yaml", self.profiles_dir / f"{old_name}.yml"
        src = p1 if p1.exists() else p2
        if not src.exists(): raise FileNotFoundError(old_name)
        dst = self.profiles_dir / f"{new_name}{src.suffix}"
        if dst.exists() or (self.profiles_dir / f"{new_name}.yaml").exists() or (self.profiles_dir / f"{new_name}.yml").exists():
            raise FileExistsError(new_name)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        src.rename(dst)

    def is_valid_name(self, name: str) -> bool:
        if not name or len(name) > 100: return False
        return re.fullmatch(r"[A-Za-z0-9_.-]+", name) is not None


def create_app(config_path: Optional[Path] = None) -> FastAPI:
    """Create and configure the MultiRig FastAPI application."""
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await _bootstrap_active_profile()
        except Exception: pass

        await app.state.sync_service.start()
        try:
            await app.state.rigctl_server.start()
        except Exception: pass
        yield
        await app.state.sync_service.stop()
        try:
            await app.state.rigctl_server.stop()
        except Exception: pass
        for rig in getattr(app.state, "rigs", []):
            try:
                await rig.close()
            except Exception: pass

    app = FastAPI(title="MultiRig", version="0.1.0", default_response_class=ORJSONResponse, lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    if config_path is None:
        env_path = os.getenv("MULTIRIG_CONFIG")
        config_path = Path(env_path) if env_path else Path.cwd() / "multirig.config.yaml"

    app.state.config_path = config_path
    app.state.config = load_config(app.state.config_path)
    app.state.profiles = ProfileManager(config_path, test_mode=app.state.config.test_mode)
    app.state.active_profile_name = app.state.profiles.get_active_name()
    
    app.state.rigs: List[RigClient] = []
    app.state.debug = DebugStore(0)
    
    def _rebuild_rigs(cfg: AppConfig):
        # Close existing
        for rig in getattr(app.state, "rigs", []):
            asyncio.create_task(rig.close()) # Best effort background close
        
        app.state.rigs = [RigClient(rc) for rc in cfg.rigs]
        app.state.debug.ensure_rigs(len(app.state.rigs))
        for idx, rig in enumerate(app.state.rigs):
            log = app.state.debug.rig(idx)
            if log:
                try: setattr(rig._backend, "_debug", log)
                except Exception: pass
        return app.state.rigs

    _rebuild_rigs(app.state.config)

    app.state.sync_service = SyncService(
        app.state.rigs,
        interval_ms=app.state.config.poll_interval_ms,
        enabled=app.state.config.sync_enabled,
        source_index=app.state.config.sync_source_index,
    )

    def _rigctl_bind_host() -> str:
        return os.getenv("MULTIRIG_RIGCTL_HOST", app.state.config.rigctl_listen_host)

    def _rigctl_bind_port() -> int:
        port_s = os.getenv("MULTIRIG_RIGCTL_PORT")
        try: return int(port_s) if port_s else app.state.config.rigctl_listen_port
        except Exception: return app.state.config.rigctl_listen_port

    class AppRigctlServer(RigctlServer):
        """App-specific RigctlServer implementation."""
        def __init__(self, fastapi_app: FastAPI, config: Optional[RigctlServerConfig] = None, debug: Any = None):
            self.app = fastapi_app
            super().__init__(config, debug)

        def get_rigs(self) -> Sequence[RigClient]:
            return self.app.state.rigs

        def get_source_index(self) -> int:
            return self.app.state.sync_service.source_index

        def get_rigctl_to_main_enabled(self) -> bool:
            return self.app.state.config.rigctl_to_main_enabled

        def get_sync_enabled(self) -> bool:
            return self.app.state.config.sync_enabled

    app.state.rigctl_server = AppRigctlServer(
        fastapi_app=app,
        config=RigctlServerConfig(host=_rigctl_bind_host(), port=_rigctl_bind_port()),
        debug=app.state.debug.server,
    )

    async def _restart_rigctl_server(start: bool = True) -> None:
        try: await app.state.rigctl_server.stop()
        except Exception: pass
        app.state.rigctl_server = AppRigctlServer(
            fastapi_app=app,
            config=RigctlServerConfig(host=_rigctl_bind_host(), port=_rigctl_bind_port()),
            debug=app.state.debug.server,
        )
        if start:
            try: await app.state.rigctl_server.start()
            except Exception: pass

    async def _apply_config(cfg: AppConfig, restart_rigctl: bool = True):
        cfg.test_mode = getattr(app.state.config, "test_mode", False)
        app.state.config = cfg
        save_config(cfg, app.state.config_path)

        _rebuild_rigs(cfg)
        
        app.state.sync_service.rigs = app.state.rigs
        app.state.sync_service.interval_ms = cfg.poll_interval_ms
        app.state.sync_service.enabled = cfg.sync_enabled
        app.state.sync_service.source_index = cfg.sync_source_index
        try: app.state.sync_service._last = (None, None, None)
        except Exception: pass
        
        await app.state.sync_service.stop()
        await app.state.sync_service.start()
        await _restart_rigctl_server(start=restart_rigctl)

    def _ensure_default_profile() -> None:
        names = app.state.profiles.list_names()
        if names:
            active = str(getattr(app.state, "active_profile_name", "") or "").strip()
            if not active or active not in names:
                app.state.active_profile_name = names[0]
                app.state.profiles.persist_active_name(app.state.active_profile_name)
            return
        if not app.state.profiles.exists("Default"):
            app.state.profiles.save_data("Default", app.state.config.model_dump())
        app.state.active_profile_name = "Default"
        app.state.profiles.persist_active_name(app.state.active_profile_name)

    async def _bootstrap_active_profile() -> None:
        _ensure_default_profile()
        name = str(getattr(app.state, "active_profile_name", "") or "").strip()
        if not name: return
        try:
            data = app.state.profiles.load_data(name)
            from .config import _migrate_config
            cfg = AppConfig.model_validate(_migrate_config(data))
            await _apply_config(cfg, restart_rigctl=False)
        except Exception: pass

    # Pages
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse("index.html", {
            "request": request, "assets_ts": int(time.time() * 1000), "app_version": getattr(app, "version", ""),
        })

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request):
        return templates.TemplateResponse("settings.html", {
            "request": request, "config": app.state.config, "assets_ts": int(time.time() * 1000), "app_version": getattr(app, "version", ""),
        })

    # API
    @app.get("/api/config")
    async def get_config():
        return app.state.config

    @app.post("/api/config")
    async def update_config(cfg: AppConfig):
        await _apply_config(cfg)
        return {"status": "ok"}

    @app.get("/api/config/export")
    async def export_config():
        content = yaml.safe_dump(app.state.config.model_dump(), sort_keys=False)
        return Response(content=content, media_type="text/yaml")

    @app.post("/api/config/import")
    async def import_config(request: Request):
        try:
            body = await request.body()
            data = yaml.safe_load(body)
            if not isinstance(data, dict):
                return ORJSONResponse({"status": "error", "error": "Invalid YAML: expected dictionary"}, status_code=400)
            from .config import _migrate_config
            cfg = AppConfig.model_validate(_migrate_config(data))
            await _apply_config(cfg)
            return {"status": "ok"}
        except Exception as e:
            return ORJSONResponse({"status": "error", "error": str(e)}, status_code=400)

    @app.get("/api/config/profiles")
    async def list_config_profiles():
        _ensure_default_profile()
        return {"status": "ok", "profiles": app.state.profiles.list_names()}

    @app.get("/api/config/active_profile")
    async def get_active_profile():
        _ensure_default_profile()
        return {"status": "ok", "name": getattr(app.state, "active_profile_name", "")}

    @app.post("/api/config/profiles/{name}/create")
    async def create_config_profile(name: str):
        if not app.state.profiles.is_valid_name(name):
            return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
        if app.state.profiles.exists(name):
            return ORJSONResponse({"status": "error", "error": "profile already exists"}, status_code=409)
        app.state.profiles.save_data(name, app.state.config.model_dump())
        return {"status": "ok"}

    @app.post("/api/config/profiles/{name}/rename")
    async def rename_config_profile(name: str, payload: dict):
        new_name = str((payload or {}).get("new_name") or "").strip()
        if not app.state.profiles.is_valid_name(name) or not app.state.profiles.is_valid_name(new_name):
            return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
        if name == new_name: return {"status": "ok"}
        try:
            app.state.profiles.rename(name, new_name)
        except FileNotFoundError: return ORJSONResponse({"status": "error", "error": "profile not found"}, status_code=404)
        except FileExistsError: return ORJSONResponse({"status": "error", "error": "profile already exists"}, status_code=409)
        if getattr(app.state, "active_profile_name", "") == name:
            app.state.active_profile_name = new_name
            app.state.profiles.persist_active_name(app.state.active_profile_name)
        return {"status": "ok"}

    @app.post("/api/config/profiles/{name}/duplicate")
    async def duplicate_config_profile(name: str, payload: dict):
        new_name = str((payload or {}).get("new_name") or "").strip()
        if not app.state.profiles.is_valid_name(name) or not app.state.profiles.is_valid_name(new_name):
            return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
        if app.state.profiles.exists(new_name):
            return ORJSONResponse({"status": "error", "error": "profile already exists"}, status_code=409)
        try:
            data = app.state.profiles.load_data(name)
            app.state.profiles.save_data(new_name, data)
            return {"status": "ok"}
        except FileNotFoundError: return ORJSONResponse({"status": "error", "error": "profile not found"}, status_code=404)

    @app.post("/api/config/profiles/{name}")
    async def save_config_profile(name: str):
        if not app.state.profiles.is_valid_name(name):
            return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
        app.state.profiles.save_data(name, app.state.config.model_dump())
        return {"status": "ok"}

    @app.get("/api/config/profiles/{name}/export")
    async def export_config_profile(name: str):
        if not app.state.profiles.is_valid_name(name):
            return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
        try:
            data = app.state.profiles.load_data(name)
            return Response(content=yaml.safe_dump(data, sort_keys=False), media_type="text/yaml")
        except FileNotFoundError: return ORJSONResponse({"status": "error", "error": "profile not found"}, status_code=404)
        except Exception as e: return ORJSONResponse({"status": "error", "error": str(e)}, status_code=400)

    @app.post("/api/config/profiles/{name}/load")
    async def load_config_profile(name: str):
        if not app.state.profiles.is_valid_name(name):
            return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
        try:
            data = app.state.profiles.load_data(name)
            from .config import _migrate_config
            cfg = AppConfig.model_validate(_migrate_config(data))
            await _apply_config(cfg)
            app.state.active_profile_name = name
            app.state.profiles.persist_active_name(app.state.active_profile_name)
            return {"status": "ok"}
        except FileNotFoundError: return ORJSONResponse({"status": "error", "error": "profile not found"}, status_code=404)
        except Exception as e: return ORJSONResponse({"status": "error", "error": str(e)}, status_code=400)

    @app.delete("/api/config/profiles/{name}")
    async def delete_config_profile(name: str):
        if not app.state.profiles.is_valid_name(name):
            return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
        was_active = getattr(app.state, "active_profile_name", "") == name
        if not app.state.profiles.delete(name):
            return ORJSONResponse({"status": "error", "error": "profile not found"}, status_code=404)
        if was_active:
            app.state.active_profile_name = ""
            app.state.profiles.persist_active_name("")
        _ensure_default_profile()
        if was_active:
            try:
                next_name = str(getattr(app.state, "active_profile_name", "") or "").strip()
                if next_name:
                    data = app.state.profiles.load_data(next_name)
                    from .config import _migrate_config
                    cfg = AppConfig.model_validate(_migrate_config(data))
                    await _apply_config(cfg)
            except Exception: pass
        return {"status": "ok"}

    @app.get("/api/rigctl_listener")
    async def rigctl_listener_status():
        return {"host": app.state.rigctl_server.host, "port": app.state.rigctl_server.port}

    @app.get("/api/debug/server")
    async def debug_server():
        return {"events": app.state.debug.server.snapshot()}

    @app.get("/api/debug/rig/{idx}")
    async def debug_rig(idx: int):
        log = app.state.debug.rig(idx)
        return {"events": log.snapshot() if log else []}

    @app.post("/api/rig/{idx}/enabled")
    async def set_rig_enabled(idx: int, payload: dict):
        if idx < 0 or idx >= len(app.state.config.rigs):
            return {"status": "error", "error": "rig index out of range"}
        enabled = bool(payload.get("enabled", True))
        app.state.config.rigs[idx].enabled = enabled
        try: app.state.rigs[idx].cfg.enabled = enabled
        except Exception: pass
        save_config(app.state.config, app.state.config_path)
        return {"status": "ok", "enabled": enabled}

    @app.post("/api/rig/{idx}/follow_main")
    async def set_rig_follow_main(idx: int, payload: dict):
        if idx < 0 or idx >= len(app.state.config.rigs):
            return {"status": "error", "error": "rig index out of range"}
        follow_main = bool(payload.get("follow_main", True))
        app.state.config.rigs[idx].follow_main = follow_main
        try: app.state.rigs[idx].cfg.follow_main = follow_main
        except Exception: pass
        save_config(app.state.config, app.state.config_path)
        return {"status": "ok", "follow_main": follow_main}

    @app.post("/api/rig/{idx}/caps")
    async def refresh_rig_caps(idx: int):
        if idx < 0 or idx >= len(app.state.rigs):
            return {"status": "error", "error": "rig index out of range"}
        rig = app.state.rigs[idx]
        if not (await rig.status()).connected:
            return {"status": "error", "error": "rig not connected"}
        try:
            return {"status": "ok", **(await rig.refresh_caps())}
        except Exception as e: return {"status": "error", "error": str(e)}

    @app.post("/api/rig/enabled_all")
    async def set_all_rigs_enabled(payload: dict):
        enabled = bool(payload.get("enabled", True))
        for r in app.state.config.rigs: r.enabled = enabled
        for rig in getattr(app.state, "rigs", []):
            try: rig.cfg.enabled = enabled
            except Exception: pass
        save_config(app.state.config, app.state.config_path)
        return {"status": "ok", "enabled": enabled}

    @app.post("/api/rig/{idx}/sync_from_source")
    async def sync_rig_from_source(idx: int):
        if idx < 0 or idx >= len(app.state.rigs):
            return {"status": "error", "error": "rig index out of range"}
        src_idx = getattr(app.state.sync_service, 'source_index', 0)
        src, dst = app.state.rigs[src_idx], app.state.rigs[idx]
        st = await src.status()
        if not st.connected or st.frequency_hz is None:
            return {"status": "error", "error": "source rig not connected"}
        freq_ok = await dst.set_frequency(st.frequency_hz)
        mode_ok = await dst.set_mode(st.mode, st.passband) if st.mode else True
        return {"status": "ok", "freq_ok": freq_ok, "mode_ok": mode_ok}

    @app.post("/api/rig/sync_all_once")
    async def sync_all_once():
        if not app.state.rigs: return {"status": "error", "error": "no rigs"}
        src_idx = max(0, min(getattr(app.state.sync_service, 'source_index', 0), len(app.state.rigs) - 1))
        src = app.state.rigs[src_idx]
        st = await src.status()
        if not st.connected or st.frequency_hz is None:
            return {"status": "error", "error": "source rig not connected"}
        results = []
        for i, rig in enumerate(app.state.rigs):
            if i == src_idx or not getattr(rig.cfg, "enabled", True) or not getattr(rig.cfg, "follow_main", True):
                continue
            freq_ok = await rig.set_frequency(st.frequency_hz)
            mode_ok = await rig.set_mode(st.mode, st.passband) if st.mode else True
            results.append({"index": i, "freq_ok": freq_ok, "mode_ok": mode_ok})
        return {"status": "ok", "results": results}

    @app.get("/api/bind_addrs")
    async def get_bind_addrs():
        addrs = {"127.0.0.1", "0.0.0.0"}
        try:
            for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
                if ip: addrs.add(ip)
        except Exception: pass
        try:
            out = subprocess.check_output(["ifconfig"], text=True, stderr=subprocess.DEVNULL)
            for m in re.finditer(r"\binet\s+(\d+\.\d+\.\d+\.\d+)", out):
                if m.group(1): addrs.add(m.group(1))
        except Exception: pass
        return sorted(addrs)

    @app.get("/api/status")
    async def get_status():
        rigs = [await r.safe_status() for r in app.state.rigs]
        for idx, r in enumerate(rigs): r["index"] = idx
        result = {
            "rigs": rigs,
            "sync_enabled": app.state.sync_service.enabled,
            "sync_source_index": app.state.sync_service.source_index,
            "rigctl_to_main_enabled": getattr(app.state.config, "rigctl_to_main_enabled", True),
            "all_rigs_enabled": bool(rigs) and all(r.get("enabled", True) is not False for r in rigs),
        }
        if hasattr(app.state.sync_service, '_task'):
            result["sync_service_running"] = app.state.sync_service._task is not None and not app.state.sync_service._task.done()
        return result

    @app.post("/api/sync")
    async def set_sync(payload: dict):
        if "enabled" in payload:
            app.state.sync_service.enabled = bool(payload["enabled"])
            app.state.config.sync_enabled = app.state.sync_service.enabled
        if "source_index" in payload:
            try: app.state.sync_service.source_index = int(payload["source_index"])
            except Exception: pass
            app.state.config.sync_source_index = app.state.sync_service.source_index
        save_config(app.state.config, app.state.config_path)
        return {"status": "ok", "enabled": app.state.sync_service.enabled, "sync_source_index": app.state.sync_service.source_index}

    @app.post("/api/rigctl_to_main")
    async def set_rigctl_to_main(payload: dict):
        enabled = bool(payload.get("enabled", True))
        app.state.config.rigctl_to_main_enabled = enabled
        save_config(app.state.config, app.state.config_path)
        return {"status": "ok", "enabled": enabled}

    @app.post("/api/rig/{which}/set")
    async def set_rig(which: str, payload: dict):
        idx = {"a": 0, "b": 1}.get(which.lower())
        if idx is None:
            try: idx = int(which)
            except ValueError: return {"status": "error", "error": "invalid rig index"}
        if idx < 0 or idx >= len(app.state.rigs):
            return {"status": "error", "error": "rig index out of range"}
        
        rig, res = app.state.rigs[idx], {}
        freq, mode, pb, vfo = payload.get("frequency_hz"), payload.get("mode"), payload.get("passband"), payload.get("vfo")
        
        if freq is not None:
            hz = int(freq)
            if not getattr(rig.cfg, "allow_out_of_band", False):
                presets = [p for p in getattr(rig.cfg, "band_presets", []) if getattr(p, "enabled", True) is not False]
                ranges = [(getattr(p, "lower_hz", None), getattr(p, "upper_hz", None)) for p in presets]
                if any(r[0] is not None and r[1] is not None for r in ranges):
                    if not any(r[0] is not None and r[1] is not None and hz >= int(r[0]) and hz <= int(r[1]) for r in ranges):
                        return {"status": "error", "error": "frequency out of configured band ranges", "frequency_hz": hz}
            res["freq_ok"] = await rig.set_frequency(hz)
        if mode is not None: res["mode_ok"] = await rig.set_mode(str(mode), pb)
        if vfo is not None: res["vfo_ok"] = await rig.set_vfo(str(vfo))
        return {"status": "ok", **res}

    @app.post("/api/test-rig")
    async def test_rig_connection(rig_config: dict):
        from .config import RigConfig, parse_dump_state_ranges, detect_bands_from_ranges
        try:
            cfg = RigConfig.model_validate(rig_config)
            test_rig = RigClient(cfg)
            try:
                status = await test_rig.safe_status()
                detected_bands = []
                try:
                    lines = await test_rig.dump_state()
                    if lines:
                        detected_bands = [{"label": p.label, "frequency_hz": p.frequency_hz, "enabled": p.enabled, "lower_hz": p.lower_hz, "upper_hz": p.upper_hz} 
                                         for p in detect_bands_from_ranges(parse_dump_state_ranges(lines))]
                except Exception: pass
                caps = await test_rig.refresh_caps() if status.get("connected") else None
                await test_rig.close()
                if status.get("error"): return {"status": "error", "message": f"Connection failed: {status['error']}", "details": status}
                
                msg = f"Connected successfully! Frequency: {status['frequency_hz']} Hz, Mode: {status.get('mode', 'unknown')}."
                if detected_bands: msg += f" Detected {len(detected_bands)} supported bands."
                return {"status": "success", "message": msg, "details": status, "detected_bands": detected_bands, "caps": (caps or {}).get("caps", {}), "modes": (caps or {}).get("modes", [])}
            except Exception as e:
                await test_rig.close()
                return {"status": "error", "message": f"Connection test failed: {str(e)}", "details": {"error": str(e)}}
        except Exception as e: return {"status": "error", "message": f"Invalid configuration: {str(e)}", "details": {"error": str(e)}}

    @app.get("/api/serial-ports")
    async def list_serial_ports():
        try:
            import serial.tools.list_ports
            return {"status": "ok", "ports": [{"device": p.device, "description": p.description, "hwid": p.hwid} for p in serial.tools.list_ports.comports()]}
        except ImportError: return {"status": "error", "message": "pyserial not installed.", "ports": []}
        except Exception as e: return {"status": "error", "message": str(e), "ports": []}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        try:
            await ws.send_json(await get_status())
            while True:
                await asyncio.sleep(1.0)
                await ws.send_json(await get_status())
        except (WebSocketDisconnect, Exception): pass

    return app


def run():
    import uvicorn
    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass

    port = int(os.getenv("MULTIRIG_HTTP_PORT", os.getenv("PORT", 8000)))
    uvicorn.run(create_app(), host="0.0.0.0", port=port)
