from __future__ import annotations
from typing import Optional, Tuple, Sequence
from .common import RigStatus

class RigBackend:
    """Abstract base class for a rig control backend.
    
    This class defines the interface that all rig control backends (e.g. rigctld,
    direct subprocess) must implement.
    """
    async def get_frequency(self) -> Optional[int]:
        """Get the current frequency in Hz."""
        raise NotImplementedError

    async def set_frequency(self, hz: int) -> bool:
        """Set the frequency in Hz.
        
        Args:
            hz: Frequency in Hertz.
            
        Returns:
            True if successful, False otherwise.
        """
        raise NotImplementedError

    async def get_mode(self) -> Tuple[Optional[str], Optional[int]]:
        """Get the current mode and passband.
        
        Returns:
            Tuple of (mode string, passband width in Hz).
            Returns (None, None) on failure.
        """
        raise NotImplementedError

    async def set_mode(self, mode: str, passband: Optional[int] = None) -> bool:
        """Set the mode and optional passband.
        
        Args:
            mode: Mode string (e.g. 'USB', 'LSB').
            passband: Optional passband width in Hz.
            
        Returns:
            True if successful, False otherwise.
        """
        raise NotImplementedError

    async def set_vfo(self, vfo: str) -> bool:
        """Set the current VFO.
        
        Args:
            vfo: VFO string (e.g. 'VFOA', 'VFOB').
            
        Returns:
            True if successful, False otherwise.
        """
        raise NotImplementedError

    async def get_vfo(self) -> Optional[str]:
        """Get the current VFO.
        
        Returns:
            VFO string or None on failure.
        """
        raise NotImplementedError

    async def set_ptt(self, ptt: int) -> bool:
        """Set PTT (Push-to-Talk) state.
        
        Args:
            ptt: 1 for TX, 0 for RX.
            
        Returns:
            True if successful, False otherwise.
        """
        raise NotImplementedError

    async def get_ptt(self) -> Optional[int]:
        """Get PTT state.
        
        Returns:
            1 for TX, 0 for RX, or None on failure.
        """
        raise NotImplementedError

    async def get_powerstat(self) -> Optional[int]:
        """Get power status.
        
        Returns:
            1 for On, 0 for Off/Standby, or None on failure.
        """
        raise NotImplementedError

    async def chk_vfo(self) -> Optional[int]:
        """Check for VFO changes (hamlib chk_vfo).
        
        Returns:
            1 if VFO changed, 0 if not, or None on failure.
        """
        raise NotImplementedError

    async def dump_state(self) -> Sequence[str]:
        """Dump comprehensive rig state.
        
        Returns:
            List of strings representing the rig state lines.
        """
        raise NotImplementedError

    async def dump_caps(self) -> Sequence[str]:
        """Dump rig capabilities.
        
        Returns:
            List of strings representing capabilities.
        """
        raise NotImplementedError

    async def status(self) -> RigStatus:
        """Get a summary status of the rig for UI dashboard.
        
        Returns:
            RigStatus object containing connection state, freq, mode, etc.
        """
        raise NotImplementedError

    async def close(self) -> None:
        """Close the backend connection and release resources."""
        return None
