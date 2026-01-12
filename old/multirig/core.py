from __future__ import annotations
import asyncio
import os
import re
from typing import Optional, List, Any, Sequence, TYPE_CHECKING

from fastapi import FastAPI
from .config import AppConfig, save_config
from .rig import RigClient, RigctlServer, RigctlServerConfig
from .profiles import ProfileManager

if TYPE_CHECKING:
    from .router import MessageRouter

class AppRigctlServer(RigctlServer):
    """App-specific RigctlServer implementation."""
    def __init__(
        self,
        fastapi_app: FastAPI,
        config: Optional[RigctlServerConfig] = None,
        debug: Any = None,
        router: Optional[MessageRouter] = None,
    ):
        self.app = fastapi_app
        super().__init__(config, debug, router)

    def get_rigs(self) -> Sequence[RigClient]:
        return self.app.state.rigs

    def get_source_index(self) -> int:
        return self.app.state.sync_service.source_index

    def get_rigctl_to_main_enabled(self) -> bool:
        return self.app.state.config.rigctl_to_main_enabled

    def get_sync_enabled(self) -> bool:
        return self.app.state.config.sync_enabled

def _rigctl_bind_host(app: FastAPI) -> str:
    return os.getenv("MULTIRIG_RIGCTL_HOST", app.state.config.rigctl_listen_host)

def _rigctl_bind_port(app: FastAPI) -> int:
    port_s = os.getenv("MULTIRIG_RIGCTL_PORT")
    try: return int(port_s) if port_s else app.state.config.rigctl_listen_port
    except Exception: return app.state.config.rigctl_listen_port

async def rebuild_rigs(app: FastAPI, cfg: AppConfig):
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
        if log:
            try: setattr(rig._backend, "_debug", log)
            except Exception: pass
    
    # Update router with new rigs
    router = getattr(app.state, "router", None)
    if router is not None:
        router.set_rigs(app.state.rigs)
    
    return app.state.rigs

async def restart_rigctl_server(app: FastAPI, start: bool = True) -> None:
    try: await app.state.rigctl_server.stop()
    except Exception: pass
    
    # Get router if available
    router = getattr(app.state, "router", None)
    
    app.state.rigctl_server = AppRigctlServer(
        fastapi_app=app,
        config=RigctlServerConfig(host=_rigctl_bind_host(app), port=_rigctl_bind_port(app)),
        debug=app.state.debug.server,
        router=router,
    )
    if start:
        try: await app.state.rigctl_server.start()
        except Exception: pass

async def apply_config(app: FastAPI, cfg: AppConfig, restart_rigctl: bool = True):
    cfg.test_mode = getattr(app.state.config, "test_mode", False)
    app.state.config = cfg
    save_config(cfg, app.state.config_path)

    await rebuild_rigs(app, cfg)
    
    # Update router settings
    router = getattr(app.state, "router", None)
    if router is not None:
        router.poll_interval_ms = cfg.poll_interval_ms
        router.sync_enabled = cfg.sync_enabled
        router.source_index = cfg.sync_source_index
        router.rigctl_to_main_enabled = cfg.rigctl_to_main_enabled
    
    # Update sync service (legacy)
    app.state.sync_service.rigs = app.state.rigs
    app.state.sync_service.interval_ms = cfg.poll_interval_ms
    app.state.sync_service.enabled = cfg.sync_enabled
    app.state.sync_service.source_index = cfg.sync_source_index
    try: app.state.sync_service._last = (None, None, None)
    except Exception: pass
    
    await app.state.sync_service.stop()
    await app.state.sync_service.start()
    await restart_rigctl_server(app, start=restart_rigctl)

def ensure_default_profile(app: FastAPI) -> None:
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

async def bootstrap_active_profile(app: FastAPI) -> None:
    ensure_default_profile(app)
    name = str(getattr(app.state, "active_profile_name", "") or "").strip()
    if not name: return
    try:
        data = app.state.profiles.load_data(name)
        from .config import _migrate_config
        cfg = AppConfig.model_validate(_migrate_config(data))
        await apply_config(app, cfg, restart_rigctl=False)
    except Exception: pass
