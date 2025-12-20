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
from .rigctl_tcp import RigctlTcpServer, RigctlServerConfig
from .debug_log import DebugStore


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def create_app(config_path: Optional[Path] = None) -> FastAPI:
    """Create and configure the MultiRig FastAPI application.

    This function wires together:
    - The runtime configuration loading/saving.
    - Rig backend construction.
    - The sync service and the built-in rigctl TCP listener.
    - HTTP API routes and static/template assets.

    Args:
        config_path: Optional path to the main YAML config file. If omitted, the
            app uses `MULTIRIG_CONFIG` if set, otherwise `./multirig.config.yaml`.

    Returns:
        A configured FastAPI application instance.
    """
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manage application startup/shutdown.

        On startup, the sync service and rigctl TCP server are started.
        On shutdown, services are stopped and rig backends are closed.

        Args:
            app: The FastAPI app instance.

        Yields:
            None. Control returns to FastAPI for the duration of the app.
        """
        try:
            await _bootstrap_active_profile()
        except Exception:
            pass

        await app.state.sync_service.start()
        try:
            await app.state.rigctl_server.start()
        except Exception:
            pass
        yield
        await app.state.sync_service.stop()
        try:
            await app.state.rigctl_server.stop()
        except Exception:
            pass
        # Close rig backends
        for rig in getattr(app.state, "rigs", []):
            try:
                await rig.close()
            except Exception:
                pass

    app = FastAPI(title="MultiRig", version="0.1.0", default_response_class=ORJSONResponse, lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Ensure assets exist
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    if config_path is None:
        env_path = os.getenv("MULTIRIG_CONFIG")
        if env_path:
            config_path = Path(env_path)
        else:
            config_path = Path.cwd() / "multirig.config.yaml"

    app.state.config_path = config_path
    app.state.config = load_config(app.state.config_path)
    app.state.active_profile_name = ""
    active_profile_path = app.state.config_path.parent / "multirig.config.active_profile"
    try:
        if active_profile_path.exists():
            app.state.active_profile_name = active_profile_path.read_text().strip()
    except Exception:
        pass
    # Build rigs list
    app.state.rigs: List[RigClient] = [RigClient(rc) for rc in app.state.config.rigs]
    app.state.debug = DebugStore(len(app.state.rigs), rig_maxlen=3000)
    for idx, rig in enumerate(app.state.rigs):
        log = app.state.debug.rig(idx)
        if log is None:
            continue
        try:
            setattr(rig._backend, "_debug", log)
        except Exception:
            pass
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
        if port_s is not None:
            try:
                return int(port_s)
            except Exception:
                return app.state.config.rigctl_listen_port
        return app.state.config.rigctl_listen_port

    app.state.rigctl_server = RigctlTcpServer(
        get_rigs=lambda: app.state.rigs,
        get_source_index=lambda: app.state.sync_service.source_index,
        get_rigctl_to_main_enabled=lambda: app.state.config.rigctl_to_main_enabled,
        get_sync_enabled=lambda: app.state.config.sync_enabled,
        config=RigctlServerConfig(host=_rigctl_bind_host(), port=_rigctl_bind_port()),
        debug=app.state.debug.server,
    )

    async def _restart_rigctl_server(start: bool = True) -> None:
        try:
            await app.state.rigctl_server.stop()
        except Exception:
            pass
        app.state.rigctl_server = RigctlTcpServer(
            get_rigs=lambda: app.state.rigs,
            get_source_index=lambda: app.state.sync_service.source_index,
            get_rigctl_to_main_enabled=lambda: app.state.config.rigctl_to_main_enabled,
            get_sync_enabled=lambda: app.state.config.sync_enabled,
            config=RigctlServerConfig(host=_rigctl_bind_host(), port=_rigctl_bind_port()),
            debug=app.state.debug.server,
        )
        if start:
            try:
                await app.state.rigctl_server.start()
            except Exception:
                pass

    async def _apply_config(cfg: AppConfig, restart_rigctl: bool = True):
        """Apply a new configuration to the running server.

        This updates the in-memory `app.state.config`, rebuilds rig backends, and
        reconfigures the sync service and rigctl TCP server.

        Important behavior:
        - `test_mode` is preserved from the currently loaded config.
        - When not in `test_mode`, the config is persisted to disk.

        Args:
            cfg: A validated `AppConfig` instance to apply.
        """
        # Preserve test_mode if not explicitly set in new config (though AppConfig defaults it to False)
        # Actually, cfg comes from user input which might not have test_mode set (excluded).
        # We should respect the current app mode.
        current_test_mode = getattr(app.state.config, "test_mode", False)
        cfg.test_mode = current_test_mode

        app.state.config = cfg
        save_config(cfg, app.state.config_path)

        # Rebuild rigs
        # Close existing
        for rig in getattr(app.state, "rigs", []):
            try:
                await rig.close()
            except Exception:
                pass
        app.state.rigs = [RigClient(rc) for rc in cfg.rigs]
        app.state.debug.ensure_rigs(len(app.state.rigs))
        for idx, rig in enumerate(app.state.rigs):
            log = app.state.debug.rig(idx)
            if log is None:
                continue
            try:
                setattr(rig._backend, "_debug", log)
            except Exception:
                pass
        
        # Update sync service settings/reference
        app.state.sync_service.rigs = app.state.rigs
        app.state.sync_service.interval_ms = cfg.poll_interval_ms
        app.state.sync_service.enabled = cfg.sync_enabled
        app.state.sync_service.source_index = cfg.sync_source_index
        # Reset sync-service debounce cache so a newly applied config will
        # immediately attempt to sync current state to followers.
        try:
            app.state.sync_service._last = (None, None, None)
        except Exception:
            pass
        
        # Restart sync service to pick up new rigs
        await app.state.sync_service.stop()
        await app.state.sync_service.start()
        
        await _restart_rigctl_server(start=restart_rigctl)

    def _profiles_dir() -> Path:
        """Return the on-disk directory used for config profile storage."""
        return app.state.config_path.parent / "multirig.config.profiles"

    def _active_profile_path() -> Path:
        return app.state.config_path.parent / "multirig.config.active_profile"

    def _persist_active_profile_name(name: str) -> None:
        if getattr(app.state.config, "test_mode", False):
            return
        p = _active_profile_path()
        try:
            if not name:
                if p.exists():
                    p.unlink()
                return
            p.write_text(name)
        except Exception:
            pass

    def _is_valid_profile_name(name: str) -> bool:
        """Validate a profile name.

        Profile names are used directly as filesystem stems in non-test mode, so
        they are constrained to a safe subset.

        Args:
            name: Proposed profile name.

        Returns:
            True if the name is valid; otherwise False.
        """
        if not name:
            return False
        if len(name) > 100:
            return False
        return re.fullmatch(r"[A-Za-z0-9_.-]+", name) is not None

    def _list_profile_names() -> List[str]:
        """List available config profile names.

        Returns:
            Sorted list of profile names.
        """
        if getattr(app.state.config, "test_mode", False):
            store = getattr(app.state, "config_profiles", {})
            if isinstance(store, dict):
                return sorted([str(k) for k in store.keys()])
            return []
        d = _profiles_dir()
        if not d.exists():
            return []
        names: List[str] = []
        for p in d.glob("*.yaml"):
            if p.is_file():
                names.append(p.stem)
        for p in d.glob("*.yml"):
            if p.is_file():
                names.append(p.stem)
        return sorted(list(dict.fromkeys(names)))

    def _profile_exists(name: str) -> bool:
        if getattr(app.state.config, "test_mode", False):
            store = getattr(app.state, "config_profiles", {})
            return isinstance(store, dict) and name in store
        d = _profiles_dir()
        return (d / f"{name}.yaml").exists() or (d / f"{name}.yml").exists()

    def _ensure_default_profile() -> None:
        names = _list_profile_names()
        if names:
            active = str(getattr(app.state, "active_profile_name", "") or "").strip()
            if not active or active not in names:
                app.state.active_profile_name = names[0]
                _persist_active_profile_name(app.state.active_profile_name)
            return
        if not _profile_exists("Default"):
            _save_profile_data("Default", app.state.config.model_dump())
        app.state.active_profile_name = "Default"
        _persist_active_profile_name(app.state.active_profile_name)

    async def _bootstrap_active_profile() -> None:
        _ensure_default_profile()
        name = str(getattr(app.state, "active_profile_name", "") or "").strip()
        if not name:
            return
        try:
            data = _load_profile_data(name)
            from .config import _migrate_config
            data = _migrate_config(data)
            cfg = AppConfig.model_validate(data)
            await _apply_config(cfg, restart_rigctl=False)
        except Exception:
            pass

    def _rename_profile(old_name: str, new_name: str) -> None:
        if getattr(app.state.config, "test_mode", False):
            store = getattr(app.state, "config_profiles", {})
            if not isinstance(store, dict) or old_name not in store:
                raise FileNotFoundError(old_name)
            if new_name in store:
                raise FileExistsError(new_name)
            store[new_name] = store.pop(old_name)
            return
        d = _profiles_dir()
        p1 = d / f"{old_name}.yaml"
        p2 = d / f"{old_name}.yml"
        src = p1 if p1.exists() else p2
        if not src.exists():
            raise FileNotFoundError(old_name)
        dst = d / f"{new_name}{src.suffix}"
        if dst.exists() or (d / f"{new_name}.yaml").exists() or (d / f"{new_name}.yml").exists():
            raise FileExistsError(new_name)
        d.mkdir(parents=True, exist_ok=True)
        src.rename(dst)

    def _load_profile_data(name: str) -> Dict[str, Any]:
        """Load raw profile data (unvalidated) by name.

        Args:
            name: Profile name.

        Returns:
            A dict representing an `AppConfig` payload.

        Raises:
            FileNotFoundError: If the profile does not exist.
            ValueError: If the stored profile is not a YAML mapping.
        """
        if getattr(app.state.config, "test_mode", False):
            store = getattr(app.state, "config_profiles", {})
            if not isinstance(store, dict) or name not in store:
                raise FileNotFoundError(name)
            data = store[name]
            if not isinstance(data, dict):
                raise ValueError("invalid profile")
            return data
        d = _profiles_dir()
        p1 = d / f"{name}.yaml"
        p2 = d / f"{name}.yml"
        path = p1 if p1.exists() else p2
        if not path.exists():
            raise FileNotFoundError(name)
        raw = yaml.safe_load(path.read_text()) or {}
        if not isinstance(raw, dict):
            raise ValueError("invalid profile")
        return raw

    def _save_profile_data(name: str, data: Dict[str, Any]) -> None:
        """Persist a profile payload.

        In `test_mode`, profiles are stored in-memory (`app.state.config_profiles`).
        Otherwise, they are written to `multirig.config.profiles/<name>.yaml`.

        Args:
            name: Profile name.
            data: Profile payload.
        """
        if getattr(app.state.config, "test_mode", False):
            if not hasattr(app.state, "config_profiles") or not isinstance(app.state.config_profiles, dict):
                app.state.config_profiles = {}
            app.state.config_profiles[name] = data
            return
        d = _profiles_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{name}.yaml"
        path.write_text(yaml.safe_dump(data, sort_keys=False))

    def _delete_profile(name: str) -> bool:
        """Delete a profile.

        Args:
            name: Profile name.

        Returns:
            True if a profile was removed; False if it did not exist.
        """
        if getattr(app.state.config, "test_mode", False):
            store = getattr(app.state, "config_profiles", {})
            if isinstance(store, dict) and name in store:
                del store[name]
                return True
            return False
        d = _profiles_dir()
        removed = False
        for ext in ("yaml", "yml"):
            p = d / f"{name}.{ext}"
            if p.exists():
                try:
                    p.unlink()
                    removed = True
                except Exception:
                    pass
        return removed

    # Pages
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "assets_ts": int(time.time() * 1000),
                "app_version": getattr(app, "version", ""),
            },
        )

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request):
        return templates.TemplateResponse(
            "settings.html",
            {
                "request": request,
                "config": app.state.config,
                "assets_ts": int(time.time() * 1000),
                "app_version": getattr(app, "version", ""),
            },
        )

    # API
    @app.get("/api/config")
    async def get_config():
        """Get the currently applied configuration."""
        return app.state.config

    @app.post("/api/config")
    async def update_config(cfg: AppConfig):
        """Replace the current configuration.

        Args:
            cfg: New configuration payload.

        Returns:
            Status object.
        """
        await _apply_config(cfg)
        return {"status": "ok"}

    @app.get("/api/config/export")
    async def export_config():
        """Export the current configuration as YAML."""
        content = yaml.safe_dump(app.state.config.model_dump(), sort_keys=False)
        return Response(content=content, media_type="text/yaml")

    @app.post("/api/config/import")
    async def import_config(request: Request):
        """Import a configuration from YAML.

        The body is parsed as YAML, migrated to the current schema, validated
        as an `AppConfig`, and then applied.

        Args:
            request: Incoming FastAPI request.

        Returns:
            Status object.
        """
        try:
            body = await request.body()
            data = yaml.safe_load(body)
            if not isinstance(data, dict):
                return ORJSONResponse({"status": "error", "error": "Invalid YAML: expected dictionary"}, status_code=400)
            
            # Need to handle migration if needed, though load_config handles it usually.
            # load_config uses _migrate_config. We should probably use it here too.
            from .config import _migrate_config
            data = _migrate_config(data)
            
            cfg = AppConfig.model_validate(data)
            await _apply_config(cfg)
            return {"status": "ok"}
        except Exception as e:
            return ORJSONResponse({"status": "error", "error": str(e)}, status_code=400)

    @app.get("/api/config/profiles")
    async def list_config_profiles():
        """List available configuration profile names."""
        _ensure_default_profile()
        return {"status": "ok", "profiles": _list_profile_names()}

    @app.get("/api/config/active_profile")
    async def get_active_profile():
        _ensure_default_profile()
        return {"status": "ok", "name": getattr(app.state, "active_profile_name", "")}

    @app.post("/api/config/profiles/{name}/create")
    async def create_config_profile(name: str):
        if not _is_valid_profile_name(name):
            return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
        if _profile_exists(name):
            return ORJSONResponse({"status": "error", "error": "profile already exists"}, status_code=409)
        _save_profile_data(name, app.state.config.model_dump())
        return {"status": "ok"}

    @app.post("/api/config/profiles/{name}/rename")
    async def rename_config_profile(name: str, payload: dict):
        new_name = str((payload or {}).get("new_name") or "").strip()
        if not _is_valid_profile_name(name) or not _is_valid_profile_name(new_name):
            return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
        if name == new_name:
            return {"status": "ok"}
        try:
            _rename_profile(name, new_name)
        except FileNotFoundError:
            return ORJSONResponse({"status": "error", "error": "profile not found"}, status_code=404)
        except FileExistsError:
            return ORJSONResponse({"status": "error", "error": "profile already exists"}, status_code=409)
        if getattr(app.state, "active_profile_name", "") == name:
            app.state.active_profile_name = new_name
            _persist_active_profile_name(app.state.active_profile_name)
        return {"status": "ok"}

    @app.post("/api/config/profiles/{name}/duplicate")
    async def duplicate_config_profile(name: str, payload: dict):
        new_name = str((payload or {}).get("new_name") or "").strip()
        if not _is_valid_profile_name(name) or not _is_valid_profile_name(new_name):
            return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
        if _profile_exists(new_name):
            return ORJSONResponse({"status": "error", "error": "profile already exists"}, status_code=409)
        try:
            data = _load_profile_data(name)
            _save_profile_data(new_name, data)
            return {"status": "ok"}
        except FileNotFoundError:
            return ORJSONResponse({"status": "error", "error": "profile not found"}, status_code=404)

    @app.post("/api/config/profiles/{name}")
    async def save_config_profile(name: str):
        """Save the current configuration as a named profile.

        Args:
            name: Profile name.

        Returns:
            Status object.
        """
        if not _is_valid_profile_name(name):
            return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
        _save_profile_data(name, app.state.config.model_dump())
        return {"status": "ok"}

    @app.get("/api/config/profiles/{name}/export")
    async def export_config_profile(name: str):
        """Export a saved configuration profile as YAML.

        Args:
            name: Profile name.

        Returns:
            YAML response body.
        """
        if not _is_valid_profile_name(name):
            return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
        try:
            data = _load_profile_data(name)
            content = yaml.safe_dump(data, sort_keys=False)
            return Response(content=content, media_type="text/yaml")
        except FileNotFoundError:
            return ORJSONResponse({"status": "error", "error": "profile not found"}, status_code=404)
        except Exception as e:
            return ORJSONResponse({"status": "error", "error": str(e)}, status_code=400)

    @app.post("/api/config/profiles/{name}/load")
    async def load_config_profile(name: str):
        """Load a saved configuration profile.

        The profile is read, migrated, validated as an `AppConfig`, and applied.

        Args:
            name: Profile name.

        Returns:
            Status object.
        """
        if not _is_valid_profile_name(name):
            return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
        try:
            data = _load_profile_data(name)
            from .config import _migrate_config
            data = _migrate_config(data)
            cfg = AppConfig.model_validate(data)
            await _apply_config(cfg)
            app.state.active_profile_name = name
            _persist_active_profile_name(app.state.active_profile_name)
            return {"status": "ok"}
        except FileNotFoundError:
            return ORJSONResponse({"status": "error", "error": "profile not found"}, status_code=404)
        except Exception as e:
            return ORJSONResponse({"status": "error", "error": str(e)}, status_code=400)

    @app.delete("/api/config/profiles/{name}")
    async def delete_config_profile(name: str):
        """Delete a saved configuration profile.

        Args:
            name: Profile name.

        Returns:
            Status object.
        """
        if not _is_valid_profile_name(name):
            return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
        was_active = getattr(app.state, "active_profile_name", "") == name
        removed = _delete_profile(name)
        if not removed:
            return ORJSONResponse({"status": "error", "error": "profile not found"}, status_code=404)
        if was_active:
            app.state.active_profile_name = ""
            _persist_active_profile_name(app.state.active_profile_name)
        _ensure_default_profile()

        if was_active:
            try:
                next_name = str(getattr(app.state, "active_profile_name", "") or "").strip()
                if next_name:
                    data = _load_profile_data(next_name)
                    from .config import _migrate_config
                    data = _migrate_config(data)
                    cfg = AppConfig.model_validate(data)
                    await _apply_config(cfg)
            except Exception:
                pass
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
        if log is None:
            return {"events": []}
        return {"events": log.snapshot()}

    @app.post("/api/rig/{idx}/enabled")
    async def set_rig_enabled(idx: int, payload: dict):
        if idx < 0 or idx >= len(app.state.config.rigs):
            return {"status": "error", "error": "rig index out of range"}
        enabled = bool(payload.get("enabled", True))
        app.state.config.rigs[idx].enabled = enabled
        try:
            app.state.rigs[idx].cfg.enabled = enabled
        except Exception:
            pass
        save_config(app.state.config, app.state.config_path)
        return {"status": "ok", "enabled": enabled}

    @app.post("/api/rig/{idx}/follow_main")
    async def set_rig_follow_main(idx: int, payload: dict):
        if idx < 0 or idx >= len(app.state.config.rigs):
            return {"status": "error", "error": "rig index out of range"}
        follow_main = bool(payload.get("follow_main", True))
        app.state.config.rigs[idx].follow_main = follow_main
        try:
            app.state.rigs[idx].cfg.follow_main = follow_main
        except Exception:
            pass
        save_config(app.state.config, app.state.config_path)
        return {"status": "ok", "follow_main": follow_main}

    @app.post("/api/rig/{idx}/caps")
    async def refresh_rig_caps(idx: int):
        if idx < 0 or idx >= len(app.state.rigs):
            return {"status": "error", "error": "rig index out of range"}
        rig = app.state.rigs[idx]
        st = await rig.status()
        if not st.connected:
            return {"status": "error", "error": "rig not connected"}
        try:
            result = await rig.refresh_caps()
            return {"status": "ok", **result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @app.post("/api/rig/enabled_all")
    async def set_all_rigs_enabled(payload: dict):
        enabled = bool(payload.get("enabled", True))
        for i in range(len(app.state.config.rigs)):
            app.state.config.rigs[i].enabled = enabled
        for rig in getattr(app.state, "rigs", []):
            try:
                rig.cfg.enabled = enabled
            except Exception:
                pass
        save_config(app.state.config, app.state.config_path)
        return {"status": "ok", "enabled": enabled}

    @app.post("/api/rig/{idx}/sync_from_source")
    async def sync_rig_from_source(idx: int):
        if idx < 0 or idx >= len(app.state.rigs):
            return {"status": "error", "error": "rig index out of range"}
        src_idx = app.state.sync_service.source_index
        if src_idx < 0 or src_idx >= len(app.state.rigs):
            src_idx = 0
        src = app.state.rigs[src_idx]
        dst = app.state.rigs[idx]
        st = await src.status()
        if not st.connected or st.frequency_hz is None:
            return {"status": "error", "error": "source rig not connected"}
        freq_ok = await dst.set_frequency(st.frequency_hz)
        mode_ok = True
        if st.mode is not None:
            mode_ok = await dst.set_mode(st.mode, st.passband)
        return {"status": "ok", "freq_ok": freq_ok, "mode_ok": mode_ok}

    @app.post("/api/rig/sync_all_once")
    async def sync_all_once():
        if not app.state.rigs:
            return {"status": "error", "error": "no rigs"}
        src_idx = app.state.sync_service.source_index
        src_idx = max(0, min(src_idx, len(app.state.rigs) - 1))
        src = app.state.rigs[src_idx]
        st = await src.status()
        if not st.connected or st.frequency_hz is None:
            return {"status": "error", "error": "source rig not connected"}
        results = []
        for i, rig in enumerate(app.state.rigs):
            if i == src_idx:
                continue
            if not getattr(rig.cfg, "enabled", True):
                continue
            if not getattr(rig.cfg, "follow_main", True):
                continue
            freq_ok = await rig.set_frequency(st.frequency_hz)
            mode_ok = True
            if st.mode is not None:
                mode_ok = await rig.set_mode(st.mode, st.passband)
            results.append({"index": i, "freq_ok": freq_ok, "mode_ok": mode_ok})
        return {"status": "ok", "results": results}

    @app.get("/api/bind_addrs")
    async def get_bind_addrs():
        addrs = {"127.0.0.1", "0.0.0.0"}
        try:
            host = socket.gethostname()
            for fam, _, _, _, sockaddr in socket.getaddrinfo(host, None):
                if fam == socket.AF_INET:
                    ip = sockaddr[0]
                    if ip:
                        addrs.add(ip)
        except Exception:
            pass
        try:
            _, _, ips = socket.gethostbyname_ex(socket.gethostname())
            for ip in ips:
                if ip:
                    addrs.add(ip)
        except Exception:
            pass
        try:
            out = subprocess.check_output(["ifconfig"], text=True, stderr=subprocess.DEVNULL)
            for m in re.finditer(r"\binet\s+(\d+\.\d+\.\d+\.\d+)", out):
                ip = m.group(1)
                if ip:
                    addrs.add(ip)
        except Exception:
            pass
        return sorted(addrs)

    @app.get("/api/status")
    async def get_status():
        rigs = [await r.safe_status() for r in app.state.rigs]
        # attach index for client convenience
        for idx, r in enumerate(rigs):
            r["index"] = idx
        all_rigs_enabled = bool(rigs) and all(r.get("enabled", True) is not False for r in rigs)
        result = {
            "rigs": rigs,
            "sync_enabled": app.state.sync_service.enabled,
            "sync_source_index": app.state.sync_service.source_index,
            "rigctl_to_main_enabled": getattr(app.state.config, "rigctl_to_main_enabled", True),
            "all_rigs_enabled": all_rigs_enabled,
        }
        # Add diagnostic info if available (not present in test mocks)
        if hasattr(app.state.sync_service, '_task'):
            result["sync_service_running"] = app.state.sync_service._task is not None and not app.state.sync_service._task.done()
        if hasattr(app.state.sync_service, 'rigs'):
            result["sync_service_rigs_count"] = len(app.state.sync_service.rigs)
        return result

    @app.post("/api/sync/{enabled}")
    async def set_sync_compat(enabled: bool):
        app.state.sync_service.enabled = enabled
        app.state.config.sync_enabled = enabled
        save_config(app.state.config, app.state.config_path)
        return {"status": "ok", "enabled": enabled, "sync_source_index": app.state.sync_service.source_index}

    @app.post("/api/sync")
    async def set_sync(payload: dict):
        if "enabled" in payload:
            app.state.sync_service.enabled = bool(payload["enabled"])
            app.state.config.sync_enabled = app.state.sync_service.enabled
        if "source_index" in payload:
            try:
                app.state.sync_service.source_index = int(payload["source_index"])
            except Exception:
                pass
            app.state.config.sync_source_index = app.state.sync_service.source_index
        save_config(app.state.config, app.state.config_path)
        return {
            "status": "ok",
            "enabled": app.state.sync_service.enabled,
            "sync_source_index": app.state.sync_service.source_index,
        }

    @app.post("/api/rigctl_to_main")
    async def set_rigctl_to_main(payload: dict):
        enabled = bool(payload.get("enabled", True))
        app.state.config.rigctl_to_main_enabled = enabled
        save_config(app.state.config, app.state.config_path)
        return {"status": "ok", "enabled": enabled}

    @app.post("/api/rig/{which}/set")
    async def set_rig(which: str, payload: dict):
        # Back-compat: 'a'/'b' map to indices 0/1. Otherwise expect an integer index as string.
        if which.lower() in ("a", "b"):
            idx = 0 if which.lower() == "a" else 1
        else:
            try:
                idx = int(which)
            except ValueError:
                return {"status": "error", "error": "invalid rig index"}
        if idx < 0 or idx >= len(app.state.rigs):
            return {"status": "error", "error": "rig index out of range"}
        rig = app.state.rigs[idx]
        freq = payload.get("frequency_hz")
        mode = payload.get("mode")
        passband = payload.get("passband")
        vfo = payload.get("vfo")
        results = {}
        if freq is not None:
            hz = int(freq)
            allow_oob = bool(getattr(rig.cfg, "allow_out_of_band", False))
            if not allow_oob:
                presets = getattr(rig.cfg, "band_presets", [])
                in_any = False
                has_any_ranges = False
                for p in presets:
                    try:
                        if getattr(p, "enabled", True) is False:
                            continue
                        lo = getattr(p, "lower_hz", None)
                        hi = getattr(p, "upper_hz", None)
                        if lo is None or hi is None:
                            # Band preset without explicit ranges - allow any frequency
                            in_any = True
                            break
                        has_any_ranges = True
                        if hz >= int(lo) and hz <= int(hi):
                            in_any = True
                            break
                    except Exception:
                        continue
                # Only reject if we have explicit ranges and frequency doesn't match any
                if has_any_ranges and not in_any:
                    return {
                        "status": "error",
                        "error": "frequency out of configured band ranges",
                        "frequency_hz": hz,
                    }
            results["freq_ok"] = await rig.set_frequency(hz)
        if mode is not None:
            results["mode_ok"] = await rig.set_mode(str(mode), passband)
        if vfo is not None:
            results["vfo_ok"] = await rig.set_vfo(str(vfo))
        return {"status": "ok", **results}

    @app.post("/api/test-rig")
    async def test_rig_connection(rig_config: dict):
        """Test a rig configuration without saving it."""
        from .config import RigConfig, parse_dump_state_ranges, detect_bands_from_ranges
        try:
            # Validate and create RigConfig from payload
            cfg = RigConfig.model_validate(rig_config)
            # Create a temporary RigClient to test the connection
            test_rig = RigClient(cfg)
            try:
                # Try to get basic info from the rig
                status = await test_rig.safe_status()
                
                # Try to detect supported bands from dump_state
                detected_bands = []
                try:
                    dump_state_lines = await test_rig.dump_state()
                    if dump_state_lines:
                        freq_ranges = parse_dump_state_ranges(dump_state_lines)
                        if freq_ranges:
                            band_presets = detect_bands_from_ranges(freq_ranges)
                            detected_bands = [
                                {
                                    "label": p.label,
                                    "frequency_hz": p.frequency_hz,
                                    "enabled": p.enabled,
                                    "lower_hz": p.lower_hz,
                                    "upper_hz": p.upper_hz,
                                }
                                for p in band_presets
                            ]
                except Exception:
                    # If band detection fails, continue without it
                    pass

                caps_result = None
                try:
                    caps_result = await test_rig.refresh_caps()
                except Exception:
                    caps_result = None
                
                await test_rig.close()

                if status.get("error"):
                    return {
                        "status": "error",
                        "message": f"Connection failed: {status['error']}",
                        "details": status
                    }

                # Check if we got valid data
                if status.get("frequency_hz") is not None:
                    band_msg = f" Detected {len(detected_bands)} supported bands." if detected_bands else ""
                    return {
                        "status": "success",
                        "message": f"Connected successfully! Frequency: {status['frequency_hz']} Hz, Mode: {status.get('mode', 'unknown')}.{band_msg}",
                        "details": status,
                        "detected_bands": detected_bands,
                        "caps": (caps_result or {}).get("caps", {}),
                        "modes": (caps_result or {}).get("modes", []),
                    }
                else:
                    return {
                        "status": "warning",
                        "message": "Connected but could not read rig status. Check your model ID and settings.",
                        "details": status,
                        "detected_bands": detected_bands,
                        "caps": (caps_result or {}).get("caps", {}),
                        "modes": (caps_result or {}).get("modes", []),
                    }
            except Exception as e:
                await test_rig.close()
                return {
                    "status": "error",
                    "message": f"Connection test failed: {str(e)}",
                    "details": {"error": str(e)}
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Invalid configuration: {str(e)}",
                "details": {"error": str(e)}
            }

    @app.get("/api/serial-ports")
    async def list_serial_ports():
        """List available serial ports on the system."""
        try:
            import serial.tools.list_ports
            ports = []
            for port in serial.tools.list_ports.comports():
                ports.append({
                    "device": port.device,
                    "description": port.description,
                    "hwid": port.hwid,
                })
            return {"status": "ok", "ports": ports}
        except ImportError:
            return {
                "status": "error",
                "message": "pyserial not installed. Install with: pip install pyserial",
                "ports": []
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "ports": []
            }

    # WebSocket for streaming status updates
    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        try:
            # Initial push
            await ws.send_json(await get_status())
            # Stream periodic updates
            while True:
                await asyncio.sleep(1.0)
                await ws.send_json(await get_status())
        except WebSocketDisconnect:
            return
        except Exception as exc:  # noqa: BLE001
            # Best-effort error send
            try:
                await ws.send_json({"error": str(exc)})
            except Exception:
                pass

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
