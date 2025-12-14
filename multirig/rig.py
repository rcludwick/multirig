from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, List
import contextlib
import shlex
import asyncio.subprocess as asp

from .config import RigConfig


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

    async def status(self) -> RigStatus:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class RigctldBackend(RigBackend):
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._lock = asyncio.Lock()

    async def _send_erp(self, cmd: str, timeout: float = 1.5) -> Tuple[int, List[str]]:
        reader: asyncio.StreamReader
        writer: asyncio.StreamWriter
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=timeout
            )
        except Exception as e:  # noqa: BLE001
            raise ConnectionError(f"rigctld connect failed {self.host}:{self.port}: {e}")

        try:
            writer.write(("+" + cmd + "\n").encode())
            await writer.drain()
            lines: List[str] = []
            while True:
                data = await asyncio.wait_for(reader.readline(), timeout=timeout)
                if not data:
                    break
                s = data.decode(errors="ignore").strip("\r\n")
                if s.startswith("RPRT "):
                    try:
                        code = int(s.split()[1])
                    except Exception:
                        code = -1
                    return code, lines
                lines.append(s)
            return -1, lines
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

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
            code, lines = await self._send_erp("f")
        if code != 0:
            return None
        kv = self._kv(lines)
        val = kv.get("Frequency")
        if val is None:
            return None
        try:
            return int(float(val))
        except Exception:
            return None

    async def set_frequency(self, hz: int) -> bool:
        async with self._lock:
            code, _ = await self._send_erp(f"F {hz}")
        return code == 0

    async def get_mode(self) -> Tuple[Optional[str], Optional[int]]:
        async with self._lock:
            code, lines = await self._send_erp("m")
        if code != 0:
            return None, None
        kv = self._kv(lines)
        mode = kv.get("Mode")
        pb_s = kv.get("Passband")
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
            code, _ = await self._send_erp(cmd)
        return code == 0

    async def set_vfo(self, vfo: str) -> bool:
        async with self._lock:
            code, _ = await self._send_erp(f"V {vfo}")
        return code == 0

    async def get_vfo(self) -> Optional[str]:
        async with self._lock:
            code, lines = await self._send_erp("v")
        if code != 0:
            return None
        kv = self._kv(lines)
        return kv.get("VFO")

    async def set_ptt(self, ptt: int) -> bool:
        async with self._lock:
            code, _ = await self._send_erp(f"T {ptt}")
        return code == 0

    async def get_ptt(self) -> Optional[int]:
        async with self._lock:
            code, lines = await self._send_erp("t")
        if code != 0:
            return None
        kv = self._kv(lines)
        val = kv.get("PTT")
        if val is None:
            return None
        try:
            return int(float(val))
        except Exception:
            return None

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
        return await self._backend.set_frequency(hz)

    async def get_mode(self) -> Tuple[Optional[str], Optional[int]]:
        return await self._backend.get_mode()

    async def set_mode(self, mode: str, passband: Optional[int] = None) -> bool:
        return await self._backend.set_mode(mode, passband)

    async def set_vfo(self, vfo: str) -> bool:
        return await self._backend.set_vfo(vfo)

    async def get_vfo(self) -> Optional[str]:
        return await self._backend.get_vfo()

    async def set_ptt(self, ptt: int) -> bool:
        return await self._backend.set_ptt(ptt)

    async def get_ptt(self) -> Optional[int]:
        return await self._backend.get_ptt()

    async def status(self) -> RigStatus:
        return await self._backend.status()

    async def close(self) -> None:
        await self._backend.close()

    async def safe_status(self) -> Dict[str, Any]:
        s = await self.status()
        data: Dict[str, Any] = {
            "name": self.cfg.name,
            "connected": s.connected,
            "frequency_hz": s.frequency_hz,
            "mode": s.mode,
            "passband": s.passband,
            "error": s.error,
            "connection_type": self.cfg.connection_type,
        }
        if self.cfg.connection_type == "rigctld":
            data.update({"host": self.cfg.host, "port": self.cfg.port})
        else:
            data.update({
                "model_id": self.cfg.model_id,
                "device": self.cfg.device,
                "baud": self.cfg.baud,
            })
        return data
