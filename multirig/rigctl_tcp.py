from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Awaitable, Optional, Sequence

from .rig import RigClient


@dataclass
class RigctlServerConfig:
    host: str
    port: int


def _default_server_config() -> RigctlServerConfig:
    return RigctlServerConfig(host="127.0.0.1", port=4534)


def _is_erp_prefix(ch: str) -> bool:
    if not ch:
        return False
    if ch.isalnum() or ch.isspace():
        return False
    if ch in ("\\", "?", "_"):
        return False
    return True


def _sep_for_erp(prefix: str) -> str:
    return "\n" if prefix == "+" else prefix


def _records_to_bytes(records: Sequence[str], sep: str) -> bytes:
    if sep == "\n":
        return ("\n".join(records) + "\n").encode()
    return (sep.join(records) + sep).encode()


class RigctlTcpServer:
    def __init__(
        self,
        get_rigs: Callable[[], Sequence[RigClient]],
        get_source_index: Callable[[], int],
        config: Optional[RigctlServerConfig] = None,
    ):
        self._get_rigs = get_rigs
        self._get_source_index = get_source_index
        self._cfg = config or _default_server_config()
        self._server: Optional[asyncio.base_events.Server] = None
        self._lock = asyncio.Lock()

    @property
    def host(self) -> str:
        return self._cfg.host

    @property
    def port(self) -> int:
        return self._cfg.port

    async def start(self) -> None:
        if self._server is not None:
            return
        self._server = await asyncio.start_server(self._handle_client, self._cfg.host, self._cfg.port)

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    def _source_rig(self) -> Optional[RigClient]:
        rigs = list(self._get_rigs())
        if not rigs:
            return None
        idx = self._get_source_index()
        if idx < 0:
            idx = 0
        if idx >= len(rigs):
            idx = len(rigs) - 1
        return rigs[idx]

    async def _fanout(self, fn: Callable[[RigClient], Awaitable[bool]]) -> bool:
        ok = True
        for rig in self._get_rigs():
            try:
                res = await fn(rig)
                ok = ok and bool(res)
            except Exception:
                ok = False
        return ok

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    return
                line = raw.decode(errors="ignore").strip("\r\n")
                if not line:
                    continue
                if line.strip() in ("q", "Q", "quit", "exit"):
                    return

                async with self._lock:
                    resp = await self._handle_command_line(line)
                writer.write(resp)
                await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _handle_command_line(self, line: str) -> bytes:
        erp_prefix: Optional[str] = None
        cmdline = line.lstrip()
        if cmdline and _is_erp_prefix(cmdline[0]):
            erp_prefix = cmdline[0]
            cmdline = cmdline[1:].lstrip()

        if not cmdline:
            return b""

        parts = cmdline.split()
        cmd = parts[0]
        args = parts[1:]

        if cmd.startswith("\\"):
            cmd_key = cmd[1:]
        else:
            cmd_key = cmd

        if cmd_key in ("F", "set_freq"):
            return await self._cmd_set_freq(args, erp_prefix)
        if cmd_key in ("f", "get_freq"):
            return await self._cmd_get_freq(erp_prefix)
        if cmd_key in ("M", "set_mode"):
            return await self._cmd_set_mode(args, erp_prefix)
        if cmd_key in ("m", "get_mode"):
            return await self._cmd_get_mode(erp_prefix)
        if cmd_key in ("V", "set_vfo"):
            return await self._cmd_set_vfo(args, erp_prefix)
        if cmd_key in ("v", "get_vfo"):
            return await self._cmd_get_vfo(erp_prefix)
        if cmd_key in ("T", "set_ptt"):
            return await self._cmd_set_ptt(args, erp_prefix)
        if cmd_key in ("t", "get_ptt"):
            return await self._cmd_get_ptt(erp_prefix)

        return self._format_error("unknown", erp_prefix, -4)

    def _format_error(self, long_name: str, erp_prefix: Optional[str], code: int) -> bytes:
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = [f"{long_name}:" if long_name else "", f"RPRT {code}"]
            records = [r for r in records if r]
            return _records_to_bytes(records, sep)
        return f"RPRT {code}\n".encode()

    async def _cmd_set_freq(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        if not args:
            return self._format_error("set_freq", erp_prefix, -1)
        try:
            hz = int(float(args[0]))
        except Exception:
            return self._format_error("set_freq", erp_prefix, -1)

        ok = await self._fanout(lambda r: r.set_frequency(hz))
        code = 0 if ok else -1

        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = [f"set_freq: {hz}", f"RPRT {code}"]
            return _records_to_bytes(records, sep)
        return f"RPRT {code}\n".encode()

    async def _cmd_get_freq(self, erp_prefix: Optional[str]) -> bytes:
        rig = self._source_rig()
        if rig is None:
            return self._format_error("get_freq", erp_prefix, -1)
        try:
            hz = await rig.get_frequency()
        except Exception:
            hz = None
        if hz is None:
            return self._format_error("get_freq", erp_prefix, -1)

        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_freq:", f"Frequency: {hz}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{hz}\n".encode()

    async def _cmd_set_mode(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        if not args:
            return self._format_error("set_mode", erp_prefix, -1)
        mode = args[0]
        pb: Optional[int]
        if len(args) >= 2:
            try:
                pb = int(float(args[1]))
            except Exception:
                pb = None
        else:
            pb = None

        ok = await self._fanout(lambda r: r.set_mode(mode, pb))
        code = 0 if ok else -1

        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            header = f"set_mode: {mode}" + (f" {pb}" if pb is not None else "")
            records = [header, f"RPRT {code}"]
            return _records_to_bytes(records, sep)
        return f"RPRT {code}\n".encode()

    async def _cmd_get_mode(self, erp_prefix: Optional[str]) -> bytes:
        rig = self._source_rig()
        if rig is None:
            return self._format_error("get_mode", erp_prefix, -1)
        try:
            mode, pb = await rig.get_mode()
        except Exception:
            mode, pb = None, None

        if not mode:
            return self._format_error("get_mode", erp_prefix, -1)
        pb_out = pb if pb is not None else 0

        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_mode:", f"Mode: {mode}", f"Passband: {pb_out}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{mode} {pb_out}\n".encode()

    async def _cmd_set_vfo(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        if not args:
            return self._format_error("set_vfo", erp_prefix, -1)
        vfo = args[0]
        ok = await self._fanout(lambda r: r.set_vfo(vfo))
        code = 0 if ok else -1

        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = [f"set_vfo: {vfo}", f"RPRT {code}"]
            return _records_to_bytes(records, sep)
        return f"RPRT {code}\n".encode()

    async def _cmd_get_vfo(self, erp_prefix: Optional[str]) -> bytes:
        rig = self._source_rig()
        if rig is None:
            return self._format_error("get_vfo", erp_prefix, -1)
        try:
            vfo = await rig.get_vfo()
        except Exception:
            vfo = None
        if not vfo:
            return self._format_error("get_vfo", erp_prefix, -1)

        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_vfo:", f"VFO: {vfo}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{vfo}\n".encode()

    async def _cmd_set_ptt(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        if not args:
            return self._format_error("set_ptt", erp_prefix, -1)
        try:
            ptt = int(args[0])
        except Exception:
            return self._format_error("set_ptt", erp_prefix, -1)

        ok = await self._fanout(lambda r: r.set_ptt(ptt))
        code = 0 if ok else -1

        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = [f"set_ptt: {ptt}", f"RPRT {code}"]
            return _records_to_bytes(records, sep)
        return f"RPRT {code}\n".encode()

    async def _cmd_get_ptt(self, erp_prefix: Optional[str]) -> bytes:
        rig = self._source_rig()
        if rig is None:
            return self._format_error("get_ptt", erp_prefix, -1)
        try:
            ptt = await rig.get_ptt()
        except Exception:
            ptt = None
        if ptt is None:
            return self._format_error("get_ptt", erp_prefix, -1)

        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_ptt:", f"PTT: {ptt}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{ptt}\n".encode()
