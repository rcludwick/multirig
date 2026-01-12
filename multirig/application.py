"""
Application manager for MultiRig with Zenoh.

Orchestrates the lifecycle of all application components:
- Zenoh session
- Configuration store
- Rig adapters
- Sync engine
- Rigctl server
- API gateway
"""
import asyncio
import logging
from typing import Dict, List, Optional

from multirig.config import AppConfig, RigConfig, load_config
from multirig.adapters.base import BaseRigAdapter
from multirig.adapters.rigctld import RigctldAdapter
from multirig.adapters.managed import ManagedRigAdapter
from multirig.engines.sync import SyncEngine
from multirig.engines.config_store import ConfigStore
from multirig.rigctl_server import RigctlServer, RigctlServerConfig
from multirig.zenoh.session import init_session, close_session

logger = logging.getLogger(__name__)


class ApplicationManager:
    """
    Manages the lifecycle of all MultiRig components.
    
    This class coordinates:
    1. Zenoh session initialization
    2. Configuration loading
    3. Adapter creation and management
    4. Sync engine
    5. Config store
    6. Rigctl server
    
    Example:
        app_manager = ApplicationManager(profile_name="default")
        await app_manager.start()
        # ... application runs ...
        await app_manager.stop()
    """
    
    def __init__(self, profile_name: str = "default"):
        """Initialize the application manager.
        
        Args:
            profile_name: Configuration profile to use
        """
        self.profile_name = profile_name
        self.config: Optional[AppConfig] = None
        
        # Components
        self.adapters: Dict[str, BaseRigAdapter] = {}
        self.sync_engine: Optional[SyncEngine] = None
        self.config_store: Optional[ConfigStore] = None
        self.rigctl_server: Optional[RigctlServer] = None
        
        self._started = False
    
    async def start(self):
        """Start all application components."""
        if self._started:
            logger.warning("Application already started")
            return
        
        logger.info("=" * 60)
        logger.info("Starting MultiRig Application")
        logger.info("=" * 60)
        
        # 1. Initialize Zenoh session
        logger.info("Initializing Zenoh session...")
        await init_session()
        logger.info("✓ Zenoh session initialized")
        
        # 2. Load configuration
        logger.info(f"Loading configuration (profile: {self.profile_name})...")
        self.config = load_config(self.profile_name)
        logger.info(f"✓ Configuration loaded: {len(self.config.rigs)} rigs configured")
        
        # 3. Start config store
        logger.info("Starting config store...")
        self.config_store = ConfigStore(profile_name=self.profile_name)
        await self.config_store.start()
        logger.info("✓ Config store started")
        
        # 4. Create and start rig adapters
        logger.info("Creating rig adapters...")
        for rig_config in self.config.rigs:
            if not rig_config.enabled:
                logger.info(f"  - Skipping disabled rig: {rig_config.rig_id}")
                continue
            
            adapter = self._create_adapter(rig_config)
            self.adapters[rig_config.rig_id] = adapter
            
            logger.info(f"  - Starting {rig_config.rig_id} ({rig_config.connection_type})...")
            await adapter.start()
            logger.info(f"    ✓ {rig_config.rig_id} started")
        
        logger.info(f"✓ Created and started {len(self.adapters)} rig adapters")
        
        # 5. Start sync engine
        if self.config.sync.enabled:
            logger.info("Starting sync engine...")
            self.sync_engine = SyncEngine()
            self.sync_engine.enabled = True
            self.sync_engine.source_rig_id = self.config.sync.source_rig_id
            self.sync_engine.follower_rig_ids = self.config.sync.follower_rig_ids
            self.sync_engine.sync_frequency = self.config.sync.sync_frequency
            self.sync_engine.sync_mode = self.config.sync.sync_mode
            self.sync_engine.sync_ptt = self.config.sync.sync_ptt
            await self.sync_engine.start()
            logger.info(f"✓ Sync engine started (source: {self.config.sync.source_rig_id})")
        else:
            logger.info("Sync engine disabled in config")
        
        # 6. Start rigctl server
        if self.config.rigctl_server.enabled:
            logger.info("Starting rigctl server...")
            rigctl_config = RigctlServerConfig(
                host=self.config.rigctl_server.host,
                port=self.config.rigctl_server.port,
                target_rig_id=self.config.rigctl_server.target_rig_id
            )
            self.rigctl_server = RigctlServer(rigctl_config)
            await self.rigctl_server.start()
            logger.info(f"✓ Rigctl server started on {rigctl_config.host}:{rigctl_config.port}")
        else:
            logger.info("Rigctl server disabled in config")
        
        self._started = True
        
        logger.info("=" * 60)
        logger.info("MultiRig Application Started Successfully")
        logger.info("=" * 60)
        logger.info("")
        logger.info("Components:")
        logger.info(f"  - Rig Adapters: {len(self.adapters)}")
        logger.info(f"  - Sync Engine: {'enabled' if self.sync_engine else 'disabled'}")
        logger.info(f"  - Rigctl Server: {'enabled' if self.rigctl_server else 'disabled'}")
        logger.info(f"  - Config Store: enabled")
        logger.info("")
    
    async def stop(self):
        """Stop all application components."""
        if not self._started:
            return
        
        logger.info("=" * 60)
        logger.info("Stopping MultiRig Application")
        logger.info("=" * 60)
        
        # Stop rigctl server
        if self.rigctl_server:
            logger.info("Stopping rigctl server...")
            await self.rigctl_server.stop()
            logger.info("✓ Rigctl server stopped")
        
        # Stop sync engine
        if self.sync_engine:
            logger.info("Stopping sync engine...")
            await self.sync_engine.stop()
            logger.info("✓ Sync engine stopped")
        
        # Stop all adapters
        if self.adapters:
            logger.info("Stopping rig adapters...")
            for rig_id, adapter in self.adapters.items():
                logger.info(f"  - Stopping {rig_id}...")
                await adapter.stop()
                logger.info(f"    ✓ {rig_id} stopped")
            logger.info("✓ All rig adapters stopped")
        
        # Stop config store
        if self.config_store:
            logger.info("Stopping config store...")
            await self.config_store.stop()
            logger.info("✓ Config store stopped")
        
        # Close Zenoh session
        logger.info("Closing Zenoh session...")
        await close_session()
        logger.info("✓ Zenoh session closed")
        
        self._started = False
        
        logger.info("=" * 60)
        logger.info("MultiRig Application Stopped")
        logger.info("=" * 60)
    
    def _create_adapter(self, rig_config: RigConfig) -> BaseRigAdapter:
        """Create a rig adapter based on configuration.
        
        Args:
            rig_config: Rig configuration
            
        Returns:
            Appropriate adapter instance
        """
        if rig_config.connection_type == "rigctld":
            # Connect to existing rigctld
            adapter = RigctldAdapter(
                rig_id=rig_config.rig_id,
                host=rig_config.host,
                port=rig_config.port,
                poll_interval=rig_config.poll_interval_ms / 1000.0
            )
        elif rig_config.connection_type == "managed":
            # Spawn and manage rigctld subprocess
            adapter = ManagedRigAdapter(
                rig_id=rig_config.rig_id,
                model_id=rig_config.model_id,
                device=rig_config.device,
                baud=rig_config.baud,
                poll_interval=rig_config.poll_interval_ms / 1000.0
            )
        else:
            raise ValueError(f"Unknown connection type: {rig_config.connection_type}")
        
        # Configure safety settings
        adapter.set_safety_config(
            allow_out_of_band=rig_config.allow_out_of_band,
            band_presets=rig_config.band_presets
        )
        
        return adapter
    
    async def reload_config(self):
        """Reload configuration and restart components as needed.
        
        This is useful for responding to config changes without
        restarting the entire application.
        """
        logger.info("Reloading configuration...")
        
        # Load new config
        new_config = load_config(self.profile_name)
        
        # Compare with current config and determine what needs to change
        # For now, do a full restart of affected components
        
        # Stop adapters for rigs that were removed or changed
        for rig_id in list(self.adapters.keys()):
            # Check if rig still exists in new config
            rig_found = any(r.rig_id == rig_id for r in new_config.rigs)
            if not rig_found:
                logger.info(f"Stopping removed rig: {rig_id}")
                await self.adapters[rig_id].stop()
                del self.adapters[rig_id]
        
        # Start adapters for new rigs
        for rig_config in new_config.rigs:
            if not rig_config.enabled:
                continue
            
            if rig_config.rig_id not in self.adapters:
                logger.info(f"Starting new rig: {rig_config.rig_id}")
                adapter = self._create_adapter(rig_config)
                self.adapters[rig_config.rig_id] = adapter
                await adapter.start()
        
        # Update sync engine if needed
        if self.sync_engine and new_config.sync.enabled:
            if (self.config.sync.source_rig_id != new_config.sync.source_rig_id or
                self.config.sync.follower_rig_ids != new_config.sync.follower_rig_ids):
                logger.info("Updating sync engine configuration...")
                self.sync_engine.set_source(new_config.sync.source_rig_id)
                # Update followers
                for rig_id in new_config.sync.follower_rig_ids:
                    if rig_id not in self.sync_engine.follower_rig_ids:
                        self.sync_engine.add_follower(rig_id)
                for rig_id in self.sync_engine.follower_rig_ids:
                    if rig_id not in new_config.sync.follower_rig_ids:
                        self.sync_engine.remove_follower(rig_id)
        
        self.config = new_config
        logger.info("✓ Configuration reloaded")


# Global application instance
_app_manager: Optional[ApplicationManager] = None


def get_app_manager() -> Optional[ApplicationManager]:
    """Get the global application manager instance.
    
    Returns:
        Application manager instance, or None if not started
    """
    return _app_manager


async def start_application(profile_name: str = "default") -> ApplicationManager:
    """Start the application with the given profile.
    
    Args:
        profile_name: Configuration profile to use
        
    Returns:
        Started application manager instance
    """
    global _app_manager
    
    if _app_manager is not None:
        logger.warning("Application already started")
        return _app_manager
    
    _app_manager = ApplicationManager(profile_name=profile_name)
    await _app_manager.start()
    return _app_manager


async def stop_application():
    """Stop the application."""
    global _app_manager
    
    if _app_manager is None:
        return
    
    await _app_manager.stop()
    _app_manager = None
