"""
Configuration-related message types.

These messages support the hybrid discovery + config-driven approach for
managing rigs in the system.
"""
from pydantic import BaseModel, Field
from typing import Optional


class DiscoveredRig(BaseModel):
    """Information about a rig discovered on the bus but not in config.
    
    Published to: multirig/config/discovered
    """
    rig_id: str
    first_seen: float  # Unix timestamp
    last_seen: float   # Unix timestamp
    connected: bool
    model_name: Optional[str] = None  # From caps if available


class ConfigDiscovered(BaseModel):
    """List of rigs discovered on the bus but not in config.
    
    Published to: multirig/config/discovered
    
    The frontend subscribes to this to show an "Available Rigs" section
    with rigs that can be added to the configuration.
    """
    discovered_rigs: list[DiscoveredRig] = Field(default_factory=list)
    timestamp: float = 0.0


class ConfigChanged(BaseModel):
    """Notification that configuration has changed.
    
    Published to: multirig/config/changed
    
    Components subscribe to this to react to config changes:
    - Sync Engine: updates follower list when rigs added/removed
    - API Gateway: refreshes state for frontend
    - Rig Adapters: restart when their config changes
    """
    change_type: str  # "rig_added", "rig_removed", "rig_updated", "sync_updated"
    rig_id: Optional[str] = None
    timestamp: float = 0.0
