from __future__ import annotations
import asyncio
import asyncio.subprocess as asp
import contextlib
import shlex
from typing import Optional, Tuple, Sequence
from .common import RigStatus
from .backend import RigBackend
from .tcp import RigctldBackend

def _find_free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

class RigctlManagedBackend(RigBackend):
    """Backend that manages a local rigctld subprocess and connects via TCP."""

    def __init__(self, model_id: int, device: str, baud: Optional[int] = None,
                 serial_opts: Optional[str] = None, extra_args: Optional[str] = None):
        self.model_id = model_id
        self.device = device
        self.baud = baud
        self.serial_opts = serial_opts
        self.extra_args = extra_args
        
        self._port: Optional[int] = None
        self._proc: Optional[asp.Process] = None
        self._backend: Optional[RigctldBackend] = None
        self._lock = asyncio.Lock()

    async def _ensure_backend(self) -> RigctldBackend:
        async with self._lock:
            # Check if process is running
            if self._proc and self._proc.returncode is not None:
                 self._proc = None
            
            if not self._proc:
                self._port = _find_free_port()
                cmd = [
                    "rigctld",
                    "-m", str(self.model_id),
                    "-r", self.device,
 
                                  # Wait, rigctld uses -p/--port for listening port? No, it's -t/--port?
                                  # `rigctld --help` says `-T, --listen-addr` and `-t, --port`.
                    "-t", str(self._port)
                ]
                if self.baud:
                    cmd += ["-s", str(self.baud)]
                if self.serial_opts:
                    cmd += shlex.split(self.serial_opts)
                if self.extra_args:
                    cmd += shlex.split(self.extra_args)
                
                # Listen on localhost only for security
                cmd += ["-T", "127.0.0.1"]

                # Add -vvvv for debugging? Maybe just -v
                # cmd.append("-v")

                try:

                    self._proc = await asp.create_subprocess_exec(
                        *cmd,
                        stdout=asp.DEVNULL,
                        stderr=asp.DEVNULL
                    )
                    # Give it a moment to bind
                    await asyncio.sleep(0.5)
                except Exception as e:
                    raise ConnectionError(f"Failed to spawn rigctld: {e}")

                self._backend = RigctldBackend("127.0.0.1", self._port)

            return self._backend

    async def close(self) -> None:
        async with self._lock:
            if self._backend:
                await self._backend.close()
                self._backend = None
            
            if self._proc:
                with contextlib.suppress(Exception):
                    self._proc.terminate()
                try:
                    await asyncio.wait_for(self._proc.wait(), timeout=1.0)
                except Exception:
                    with contextlib.suppress(Exception):
                        self._proc.kill()
                self._proc = None

    # Delegate all methods to the inner backend
    async def get_frequency(self) -> Optional[int]:
        b = await self._ensure_backend()
        return await b.get_frequency()

    async def set_frequency(self, hz: int) -> bool:
        b = await self._ensure_backend()
        return await b.set_frequency(hz)

    async def get_mode(self) -> Tuple[Optional[str], Optional[int]]:
        b = await self._ensure_backend()
        return await b.get_mode()

    async def set_mode(self, mode: str, passband: Optional[int] = None) -> bool:
        b = await self._ensure_backend()
        return await b.set_mode(mode, passband)

    async def set_vfo(self, vfo: str) -> bool:
        b = await self._ensure_backend()
        return await b.set_vfo(vfo)

    async def get_vfo(self) -> Optional[str]:
        b = await self._ensure_backend()
        return await b.get_vfo()

    async def set_ptt(self, ptt: int) -> bool:
        b = await self._ensure_backend()
        return await b.set_ptt(ptt)

    async def get_ptt(self) -> Optional[int]:
        b = await self._ensure_backend()
        return await b.get_ptt()

    async def get_powerstat(self) -> Optional[int]:
        b = await self._ensure_backend()
        return await b.get_powerstat()

    async def chk_vfo(self) -> Optional[int]:
        b = await self._ensure_backend()
        return await b.chk_vfo()
    
    async def dump_state(self) -> Sequence[str]:
        b = await self._ensure_backend()
        return await b.dump_state()

    async def dump_caps(self) -> Sequence[str]:
        b = await self._ensure_backend()
        return await b.dump_caps()

    async def status(self) -> RigStatus:
        try:
            b = await self._ensure_backend()
            return await b.status()
        except Exception as e:
            return RigStatus(connected=False, error=str(e))
