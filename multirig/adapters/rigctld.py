"""
Rigctld TCP adapter.

Connects to an existing rigctld TCP server and bridges it to Zenoh.
"""
import asyncio
import contextlib
import logging
from typing import Optional, Tuple, List
from datetime import datetime

from .base import BaseRigAdapter
from multirig.messages import RigState, RigCommand, RigCaps
from multirig.hamlib.caps import parse_dump_caps

logger = logging.getLogger(__name__)


class RigctldAdapter(BaseRigAdapter):
    """
    Adapter for rigctld TCP server.
    
    Connects to an existing rigctld process via TCP and translates
    between the rigctl protocol and Zenoh messages.
    """
    
    def __init__(self, rig_id: str, host: str, port: int, poll_interval: float = 0.1):
        """
        Initialize the rigctld adapter.
        
        Args:
            rig_id: Unique identifier for this rig
            host: Hostname or IP address of rigctld
            port: Port number of rigctld
            poll_interval: How often to poll the rig (seconds)
        """
        super().__init__(rig_id, poll_interval)
        self.host = host
        self.port = port
        self._lock = asyncio.Lock()
        self._erp_supported = True
        
        # Cached capabilities
        self._caps_dict: Optional[dict] = None
        self._modes: Optional[list] = None
    
    async def _connect(self):
        """Connect to rigctld - just verify we can reach it."""
        # Test connection
        try:
            async with self._lock:
                code, _ = await self._send("f")
            if code != 0:
                raise ConnectionError(f"rigctld not responding at {self.host}:{self.port}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to rigctld at {self.host}:{self.port}: {e}")
    
    async def _disconnect(self):
        """Disconnect from rigctld - nothing to do for TCP."""
        pass
    
    async def _poll_state(self) -> RigState:
        """Poll the rig for current state."""
        state = RigState(
            rig_id=self.rig_id,
            timestamp=datetime.now().timestamp(),
            connected=True
        )
        
        try:
            # Get frequency
            freq = await self._get_frequency()
            if freq is not None:
                state.frequency = freq
            
            # Get mode and bandwidth
            mode, bw = await self._get_mode()
            if mode is not None:
                state.mode = mode
            if bw is not None:
                state.bandwidth = bw
            
            # Get PTT
            ptt = await self._get_ptt()
            if ptt is not None:
                state.ptt = ptt
            
            # Get VFO
            vfo = await self._get_vfo()
            if vfo is not None:
                state.vfo = vfo
            
        except Exception as e:
            logger.error(f"Error polling rig {self.rig_id}: {e}")
            state.connected = False
            state.error = str(e)
        
        return state
    
    async def _execute_command(self, command: RigCommand):
        """Execute a command on the rig."""
        try:
            if command.command_type == "set_frequency":
                freq = command.params.get("frequency")
                if freq:
                    await self._set_frequency(freq)
            
            elif command.command_type == "set_mode":
                mode = command.params.get("mode")
                bw = command.params.get("bandwidth")
                if mode:
                    await self._set_mode(mode, bw)
            
            elif command.command_type == "set_ptt":
                ptt = command.params.get("ptt")
                if ptt is not None:
                    await self._set_ptt(ptt)
            
            elif command.command_type == "set_vfo":
                vfo = command.params.get("vfo")
                if vfo:
                    await self._set_vfo(vfo)
            
            else:
                logger.warning(f"Unknown command type: {command.command_type}")
        
        except Exception as e:
            logger.error(f"Error executing command on rig {self.rig_id}: {e}")
    
    async def _get_capabilities(self) -> Optional[RigCaps]:
        """Get rig capabilities."""
        try:
            async with self._lock:
                code, lines = await self._send("dump_caps")
            
            if code != 0:
                return None
            
            # Parse capabilities
            caps_dict, modes = parse_dump_caps("\n".join(lines))
            self._caps_dict = caps_dict
            self._modes = modes
            
            # Build RigCaps message
            # Note: Some fields may not be available from dump_caps
            return RigCaps(
                rig_id=self.rig_id,
                model_id=0,  # Not available from dump_caps
                model_name="Unknown",  # Not available from dump_caps
                manufacturer="Unknown",  # Not available from dump_caps
                modes=modes,
                filters=[],  # Not parsed yet
                has_ptt=caps_dict.get("ptt_get", False) and caps_dict.get("ptt_set", False),
                has_split=False,  # Not available from dump_caps
                has_power_control=False,
                has_get_level=False
            )
        
        except Exception as e:
            logger.error(f"Error getting capabilities for rig {self.rig_id}: {e}")
            return None
    
    # Rigctld protocol methods
    
    async def _send(self, cmd: str, timeout: float = 1.5) -> Tuple[int, List[str]]:
        """Send a command to rigctld."""
        if not self._erp_supported:
            return await self._send_raw(cmd, timeout=timeout)
        
        code, lines = await self._send_erp(cmd, timeout=timeout)
        if code == 0:
            return code, lines
        
        # Fall back to raw if ERP fails
        raw_code, raw_lines = await self._send_raw(cmd, timeout=timeout)
        if raw_code == 0:
            self._erp_supported = False
            return raw_code, raw_lines
        return code, lines
    
    async def _send_erp(self, cmd: str, timeout: float = 1.5) -> Tuple[int, List[str]]:
        """Send command using Extended Response Protocol."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=timeout
            )
        except Exception as e:
            raise ConnectionError(f"rigctld connect failed {self.host}:{self.port}: {e}")
        
        try:
            writer.write(("+" + cmd + "\n").encode())
            await writer.drain()
            
            lines: List[str] = []
            rprt_code: int = -1
            got_any = False
            
            while True:
                try:
                    data = await asyncio.wait_for(reader.readline(), timeout=timeout)
                except asyncio.TimeoutError:
                    break
                if not data:
                    break
                got_any = True
                s = data.decode(errors="ignore").strip("\r\n")
                if s.startswith("RPRT "):
                    try:
                        rprt_code = int(s.split()[1])
                    except Exception:
                        rprt_code = -1
                    break
                lines.append(s)
            
            if rprt_code == -1 and got_any:
                rprt_code = 0
            
            return rprt_code, lines
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
    
    async def _send_raw(self, cmd: str, timeout: float = 1.5) -> Tuple[int, List[str]]:
        """Send command without Extended Response Protocol."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=timeout
            )
        except Exception as e:
            raise ConnectionError(f"rigctld connect failed {self.host}:{self.port}: {e}")
        
        try:
            writer.write((cmd + "\n").encode())
            await writer.drain()
            
            lines: List[str] = []
            rprt_code: int = -1
            got_any = False
            
            while True:
                try:
                    data = await asyncio.wait_for(reader.readline(), timeout=timeout)
                except asyncio.TimeoutError:
                    break
                if not data:
                    break
                got_any = True
                s = data.decode(errors="ignore").strip("\r\n")
                if s.startswith("RPRT "):
                    try:
                        rprt_code = int(s.split()[1])
                    except Exception:
                        rprt_code = -1
                    break
                if s:
                    lines.append(s)
            
            if rprt_code == -1 and got_any:
                rprt_code = 0
            
            return rprt_code, lines
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
    
    def _kv(self, lines: List[str]) -> dict:
        """Parse key-value pairs from response lines."""
        kv = {}
        for line in lines:
            if ":" in line:
                key, val = line.split(":", 1)
                kv[key.strip()] = val.strip()
        return kv
    
    # Rig control methods
    
    async def _get_frequency(self) -> Optional[int]:
        """Get current frequency in Hz."""
        async with self._lock:
            code, lines = await self._send("f")
        if code != 0:
            return None
        kv = self._kv(lines)
        val = kv.get("Frequency")
        if val is None:
            if not lines:
                return None
            try:
                return int(float(lines[0]))
            except Exception:
                return None
        try:
            return int(float(val))
        except Exception:
            return None
    
    async def _set_frequency(self, hz: int) -> bool:
        """Set frequency in Hz."""
        async with self._lock:
            code, _ = await self._send(f"F {hz}")
        return code == 0
    
    async def _get_mode(self) -> Tuple[Optional[str], Optional[int]]:
        """Get current mode and bandwidth."""
        async with self._lock:
            code, lines = await self._send("m")
        if code != 0:
            return None, None
        kv = self._kv(lines)
        mode = kv.get("Mode")
        bw_str = kv.get("Passband")
        if mode is None and lines:
            mode = lines[0] if lines else None
            bw_str = lines[1] if len(lines) > 1 else None
        bw = None
        if bw_str:
            try:
                bw = int(float(bw_str))
            except Exception:
                pass
        return mode, bw
    
    async def _set_mode(self, mode: str, bandwidth: Optional[int] = None) -> bool:
        """Set mode and optionally bandwidth."""
        cmd = f"M {mode}"
        if bandwidth is not None:
            cmd += f" {bandwidth}"
        async with self._lock:
            code, _ = await self._send(cmd)
        return code == 0
    
    async def _get_ptt(self) -> Optional[bool]:
        """Get PTT status."""
        async with self._lock:
            code, lines = await self._send("t")
        if code != 0:
            return None
        kv = self._kv(lines)
        val = kv.get("PTT")
        if val is None and lines:
            val = lines[0]
        if val:
            return val == "1"
        return None
    
    async def _set_ptt(self, ptt: bool) -> bool:
        """Set PTT status."""
        async with self._lock:
            code, _ = await self._send(f"T {1 if ptt else 0}")
        return code == 0
    
    async def _get_vfo(self) -> Optional[str]:
        """Get current VFO."""
        async with self._lock:
            code, lines = await self._send("v")
        if code != 0:
            return None
        kv = self._kv(lines)
        val = kv.get("VFO")
        if val is None and lines:
            val = lines[0]
        return val
    
    async def _set_vfo(self, vfo: str) -> bool:
        """Set VFO."""
        async with self._lock:
            code, _ = await self._send(f"V {vfo}")
        return code == 0
