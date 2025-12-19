from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, List, Sequence
import contextlib
import shlex
import asyncio.subprocess as asp

from .config import RigConfig
from .protocols import HamlibParser


class RigctlError(Exception):
    """Exception raised when a rigctl command returns an error code."""
    def __init__(self, code: int, message: str = ""):
        self.code = code
        self.message = message
        super().__init__(f"RPRT {code}: {message}" if message else f"RPRT {code}")


@dataclass
class RigStatus:
    connected: bool
    frequency_hz: Optional[int] = None
    mode: Optional[str] = None
    passband: Optional[int] = None
    error: Optional[str] = None


class RigBackend:
    async def get_frequency(self) -> Optional[int]:
        raise NotImplementedError

    async def set_frequency(self, hz: int) -> bool:
        raise NotImplementedError

    async def get_mode(self) -> Tuple[Optional[str], Optional[int]]:
        raise NotImplementedError

    async def set_mode(self, mode: str, passband: Optional[int] = None) -> bool:
        raise NotImplementedError

    async def set_vfo(self, vfo: str) -> bool:
        raise NotImplementedError

    async def get_vfo(self) -> Optional[str]:
        raise NotImplementedError

    async def set_ptt(self, ptt: int) -> bool:
        raise NotImplementedError

    async def get_ptt(self) -> Optional[int]:
        raise NotImplementedError

    async def get_powerstat(self) -> Optional[int]:
        raise NotImplementedError

    async def chk_vfo(self) -> Optional[int]:
        raise NotImplementedError

    async def dump_state(self) -> Sequence[str]:
        raise NotImplementedError

    async def dump_caps(self) -> Sequence[str]:
        raise NotImplementedError

    async def status(self) -> RigStatus:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class RigctldBackend(RigBackend):
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._lock = asyncio.Lock()
        self._erp_supported = True

    async def _send_erp(self, cmd: str, timeout: float = 1.5) -> Tuple[int, List[str]]:
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
            code, lines = await self._send("\\get_powerstat")
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
        # chk_vfo on some hamlib versions (e.g. 4.5.5) doesn't respond to extended protocol +\chk_vfo
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
            code, lines = await self._send("\\dump_state", timeout=5.0)
        if code != 0:
            return []
        # Strip header if present (extended protocol returns "dump_state:" as first line)
        if lines and lines[0].strip() == "dump_state:":
            lines = lines[1:]
        return lines

    async def dump_caps(self) -> Sequence[str]:
        async with self._lock:
            code, lines = await self._send("\\dump_caps", timeout=5.0)
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


class RigctlProcessBackend(RigBackend):
    """Direct hamlib control using a persistent 'rigctl' subprocess in interactive mode."""

    def __init__(self, model_id: int, device: str, baud: Optional[int] = None,
                 serial_opts: Optional[str] = None, extra_args: Optional[str] = None):
        self.model_id = model_id
        self.device = device
        self.baud = baud
        self.serial_opts = serial_opts
        self.extra_args = extra_args
        self._proc: Optional[asp.Process] = None
        self._lock = asyncio.Lock()

    def _build_cmd(self) -> list[str]:
        cmd = ["rigctl", "-m", str(self.model_id), "-r", self.device]
        if self.baud:
            cmd += ["-s", str(self.baud)]
        if self.serial_opts:
            # split safely but allow user to pass a full string
            cmd += shlex.split(self.serial_opts)
        if self.extra_args:
            cmd += shlex.split(self.extra_args)
        # interactive mode reads commands from stdin
        return cmd

    async def _ensure_proc(self) -> asp.Process:
        if self._proc and self._proc.returncode is None:
            return self._proc
        # Start process
        self._proc = await asp.create_subprocess_exec(
            *self._build_cmd(),
            stdin=asp.PIPE,
            stdout=asp.PIPE,
            stderr=asp.PIPE,
        )
        return self._proc

    async def _send_n(self, cmd: str, n: int, timeout: float = 1.8) -> List[str]:
        proc = await self._ensure_proc()
        assert proc.stdin and proc.stdout

        async def _do_send(p: asp.Process) -> List[str]:
            assert p.stdin and p.stdout
            p.stdin.write((cmd + "\n").encode())
            await p.stdin.drain()
            out: List[str] = []
            for _ in range(max(1, n)):
                data = await asyncio.wait_for(p.stdout.readline(), timeout=timeout)
                out.append(data.decode(errors="ignore").strip())
            return out

        try:
            return await _do_send(proc)
        except Exception:
            await self.close()
            proc = await self._ensure_proc()
            return await _do_send(proc)

    async def _send(self, cmd: str, timeout: float = 1.8) -> str:
        proc = await self._ensure_proc()
        assert proc.stdin and proc.stdout
        try:
            proc.stdin.write((cmd + "\n").encode())
            await proc.stdin.drain()
            data = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
            return data.decode().strip()
        except Exception:
            # Attempt one restart
            await self.close()
            proc = await self._ensure_proc()
            assert proc.stdin and proc.stdout
            proc.stdin.write((cmd + "\n").encode())
            await proc.stdin.drain()
            data = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
            return data.decode().strip()

    async def get_frequency(self) -> Optional[int]:
        async with self._lock:
            resp = await self._send("f")
        try:
            return int(float(resp))
        except Exception:
            return None

    async def set_frequency(self, hz: int) -> bool:
        async with self._lock:
            resp = await self._send(f"F {hz}")
        return resp == "RPRT 0" or resp == ""

    async def get_mode(self) -> Tuple[Optional[str], Optional[int]]:
        async with self._lock:
            lines = await self._send_n("m", 2)
        if not lines:
            return None, None
        first = (lines[0] or "").strip()
        if not first or first.startswith("RPRT "):
            return None, None
        parts = first.split()
        if len(parts) >= 2:
            mode = parts[0]
            try:
                pb = int(float(parts[1]))
            except Exception:
                pb = None
            return mode, pb

        mode = parts[0]
        pb: Optional[int] = None
        if len(lines) >= 2:
            second = (lines[1] or "").strip()
            if second and not second.startswith("RPRT "):
                try:
                    pb = int(float(second))
                except Exception:
                    pb = None
        return mode, pb

    async def set_mode(self, mode: str, passband: Optional[int] = None) -> bool:
        cmd = f"M {mode} {passband if passband is not None else 0}".strip()
        async with self._lock:
            resp = await self._send(cmd)
        return resp == "RPRT 0" or resp == ""

    async def set_vfo(self, vfo: str) -> bool:
        async with self._lock:
            resp = await self._send(f"V {vfo}")
        return resp == "RPRT 0" or resp == ""

    async def get_vfo(self) -> Optional[str]:
        async with self._lock:
            resp = await self._send("v")
        v = resp.strip()
        if not v or v.startswith("RPRT "):
            return None
        return v

    async def set_ptt(self, ptt: int) -> bool:
        async with self._lock:
            resp = await self._send(f"T {ptt}")
        return resp == "RPRT 0" or resp == ""

    async def get_ptt(self) -> Optional[int]:
        async with self._lock:
            resp = await self._send("t")
        v = resp.strip()
        if not v or v.startswith("RPRT "):
            return None
        try:
            return int(float(v))
        except Exception:
            return None

    async def get_powerstat(self) -> Optional[int]:
        async with self._lock:
            resp = await self._send("\\get_powerstat")
        v = resp.strip()
        if not v or v.startswith("RPRT "):
            return None
        try:
            return int(float(v))
        except Exception:
            return None

    async def chk_vfo(self) -> Optional[int]:
        async with self._lock:
            resp = await self._send("\\chk_vfo")
        v = resp.strip()
        if not v or v.startswith("RPRT "):
            return None
        try:
            return int(float(v))
        except Exception:
            return None

    async def dump_state(self) -> Sequence[str]:
        # dump_state returns many lines, ending with RPRT? 
        # In interactive mode, we send \dump_state
        # It returns many lines.
        # We need to read until we think it's done.
        # Standard rigctl dump_state ends with a specific pattern? 
        # Or just read until no more data?
        # RigctlProcessBackend._send only reads one line.
        # We need a new method for multi-line read that doesn't rely on count.
        # But dump_state structure is fixed?
        # For now, let's implement a specific reader for dump_state or just use a large N?
        # Using _send_n might work if we know N. But N varies.
        
        # Let's defer implementation slightly or use a large timeout read loop.
        # Actually, for dump_state, we can probably just read until the output stops?
        # But that's slow.
        # The last line of dump_state is usually checking for RPRT if extended?
        # But we are using interactive mode without extended responses usually?
        # Wait, RigctlProcessBackend sends commands directly.
        # dump_state output ends.
        
        # Let's implement a read_until_timeout or something.
        # Or maybe just read a large chunk.
        
        proc = await self._ensure_proc()
        assert proc.stdin and proc.stdout
        
        cmd = "\\dump_state"
        
        async with self._lock:
             try:
                proc.stdin.write((cmd + "\n").encode())
                await proc.stdin.drain()
                
                lines = []
                # It's hard to know when dump_state ends without parsing it or waiting for timeout.
                # However, rigctl -m 1 dump_state ended with empty line?
                # No, it just ended.
                # We can try reading until a short timeout occurs?
                
                while True:
                    try:
                        line_bytes = await asyncio.wait_for(proc.stdout.readline(), timeout=0.1)
                        if not line_bytes:
                            break
                        line = line_bytes.decode(errors="ignore").strip()
                        lines.append(line)
                        # Heuristic: if line looks like the end?
                        # There is no clear end marker in standard rigctl output for dump_state.
                    except asyncio.TimeoutError:
                        break
                return lines
             except Exception:
                 await self.close()
                 return []

    async def dump_caps(self) -> Sequence[str]:
        proc = await self._ensure_proc()
        assert proc.stdin and proc.stdout
        
        cmd = "\\dump_caps"
        
        async with self._lock:
             try:
                proc.stdin.write((cmd + "\n").encode())
                await proc.stdin.drain()
                
                lines = []
                while True:
                    try:
                        line_bytes = await asyncio.wait_for(proc.stdout.readline(), timeout=0.1)
                        if not line_bytes:
                            break
                        line = line_bytes.decode(errors="ignore").strip()
                        lines.append(line)
                    except asyncio.TimeoutError:
                        break
                return lines
             except Exception:
                 await self.close()
                 return []

    async def status(self) -> RigStatus:
        try:
            freq = await self.get_frequency()
            mode, pb = await self.get_mode()
            return RigStatus(connected=True, frequency_hz=freq, mode=mode, passband=pb)
        except Exception as e:  # noqa: BLE001
            return RigStatus(connected=False, error=str(e))

    async def close(self) -> None:
        if self._proc:
            with contextlib.suppress(Exception):
                if self._proc.stdin:
                    self._proc.stdin.close()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=0.2)
            except Exception:
                with contextlib.suppress(Exception):
                    self._proc.kill()
            self._proc = None


class RigClient:
    def __init__(self, cfg: RigConfig):
        self.cfg = cfg
        self._backend: RigBackend = self._make_backend(cfg)
        self._last_error: Optional[str] = None

    def _make_backend(self, cfg: RigConfig) -> RigBackend:
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
        self.cfg = cfg
        self._backend = self._make_backend(cfg)

    async def get_frequency(self) -> Optional[int]:
        return await self._backend.get_frequency()

    async def set_frequency(self, hz: int) -> bool:
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
        return await self._backend.get_mode()

    async def set_mode(self, mode: str, passband: Optional[int] = None) -> bool:
        # TODO: Add mode-specific validation if needed, similar to frequency
        res = await self._backend.set_mode(mode, passband)
        if not res:
            self._last_error = "Failed to set mode on rig backend"
            return False
        # Don't clear _last_error here - let caller manage error state
        return True

    async def set_vfo(self, vfo: str) -> bool:
        res = await self._backend.set_vfo(vfo)
        if not res:
            self._last_error = "Failed to set VFO on rig backend"
            return False
        # Don't clear _last_error here - let caller manage error state
        return True

    async def get_vfo(self) -> Optional[str]:
        return await self._backend.get_vfo()

    async def set_ptt(self, ptt: int) -> bool:
        res = await self._backend.set_ptt(ptt)
        if not res:
            self._last_error = "Failed to set PTT on rig backend"
            return False
        # Don't clear _last_error here - let caller manage error state
        return True

    async def get_ptt(self) -> Optional[int]:
        return await self._backend.get_ptt()

    async def get_powerstat(self) -> Optional[int]:
        return await self._backend.get_powerstat()

    async def chk_vfo(self) -> Optional[int]:
        return await self._backend.chk_vfo()

    async def dump_state(self) -> Sequence[str]:
        return await self._backend.dump_state()

    async def dump_caps(self) -> Sequence[str]:
        return await self._backend.dump_caps()

    async def status(self) -> RigStatus:
        return await self._backend.status()

    async def close(self) -> None:
        await self._backend.close()

    async def safe_status(self) -> Dict[str, Any]:
        s = await self.status()
        data: Dict[str, Any] = {
            "name": self.cfg.name,
            "enabled": getattr(self.cfg, "enabled", True),
            "connected": s.connected,
            "frequency_hz": s.frequency_hz,
            "mode": s.mode,
            "passband": s.passband,
            "error": s.error, # Connection error
            "last_error": self._last_error, # Last operational error
            "connection_type": self.cfg.connection_type,
            "follow_main": getattr(self.cfg, "follow_main", True),
            "model_id": self.cfg.model_id,
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
        }
        if self.cfg.connection_type == "rigctld":
            data.update({"host": self.cfg.host, "port": self.cfg.port})
        else:
            data.update({
                "device": self.cfg.device,
                "baud": self.cfg.baud,
            })
        return data
