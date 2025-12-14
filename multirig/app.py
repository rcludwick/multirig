from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional, List

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
    # Build rigs list
    app.state.rigs: List[RigClient] = [RigClient(rc) for rc in app.state.config.rigs]
    app.state.sync_service = SyncService(
        app.state.rigs,
        interval_ms=app.state.config.poll_interval_ms,
        enabled=app.state.config.sync_enabled,
        source_index=app.state.config.sync_source_index,
    )

    @app.on_event("startup")
    async def _startup() -> None:
        await app.state.sync_service.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await app.state.sync_service.stop()
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
        return {"status": "ok"}

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
