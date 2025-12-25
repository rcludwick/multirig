from __future__ import annotations
import asyncio
import contextlib
from typing import Tuple, List, Dict, Optional, Sequence
from ..protocols import HamlibParser
from .common import RigStatus, RigctlError
from .backend import RigBackend

class RigctldBackend(RigBackend):
    """Backend implementation that connects to an external rigctld instance via TCP."""
    
    def __init__(self, host: str, port: int):
        """Initialize the rigctld backend.

        Args:
            host: Hostname or IP address of rigctld.
            port: Port number of rigctld.
        """
        self.host = host
        self.port = port
        self._lock = asyncio.Lock()
        self._erp_supported = True

    async def _send_erp(self, cmd: str, timeout: float = 1.5) -> Tuple[int, List[str]]:
        """Send a command using Extended Response Protocol (ERP).
        
        Args:
            cmd: Common rigctl command string (e.g. 'f', 'm').
            timeout: Timeout in seconds for operation.
            
        Returns:
            Tuple of (RPRT code, list of response lines).
            
        Raises:
            ConnectionError: If connection to rigctld fails.
            asyncio.TimeoutError: If operation times out.
        """
        reader: asyncio.StreamReader
        writer: asyncio.StreamWriter
        
        if hasattr(self, "_debug") and self._debug:
            self._debug.add("rigctld_tx", cmd=cmd, semantic=HamlibParser.decode(cmd))

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=timeout
            )
        except Exception as e:  # noqa: BLE001
            if hasattr(self, "_debug") and self._debug:
                self._debug.add("rigctld_error", error=str(e))
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
            
            if hasattr(self, "_debug") and self._debug:
                semantic_content = f"RPRT {rprt_code}"
                if lines:
                    # Try to decode the first significant line
                    semantic_content = HamlibParser.decode(lines[0])
                self._debug.add("rigctld_rx", rprt=rprt_code, lines=lines, semantic=semantic_content)
            
            return rprt_code, lines
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _send_raw(self, cmd: str, timeout: float = 1.5) -> Tuple[int, List[str]]:
        reader: asyncio.StreamReader
        writer: asyncio.StreamWriter

        if hasattr(self, "_debug") and self._debug:
            self._debug.add("rigctld_tx", cmd=cmd, semantic=HamlibParser.decode(cmd))

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=timeout
            )
        except Exception as e:  # noqa: BLE001
            if hasattr(self, "_debug") and self._debug:
                self._debug.add("rigctld_error", error=str(e))
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

            if hasattr(self, "_debug") and self._debug:
                semantic_content = f"RPRT {rprt_code}" if rprt_code != -1 else ""
                if lines:
                    semantic_content = HamlibParser.decode(lines[0])
                self._debug.add("rigctld_rx", rprt=rprt_code, lines=lines, semantic=semantic_content)

            return rprt_code, lines
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _send(self, cmd: str, timeout: float = 1.5) -> Tuple[int, List[str]]:
        if not getattr(self, "_erp_supported", True):
            return await self._send_raw(cmd, timeout=timeout)

        code, lines = await self._send_erp(cmd, timeout=timeout)
        if code == 0:
            return code, lines

        raw_code, raw_lines = await self._send_raw(cmd, timeout=timeout)
        if raw_code == 0:
            self._erp_supported = False
            return raw_code, raw_lines
        return code, lines

    @staticmethod
    def _kv(lines: List[str]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for ln in lines:
            if ":" not in ln:
                continue
            k, v = ln.split(":", 1)
            out[k.strip()] = v.strip()
        return out

    async def get_frequency(self) -> Optional[int]:
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

    async def set_frequency(self, hz: int) -> bool:
        async with self._lock:
            code, _ = await self._send(f"F {hz}")
        return code == 0

    async def get_mode(self) -> Tuple[Optional[str], Optional[int]]:
        async with self._lock:
            code, lines = await self._send("m")
        if code != 0:
            return None, None
        kv = self._kv(lines)
        mode = kv.get("Mode")
        pb_s = kv.get("Passband")
        if mode is None and lines:
            mode = lines[0].strip() or None
        if pb_s is None and len(lines) >= 2:
            pb_s = lines[1].strip()
        pb: Optional[int] = None
        if pb_s is not None:
            try:
                pb = int(float(pb_s))
            except Exception:
                pb = None
        return mode, pb

    async def set_mode(self, mode: str, passband: Optional[int] = None) -> bool:
        cmd = f"M {mode} {passband if passband is not None else 0}".strip()
        async with self._lock:
            code, _ = await self._send(cmd)
        return code == 0

    async def set_vfo(self, vfo: str) -> bool:
        async with self._lock:
            code, _ = await self._send(f"V {vfo}")
        return code == 0

    async def get_vfo(self) -> Optional[str]:
        async with self._lock:
            code, lines = await self._send("v")
        if code != 0:
            return None
        kv = self._kv(lines)
        vfo = kv.get("VFO")
        if vfo is None and lines:
            vfo = lines[0].strip() or None
        return vfo

    async def set_ptt(self, ptt: int) -> bool:
        async with self._lock:
            code, _ = await self._send(f"T {ptt}")
        return code == 0

    async def get_ptt(self) -> Optional[int]:
        async with self._lock:
            code, lines = await self._send("t")
        if code != 0:
            raise RigctlError(code, "get_ptt")
        kv = self._kv(lines)
        val = kv.get("PTT")
        if val is None:
            if not lines:
                return None
            val = lines[0].strip()
        try:
            return int(float(val))
        except Exception:
            return None

    async def get_powerstat(self) -> Optional[int]:
        async with self._lock:
            code, lines = await self._send(r"\get_powerstat")
        if code != 0:
            return None
        kv = self._kv(lines)
        val = kv.get("Power Status")
        if val is None:
            if not lines:
                return None
            val = lines[0].strip()
        try:
            return int(float(val))
        except Exception:
            return None

    async def chk_vfo(self) -> Optional[int]:
        # chk_vfo on some hamlib versions (e.g. 4.5.5) doesn't respond to extended protocol +
        # correctly (returns empty). We fallback to raw protocol \chk_vfo.
        async with self._lock:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), timeout=1.5
                )
                try:
                    writer.write(b"\\chk_vfo\n")
                    await writer.drain()
                    data = await asyncio.wait_for(reader.readline(), timeout=1.5)
                    resp = data.decode(errors="ignore").strip()
                    if not resp:
                        return None
                    return int(resp)
                finally:
                    writer.close()
                    with contextlib.suppress(Exception):
                        await writer.wait_closed()
            except Exception:
                return None

    async def dump_state(self) -> Sequence[str]:
        async with self._lock:
            code, lines = await self._send(r"\dump_state", timeout=5.0)
        if code != 0:
            return []
        # Strip header if present (extended protocol returns "dump_state:" as first line)
        if lines and lines[0].strip() == "dump_state:":
            lines = lines[1:]
        return lines

    async def dump_caps(self) -> Sequence[str]:
        async with self._lock:
            code, lines = await self._send(r"\dump_caps", timeout=5.0)
        if code != 0:
            return []
        if lines and lines[0].strip() == "dump_caps:":
            lines = lines[1:]
        return lines

    async def status(self) -> RigStatus:
        try:
            freq = await self.get_frequency()
            mode, pb = await self.get_mode()
            return RigStatus(connected=True, frequency_hz=freq, mode=mode, passband=pb)
        except Exception as e:  # noqa: BLE001
            return RigStatus(connected=False, error=str(e))