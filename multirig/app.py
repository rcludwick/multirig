from __future__ import annotations

import asyncio
import os
import re
import socket
import subprocess
from pathlib import Path
from typing import Optional, List

import yaml
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, Response
from fastapi.responses import HTMLResponse, ORJSONResponse
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
    @asynccontextmanager
    async def lifespan(app: FastAPI):
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
        config=RigctlServerConfig(host=_rigctl_bind_host(), port=_rigctl_bind_port()),
        debug=app.state.debug.server,
    )

    async def _restart_rigctl_server() -> None:
        try:
            await app.state.rigctl_server.stop()
        except Exception:
            pass
        app.state.rigctl_server = RigctlTcpServer(
            get_rigs=lambda: app.state.rigs,
            get_source_index=lambda: app.state.sync_service.source_index,
            get_rigctl_to_main_enabled=lambda: app.state.config.rigctl_to_main_enabled,
            config=RigctlServerConfig(host=_rigctl_bind_host(), port=_rigctl_bind_port()),
            debug=app.state.debug.server,
        )
        try:
            await app.state.rigctl_server.start()
        except Exception:
            pass

    async def _apply_config(cfg: AppConfig):
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
        await _restart_rigctl_server()

    # Pages
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request):
        return templates.TemplateResponse("settings.html", {"request": request, "config": app.state.config})

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
        """Export current configuration as YAML."""
        content = yaml.safe_dump(app.state.config.model_dump(), sort_keys=False)
        return Response(content=content, media_type="text/yaml")

    @app.post("/api/config/import")
    async def import_config(request: Request):
        """Import configuration from YAML."""
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
        return {
            "rigs": rigs,
            "sync_enabled": app.state.sync_service.enabled,
            "sync_source_index": app.state.sync_service.source_index,
            "rigctl_to_main_enabled": getattr(app.state.config, "rigctl_to_main_enabled", True),
            "all_rigs_enabled": all_rigs_enabled,
        }

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
                for p in presets:
                    try:
                        if getattr(p, "enabled", True) is False:
                            continue
                        lo = getattr(p, "lower_hz", None)
                        hi = getattr(p, "upper_hz", None)
                        if lo is None or hi is None:
                            continue
                        if hz >= int(lo) and hz <= int(hi):
                            in_any = True
                            break
                    except Exception:
                        continue
                if not in_any:
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
                        "detected_bands": detected_bands
                    }
                else:
                    return {
                        "status": "warning",
                        "message": "Connected but could not read rig status. Check your model ID and settings.",
                        "details": status,
                        "detected_bands": detected_bands
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
