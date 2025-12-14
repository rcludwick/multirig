from __future__ import annotations

import asyncio
import os
import re
import socket
import subprocess
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import AppConfig, load_config, save_config
from .rig import RigClient
from .service import SyncService
from .rigctl_tcp import RigctlTcpServer, RigctlServerConfig


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def create_app(config_path: Optional[Path] = None) -> FastAPI:
    app = FastAPI(title="MultiRig", version="0.1.0")

    # Ensure assets exist
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    app.state.config_path = config_path or Path.cwd() / "multirig.config.yaml"
    app.state.config = load_config(app.state.config_path)
    # Build rigs list
    app.state.rigs: List[RigClient] = [RigClient(rc) for rc in app.state.config.rigs]
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
        config=RigctlServerConfig(host=_rigctl_bind_host(), port=_rigctl_bind_port()),
    )

    async def _restart_rigctl_server() -> None:
        try:
            await app.state.rigctl_server.stop()
        except Exception:
            pass
        app.state.rigctl_server = RigctlTcpServer(
            get_rigs=lambda: app.state.rigs,
            get_source_index=lambda: app.state.sync_service.source_index,
            config=RigctlServerConfig(host=_rigctl_bind_host(), port=_rigctl_bind_port()),
        )
        try:
            await app.state.rigctl_server.start()
        except Exception:
            pass

    @app.on_event("startup")
    async def _startup() -> None:
        await app.state.sync_service.start()
        try:
            await app.state.rigctl_server.start()
        except Exception:
            pass

    @app.on_event("shutdown")
    async def _shutdown() -> None:
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
        # Update sync service settings/reference
        app.state.sync_service.rigs = app.state.rigs
        app.state.sync_service.interval_ms = cfg.poll_interval_ms
        app.state.sync_service.enabled = cfg.sync_enabled
        app.state.sync_service.source_index = cfg.sync_source_index
        await _restart_rigctl_server()
        return {"status": "ok"}

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
        return {
            "rigs": rigs,
            "sync_enabled": app.state.sync_service.enabled,
            "sync_source_index": app.state.sync_service.source_index,
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
        results = {}
        if freq is not None:
            results["freq_ok"] = await rig.set_frequency(int(freq))
        if mode is not None:
            results["mode_ok"] = await rig.set_mode(str(mode), passband)
        return {"status": "ok", **results}

    @app.post("/api/test-rig")
    async def test_rig_connection(rig_config: dict):
        """Test a rig configuration without saving it."""
        from .config import RigConfig
        try:
            # Validate and create RigConfig from payload
            cfg = RigConfig.model_validate(rig_config)
            # Create a temporary RigClient to test the connection
            test_rig = RigClient(cfg)
            try:
                # Try to get basic info from the rig
                status = await test_rig.safe_status()
                await test_rig.close()

                if status.get("error"):
                    return {
                        "status": "error",
                        "message": f"Connection failed: {status['error']}",
                        "details": status
                    }

                # Check if we got valid data
                if status.get("frequency_hz") is not None:
                    return {
                        "status": "success",
                        "message": f"Connected successfully! Frequency: {status['frequency_hz']} Hz, Mode: {status.get('mode', 'unknown')}",
                        "details": status
                    }
                else:
                    return {
                        "status": "warning",
                        "message": "Connected but could not read rig status. Check your model ID and settings.",
                        "details": status
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

    uvicorn.run(create_app(), host="0.0.0.0", port=8000)
