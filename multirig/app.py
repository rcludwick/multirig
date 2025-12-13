from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import AppConfig, load_config, save_config
from .rig import RigClient
from .service import SyncService


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
    app.state.rig_a = RigClient(app.state.config.rig_a)
    app.state.rig_b = RigClient(app.state.config.rig_b)
    app.state.sync_service = SyncService(
        app.state.rig_a, app.state.rig_b, interval_ms=app.state.config.poll_interval_ms
    )

    @app.on_event("startup")
    async def _startup() -> None:
        await app.state.sync_service.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await app.state.sync_service.stop()
        # Close rig backends
        try:
            await app.state.rig_a.close()
        except Exception:
            pass
        try:
            await app.state.rig_b.close()
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
        # Update rigs
        app.state.rig_a.update_config(cfg.rig_a)
        app.state.rig_b.update_config(cfg.rig_b)
        app.state.sync_service.interval_ms = cfg.poll_interval_ms
        return {"status": "ok"}

    @app.get("/api/status")
    async def get_status():
        a = await app.state.rig_a.safe_status()
        b = await app.state.rig_b.safe_status()
        return {"a": a, "b": b, "sync_enabled": app.state.sync_service.enabled}

    @app.post("/api/sync/{enabled}")
    async def set_sync(enabled: bool):
        app.state.sync_service.enabled = enabled
        return {"status": "ok", "enabled": enabled}

    @app.post("/api/rig/{which}/set")
    async def set_rig(which: str, payload: dict):
        rig = app.state.rig_a if which.lower() == "a" else app.state.rig_b
        freq = payload.get("frequency_hz")
        mode = payload.get("mode")
        passband = payload.get("passband")
        results = {}
        if freq is not None:
            results["freq_ok"] = await rig.set_frequency(int(freq))
        if mode is not None:
            results["mode_ok"] = await rig.set_mode(str(mode), passband)
        return {"status": "ok", **results}

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
