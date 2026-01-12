"""
Sync engine message types.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SyncState:
    """
    Current state of the sync engine.
    
    Published to: multirig/sync/state
    """
    enabled: bool
    source_rig_id: Optional[str] = None
    follower_rig_ids: list[str] = field(default_factory=list)
    
    # What to sync
    sync_frequency: bool = True
    sync_mode: bool = True
    sync_ptt: bool = False
    
    # Current status
    last_sync_timestamp: Optional[float] = None
    error: Optional[str] = None
