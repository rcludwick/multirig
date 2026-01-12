"""
Rig-related message types.

These are the core messages that flow through the Zenoh bus for rig control.
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
import uuid


@dataclass
class RigState:
    """
    Current state of a rig.
    
    Published to: multirig/rig/{rig_id}/state
    """
    rig_id: str
    timestamp: float  # Unix timestamp
    connected: bool
    
    # Radio state
    frequency: Optional[int] = None      # Hz
    mode: Optional[str] = None           # USB, LSB, CW, FM, etc.
    bandwidth: Optional[int] = None      # Hz
    vfo: Optional[str] = None            # VFOA, VFOB
    ptt: Optional[bool] = None
    power_status: Optional[bool] = None
    
    # Error info
    error: Optional[str] = None
    
    @classmethod
    def disconnected(cls, rig_id: str, error: Optional[str] = None) -> 'RigState':
        """Create a disconnected state."""
        return cls(
            rig_id=rig_id,
            timestamp=datetime.now().timestamp(),
            connected=False,
            error=error
        )


@dataclass
class RigCommand:
    """
    Command to send to a rig.
    
    Published to: multirig/rig/{rig_id}/command
    """
    command_id: str              # UUID for tracking
    command_type: str            # set_frequency, set_mode, set_ptt, etc.
    source: str                  # Who sent it: api, sync, rigctl
    params: dict = field(default_factory=dict)
    
    @classmethod
    def set_frequency(cls, frequency: int, source: str = "api") -> 'RigCommand':
        """Create a set frequency command."""
        return cls(
            command_id=str(uuid.uuid4()),
            command_type="set_frequency",
            source=source,
            params={"frequency": frequency}
        )
    
    @classmethod
    def set_mode(cls, mode: str, bandwidth: Optional[int] = None, 
                 source: str = "api") -> 'RigCommand':
        """Create a set mode command."""
        params = {"mode": mode}
        if bandwidth is not None:
            params["bandwidth"] = bandwidth
        return cls(
            command_id=str(uuid.uuid4()),
            command_type="set_mode",
            source=source,
            params=params
        )
    
    @classmethod
    def set_ptt(cls, ptt: bool, source: str = "api") -> 'RigCommand':
        """Create a set PTT command."""
        return cls(
            command_id=str(uuid.uuid4()),
            command_type="set_ptt",
            source=source,
            params={"ptt": ptt}
        )
    
    @classmethod
    def set_vfo(cls, vfo: str, source: str = "api") -> 'RigCommand':
        """Create a set VFO command."""
        return cls(
            command_id=str(uuid.uuid4()),
            command_type="set_vfo",
            source=source,
            params={"vfo": vfo}
        )


@dataclass
class RigCaps:
    """
    Rig capabilities.
    
    Published to: multirig/rig/{rig_id}/caps
    """
    rig_id: str
    model_id: int
    model_name: str
    manufacturer: str
    
    # Supported modes
    modes: list[str] = field(default_factory=list)
    
    # Supported filter widths (Hz)
    filters: list[int] = field(default_factory=list)
    
    # Feature flags
    has_ptt: bool = False
    has_split: bool = False
    has_power_control: bool = False
    has_get_level: bool = False
    
    # Frequency range
    min_frequency: Optional[int] = None
    max_frequency: Optional[int] = None
