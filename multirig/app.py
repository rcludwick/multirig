from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
try:
    import orjson
    from fastapi.responses import ORJSONResponse
except ImportError:
    ORJSONResponse = JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware

from .config import AppConfig, load_config, save_config
from .rig import RigClient
from .service import SyncService
from .debug_log import DebugStore
from .profiles import ProfileManager
from .routes import router
from .core import bootstrap_active_profile, rebuild_rigs, _rigctl_bind_host, _rigctl_bind_port, AppRigctlServer
from .rigctl_tcp import RigctlServerConfig

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

def create_app(config_path: Optional[Path] = None) -> FastAPI:
    """Create and configure the MultiRig FastAPI application."""
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await bootstrap_active_profile(app)
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

    if config_path is None:
        env_path = os.getenv("MULTIRIG_CONFIG")
        config_path = Path(env_path) if env_path else Path.cwd() / "multirig.config.yaml"

    app.state.config_path = config_path
    app.state.config = load_config(app.state.config_path)
    app.state.profiles = ProfileManager(config_path, test_mode=app.state.config.test_mode)
    app.state.active_profile_name = app.state.profiles.get_active_name()
    
    app.state.rigs: List[RigClient] = []
    app.state.debug = DebugStore(0)
    
    # Initial rig build
    rebuild_rigs(app, app.state.config)

    app.state.sync_service = SyncService(
        app.state.rigs,
        interval_ms=app.state.config.poll_interval_ms,
        enabled=app.state.config.sync_enabled,
        source_index=app.state.config.sync_source_index,
    )

    app.state.rigctl_server = AppRigctlServer(
        fastapi_app=app,
        config=RigctlServerConfig(host=_rigctl_bind_host(app), port=_rigctl_bind_port(app)),
        debug=app.state.debug.server,
    )

    app.include_router(router)

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
