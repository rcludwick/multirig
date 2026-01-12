"""
Configuration store with Zenoh queryable support and rig discovery.

The ConfigStore manages:
1. Loading/saving configuration from YAML files
2. Providing queryable endpoints for config access via Zenoh
3. Discovering new rigs on the bus that aren't in the configuration
4. Publishing config change notifications
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, Set, Dict

from multirig.config import AppConfig, load_config, save_config
from multirig.messages import RigState
from multirig.messages.config import DiscoveredRig, ConfigDiscovered, ConfigChanged
from multirig.zenoh import keys
from multirig.zenoh.session import get_session, Publisher, Subscriber
from multirig.zenoh.serialization import serialize, deserialize, deserialize_dict

logger = logging.getLogger(__name__)


class ConfigStore:
    """
    Manages configuration and discovers new rigs.
    
    The Config Store:
    1. Loads/saves configuration from YAML
    2. Provides Zenoh queryable for config access
    3. Watches for new rigs on the Zenoh bus
    4. Publishes discovered rigs for the UI
    5. Publishes config change notifications
    
    Example:
        store = ConfigStore(profile_name="default")
        await store.start()
        # ... server runs ...
        await store.stop()
    """
    
    def __init__(self, profile_name: str = "default"):
        """Initialize the config store.
        
        Args:
            profile_name: Configuration profile to use
        """
        self.profile_name = profile_name
        self.config: AppConfig = AppConfig()
        
        # Known rig IDs from config
        self._configured_rig_ids: Set[str] = set()
        
        # Discovered rigs (not in config)
        self._discovered_rigs: Dict[str, DiscoveredRig] = {}
        
        # Zenoh
        self._config_queryable = None
        self._state_subscriber: Optional[Subscriber] = None
        self._discovered_publisher: Optional[Publisher] = None
        self._changed_publisher: Optional[Publisher] = None
    
    def load_config(self):
        """Load configuration from YAML file."""
        self.config = load_config(self.profile_name)
        self._configured_rig_ids = {rig.rig_id for rig in self.config.rigs}
        logger.info(f"Loaded config with {len(self.config.rigs)} rigs: {self._configured_rig_ids}")
    
    def save_config(self):
        """Save configuration to YAML file."""
        if self.config.test_mode:
            logger.debug("Skipping config save in test mode")
            return
        save_config(self.config, self.profile_name)
        logger.info(f"Saved config with {len(self.config.rigs)} rigs")
    
    def add_rig(self, rig_config: dict) -> bool:
        """Add a rig to the configuration.
        
        Called when user clicks "Add" on a discovered rig.
        
        Args:
            rig_config: Rig configuration dictionary
            
        Returns:
            True if rig was added, False if it already exists
        """
        from multirig.config import RigConfig
        
        rig = RigConfig(**rig_config)
        
        # Check if already exists
        if rig.rig_id in self._configured_rig_ids:
            logger.warning(f"Rig {rig.rig_id} already exists in config")
            return False
        
        self.config.rigs.append(rig)
        self._configured_rig_ids.add(rig.rig_id)
        
        # Remove from discovered
        if rig.rig_id in self._discovered_rigs:
            del self._discovered_rigs[rig.rig_id]
            self._publish_discovered()
        
        # Save and notify
        self.save_config()
        self._publish_changed("rig_added", rig.rig_id)
        
        logger.info(f"Added rig {rig.rig_id} to config")
        return True
    
    def remove_rig(self, rig_id: str) -> bool:
        """Remove a rig from the configuration.
        
        Args:
            rig_id: Rig ID to remove
            
        Returns:
            True if rig was removed, False if not found
        """
        # Find and remove rig
        for i, rig in enumerate(self.config.rigs):
            if rig.rig_id == rig_id:
                self.config.rigs.pop(i)
                self._configured_rig_ids.discard(rig_id)
                
                # Save and notify
                self.save_config()
                self._publish_changed("rig_removed", rig_id)
                
                logger.info(f"Removed rig {rig_id} from config")
                return True
        
        logger.warning(f"Rig {rig_id} not found in config")
        return False
    
    def update_rig(self, rig_id: str, updates: dict) -> bool:
        """Update a rig's configuration.
        
        Args:
            rig_id: Rig ID to update
            updates: Dictionary of field updates
            
        Returns:
            True if rig was updated, False if not found
        """
        # Find rig
        for rig in self.config.rigs:
            if rig.rig_id == rig_id:
                # Apply updates
                for key, value in updates.items():
                    if hasattr(rig, key):
                        setattr(rig, key, value)
                
                # Save and notify
                self.save_config()
                self._publish_changed("rig_updated", rig_id)
                
                logger.info(f"Updated rig {rig_id}")
                return True
        
        logger.warning(f"Rig {rig_id} not found in config")
        return False
    
    def update_sync(self, updates: dict) -> bool:
        """Update sync configuration.
        
        Args:
            updates: Dictionary of sync config updates
            
        Returns:
            True if sync was updated
        """
        # Apply updates
        for key, value in updates.items():
            if hasattr(self.config.sync, key):
                setattr(self.config.sync, key, value)
        
        # Save and notify
        self.save_config()
        self._publish_changed("sync_updated")
        
        logger.info("Updated sync config")
        return True
    
    async def start(self):
        """Start the config store and discovery."""
        logger.info(f"Starting config store (profile: {self.profile_name})")
        
        self.load_config()
        
        # Set up Zenoh queryable for config
        session = get_session()
        self._config_queryable = session.declare_queryable(keys.CONFIG, self._handle_config_query)
        
        # Publishers
        self._discovered_publisher = Publisher(keys.CONFIG_DISCOVERED)
        self._changed_publisher = Publisher(keys.CONFIG_CHANGED)
        
        # Subscribe to all rig states for discovery
        self._state_subscriber = Subscriber(
            keys.RIG_STATE_ALL,
            self._on_rig_state
        )
        self._state_subscriber.start()
        
        # Publish initial discovered list (empty)
        self._publish_discovered()
        
        logger.info("Config store started")
    
    async def stop(self):
        """Stop the config store."""
        logger.info("Stopping config store")
        
        if self._config_queryable:
            self._config_queryable.undeclare()
        if self._state_subscriber:
            self._state_subscriber.stop()
        if self._discovered_publisher:
            self._discovered_publisher.close()
        if self._changed_publisher:
            self._changed_publisher.close()
    
    def _handle_config_query(self, query):
        """Handle Zenoh queries for configuration.
        
        Args:
            query: Zenoh query object
        """
        try:
            # Return current config as JSON
            config_dict = self.config.model_dump(exclude={"test_mode"})
            query.reply(keys.CONFIG, serialize(config_dict))
        except Exception as e:
            logger.error(f"Error handling config query: {e}")
    
    async def _on_rig_state(self, sample):
        """Handle rig state - check if it's a new discovery.
        
        Args:
            sample: Zenoh sample containing rig state
        """
        try:
            state = deserialize(sample.payload.to_bytes(), RigState)
            rig_id = state.rig_id
            
            # Skip if already configured
            if rig_id in self._configured_rig_ids:
                return
            
            now = datetime.now().timestamp()
            
            # Update or create discovered rig entry
            if rig_id in self._discovered_rigs:
                # Update existing
                self._discovered_rigs[rig_id].last_seen = now
                self._discovered_rigs[rig_id].connected = state.connected
            else:
                # New discovery!
                logger.info(f"Discovered new rig: {rig_id}")
                self._discovered_rigs[rig_id] = DiscoveredRig(
                    rig_id=rig_id,
                    first_seen=now,
                    last_seen=now,
                    connected=state.connected,
                    model_name=None  # Will be updated from caps
                )
                self._publish_discovered()
                
        except Exception as e:
            logger.error(f"Error in discovery: {e}")
    
    def _publish_discovered(self):
        """Publish the current discovered rigs list."""
        if self._discovered_publisher:
            msg = ConfigDiscovered(
                discovered_rigs=list(self._discovered_rigs.values()),
                timestamp=datetime.now().timestamp()
            )
            self._discovered_publisher.publish(msg)
    
    def _publish_changed(self, change_type: str, rig_id: Optional[str] = None):
        """Publish a config change notification.
        
        Args:
            change_type: Type of change (rig_added, rig_removed, rig_updated, sync_updated)
            rig_id: Rig ID if applicable
        """
        if self._changed_publisher:
            msg = ConfigChanged(
                change_type=change_type,
                rig_id=rig_id,
                timestamp=datetime.now().timestamp()
            )
            self._changed_publisher.publish(msg)
