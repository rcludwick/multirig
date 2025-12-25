from __future__ import annotations
from typing import Optional, Tuple, Dict, Any, List, Sequence
from ..config import RigConfig
from .common import RigStatus, parse_dump_caps
from .backend import RigBackend
from .tcp import RigctldBackend
from .process import RigctlProcessBackend
from .managed import RigctlManagedBackend

class RigClient:
    """High-level client for controlling a rig.
    
    This class wraps a RigBackend (either TCP or process-based) and adds logic
    for configuration management, caching capabilities, and enforcing constraints
    like band limits.
    """
    
    def __init__(self, cfg: RigConfig):
        self.cfg = cfg
        self._backend: RigBackend = self._make_backend(cfg)
        self._last_error: Optional[str] = None
        self._caps: Optional[Dict[str, bool]] = None
        self._modes: Optional[List[str]] = None
        self._caps_detected: bool = False
        self._last_connected_state: bool = False
        self._check_caps_call_count: int = 0

    def _make_backend(self, cfg: RigConfig) -> RigBackend:
        if cfg.managed:
             if cfg.model_id is None:
                 return RigctlProcessBackend(model_id=0, device="/dev/null") # dummy
             
             device = cfg.device
             if not device and cfg.model_id in (1, 6):
                 device = "/dev/null"

             if not device:
                 return RigctlProcessBackend(model_id=0, device="/dev/null") # dummy

             return RigctlManagedBackend(
                model_id=cfg.model_id,
                device=device,
                baud=cfg.baud,
                serial_opts=cfg.serial_opts,
                extra_args=cfg.extra_args,
             )

        if cfg.connection_type == "hamlib":
            if cfg.model_id is None or cfg.device is None:
                # Misconfigured; create a dummy backend that will error on use
                return RigctlProcessBackend(model_id=0, device="/dev/null")
            return RigctlProcessBackend(
                model_id=cfg.model_id,
                device=cfg.device,
                baud=cfg.baud,
                serial_opts=cfg.serial_opts,
                extra_args=cfg.extra_args,
            )
        # default rigctld TCP
        return RigctldBackend(cfg.host, cfg.port)

    def update_config(self, cfg: RigConfig) -> None:
        """Update the rig configuration and recreate the backend.
        
        Args:
            cfg: New RigConfig object.
        """
        self.cfg = cfg
        self._backend = self._make_backend(cfg)

    async def get_frequency(self) -> Optional[int]:
        """Get current frequency.
        
        Returns:
            Frequency in Hz or None.
        """
        return await self._backend.get_frequency()

    async def set_frequency(self, hz: int) -> bool:
        """Set frequency, respecting band limits configuration.
        
        Args:
            hz: Target frequency in Hz.
            
        Returns:
            True if successful. Returns False if frequency is out of allowed bands
            or backend fails.
        """
        allow_oob = bool(getattr(self.cfg, "allow_out_of_band", False))
        if not allow_oob:
            presets = getattr(self.cfg, "band_presets", [])
            in_any = False
            has_any_ranges = False
            for p in presets:
                try:
                    if getattr(p, "enabled", True) is False:
                        continue
                    lo = getattr(p, "lower_hz", None)
                    hi = getattr(p, "upper_hz", None)
                    if lo is None or hi is None:
                        # Band preset without explicit ranges - allow any frequency
                        in_any = True
                        break
                    has_any_ranges = True
                    if hz >= int(lo) and hz <= int(hi):
                        in_any = True
                        break
                except Exception:
                    continue
            # Only reject if we have explicit ranges and frequency doesn't match any
            if has_any_ranges and not in_any:
                self._last_error = "Frequency out of configured band ranges"
                return False
        
        # If checks pass, try to set frequency on backend
        res = await self._backend.set_frequency(hz)
        if not res:
            self._last_error = "Failed to set frequency on rig backend"
            return False
        
        # Don't clear _last_error here - let caller manage error state
        return True

    async def get_mode(self) -> Tuple[Optional[str], Optional[int]]:
        """Get current mode.
        
        Returns:
            Tuple of (mode, passband).
        """
        return await self._backend.get_mode()

    async def set_mode(self, mode: str, passband: Optional[int] = None) -> bool:
        """Set mode.
        
        Args:
            mode: Mode string.
            passband: Optional passband.
            
        Returns:
            True if successful.
        """
        # TODO: Add mode-specific validation if needed, similar to frequency
        res = await self._backend.set_mode(mode, passband)
        if not res:
            self._last_error = "Failed to set mode on rig backend"
            return False
        # Don't clear _last_error here - let caller manage error state
        return True

    async def set_vfo(self, vfo: str) -> bool:
        """Set VFO.
        
        Args:
            vfo: VFO name.
            
        Returns:
            True if successful.
        """
        res = await self._backend.set_vfo(vfo)
        if not res:
            self._last_error = "Failed to set VFO on rig backend"
            return False
        # Don't clear _last_error here - let caller manage error state
        return True

    async def get_vfo(self) -> Optional[str]:
        """Get VFO.
        
        Returns:
            VFO name or None.
        """
        return await self._backend.get_vfo()

    async def set_ptt(self, ptt: int) -> bool:
        """Set PTT.
        
        Args:
            ptt: 1=On, 0=Off.
            
        Returns:
            True if successful.
        """
        res = await self._backend.set_ptt(ptt)
        if not res:
            self._last_error = "Failed to set PTT on rig backend"
            return False
        # Don't clear _last_error here - let caller manage error state
        return True

    async def get_ptt(self) -> Optional[int]:
        """Get PTT.
        
        Returns:
            PTT state or None.
        """
        return await self._backend.get_ptt()

    async def get_powerstat(self) -> Optional[int]:
        """Get power status.
        
        Returns:
            Power status or None.
        """
        return await self._backend.get_powerstat()

    async def chk_vfo(self) -> Optional[int]:
        """Check VFO changes.
        
        Returns:
            1 if changed, 0 if not, None if error.
        """
        return await self._backend.chk_vfo()

    async def dump_state(self) -> Sequence[str]:
        """Dump state.
        
        Returns:
            List of state lines.
        """
        return await self._backend.dump_state()

    async def dump_caps(self) -> Sequence[str]:
        """Dump caps.

        Returns:
             List of caps lines.
        """
        return await self._backend.dump_caps()

    async def refresh_caps(self) -> Dict[str, Any]:
        """Refresh rig capabilities by running dump_caps and caching results.
        
        Returns:
            Dict with 'caps' (capabilities dict), 'modes' (list of mode strings),
            and 'raw' (raw dump_caps output lines).
        """
        lines = await self.dump_caps()
        text = "\n".join([ln for ln in lines if ln is not None])
        caps, modes = parse_dump_caps(text)
        self._caps = caps or None
        self._modes = modes or None
        return {
            "caps": self._caps or {},
            "modes": self._modes or [],
            "raw": list(lines) if lines is not None else [],
        }

    async def check_and_refresh_caps(self) -> None:
        """Check connection status and automatically refresh capabilities on first connection.
        
        This method should be called periodically (e.g., from a polling loop) to detect
        when a rig connects and automatically run dump_caps to detect its capabilities.
        Capabilities are only refreshed once per connection to avoid overhead.
        """
        self._check_caps_call_count += 1
        try:
            status = await self.status()
            current_connected = status.connected
            
            # Detect disconnection - reset the caps_detected flag
            if self._last_connected_state and not current_connected:
                self._caps_detected = False
            
            # Detect first connection or reconnection
            if current_connected and not self._caps_detected:
                try:
                    await self.refresh_caps()
                    self._caps_detected = True
                except Exception:
                    # Mark as detected even on failure to avoid repeated attempts
                    self._caps_detected = True
            
            self._last_connected_state = current_connected
        except Exception:
            pass

    async def status(self) -> RigStatus:
        return await self._backend.status()

    async def close(self) -> None:
        if self._backend:
            await self._backend.close()

    async def safe_status(self) -> Dict[str, Any]:
        """Get JSON-safe rig status including capabilities and band presets.
        
        Returns:
            Dict with rig status, configuration, and cached capabilities.
        """
        s = await self.status()
        data: Dict[str, Any] = {
            "name": self.cfg.name,
            "enabled": getattr(self.cfg, "enabled", True),
            "connected": s.connected,
            "frequency_hz": s.frequency_hz,
            "mode": s.mode,
            "passband": s.passband,
            "error": s.error,
            "last_error": self._last_error,
            "connection_type": self.cfg.connection_type,
            "follow_main": getattr(self.cfg, "follow_main", True),
            "model_id": self.cfg.model_id,
            "caps": self._caps,
            "modes": self._modes,
            "caps_detected": self._caps_detected,
            "band_presets": [
                {
                    "label": p.label,
                    "frequency_hz": p.frequency_hz,
                    "enabled": p.enabled,
                    "lower_hz": p.lower_hz,
                    "upper_hz": p.upper_hz,
                }
                for p in self.cfg.band_presets
            ],
            "allow_out_of_band": self.cfg.allow_out_of_band,
            "check_caps_call_count": self._check_caps_call_count,
            "color": getattr(self.cfg, "color", "#a4c356"),
            "inverted": getattr(self.cfg, "inverted", False),
        }
        if self.cfg.connection_type == "rigctld":
            data.update({"host": self.cfg.host, "port": self.cfg.port})
        else:
            data.update({"device": self.cfg.device, "baud": self.cfg.baud})
        return data
