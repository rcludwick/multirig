from __future__ import annotations
import asyncio
import asyncio.subprocess as asp
import contextlib
import shlex
from typing import Optional, List, Tuple, Sequence
from .common import RigStatus
from .backend import RigBackend

class RigctlProcessBackend(RigBackend):
    """Direct hamlib control using a persistent 'rigctl' subprocess in interactive mode.
    
    This backend launches `rigctl` as a subprocess and communicates with it via
    stdin/stdout using the interactive commands.
    """

    def __init__(self, model_id: int, device: str, baud: Optional[int] = None,
                 serial_opts: Optional[str] = None, extra_args: Optional[str] = None):
        """Initialize the process backend.

        Args:
            model_id: Hamlib model ID.
            device: Serial device path or URI.
            baud: Optional baud rate.
            serial_opts: Optional serial configuration string.
            extra_args: Optional extra arguments for rigctl.
        """
        self.model_id = model_id
        self.device = device
        self.baud = baud
        self.serial_opts = serial_opts
        self.extra_args = extra_args
        self._proc: Optional[asp.Process] = None
        self._lock = asyncio.Lock()

    def _build_cmd(self) -> list[str]:
        """Build the rigctl command line arguments.
        
        Returns:
            List of command line arguments.
        """
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
        """Ensure the subprocess is running.
        
        Returns:
            The active asyncio Process object.
        """
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
            resp = await self._send(r"\get_powerstat")
        v = resp.strip()
        if not v or v.startswith("RPRT "):
            return None
        try:
            return int(float(v))
        except Exception:
            return None

    async def chk_vfo(self) -> Optional[int]:
        async with self._lock:
            resp = await self._send(r"\chk_vfo")
        v = resp.strip()
        if not v or v.startswith("RPRT "):
            return None
        try:
            return int(float(v))
        except Exception:
            return None

    async def dump_state(self) -> Sequence[str]:
        
        proc = await self._ensure_proc()
        assert proc.stdin and proc.stdout
        
        cmd = r"\dump_state"
        
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
             except Exception as e:
                 print(f"DEBUG: dump_state error: {e}")
                 await self.close()
                 return []

    async def dump_caps(self) -> Sequence[str]:
        proc = await self._ensure_proc()
        assert proc.stdin and proc.stdout
        
        cmd = r"\dump_caps"
        
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
