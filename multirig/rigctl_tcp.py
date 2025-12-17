from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Awaitable, Optional, Sequence

from .rig import RigClient, RigctlError


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
        get_rigctl_to_main_enabled: Callable[[], bool] = lambda: True,
        config: Optional[RigctlServerConfig] = None,
        debug: Any = None,
    ):
        self._get_rigs = get_rigs
        self._get_source_index = get_source_index
        self._get_rigctl_to_main_enabled = get_rigctl_to_main_enabled
        self._cfg = config or _default_server_config()
        self._debug = debug
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

        is_raw = cmd.startswith("\\")
        if is_raw:
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
        if cmd_key in ("l", "get_level"):
            return await self._cmd_get_level(args, erp_prefix)
        if cmd_key in ("s", "get_split_vfo"):
            return await self._cmd_get_split_vfo(erp_prefix)
        if cmd_key == "get_powerstat":
            return await self._cmd_get_powerstat(erp_prefix)
        if cmd_key == "chk_vfo":
            return await self._cmd_chk_vfo(erp_prefix, is_raw)
        if cmd_key == "dump_state":
            return await self._cmd_dump_state(erp_prefix)
        if cmd_key == "dump_caps":
            return await self._cmd_dump_caps(erp_prefix)

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
        return f"{mode}\n{pb_out}\n".encode()

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
        except RigctlError as e:
            # Pass through the error code from the backend rig
            return self._format_error("get_ptt", erp_prefix, e.code)
        except Exception:
            ptt = None
        if ptt is None:
            return self._format_error("get_ptt", erp_prefix, -1)

        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_ptt:", f"PTT: {ptt}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{ptt}\n".encode()

    async def _cmd_get_level(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        # get_level command - for now, return 0 for any level request
        # This is a stub implementation that satisfies WSJT-X's KEYSPD query
        if not args:
            return self._format_error("get_level", erp_prefix, -1)
        
        level_name = args[0]
        # Return 0 for any level - this satisfies WSJT-X
        value = 0
        
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_level:", f"Level {level_name}: {value}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{value}\n".encode()

    async def _cmd_get_split_vfo(self, erp_prefix: Optional[str]) -> bytes:
        # get_split_vfo command - returns split status and TX VFO
        # For now, return split=0 (off) and current VFO
        rig = self._source_rig()
        if rig is None:
            return self._format_error("get_split_vfo", erp_prefix, -1)
        
        try:
            vfo = await rig.get_vfo()
        except Exception:
            vfo = "VFOB"
        
        split = 0  # Split off
        tx_vfo = vfo if vfo else "VFOB"
        
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_split_vfo:", f"Split: {split}", f"TX VFO: {tx_vfo}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{split}\n{tx_vfo}\n".encode()

    async def _cmd_get_powerstat(self, erp_prefix: Optional[str]) -> bytes:
        rig = self._source_rig()
        if rig is None:
            return self._format_error("get_powerstat", erp_prefix, -1)
        try:
            stat = await rig.get_powerstat()
        except Exception:
            stat = None
        if stat is None:
            return self._format_error("get_powerstat", erp_prefix, -1)

        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_powerstat:", f"Power Status: {stat}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{stat}\n".encode()

    async def _cmd_chk_vfo(self, erp_prefix: Optional[str], is_raw: bool = False) -> bytes:
        rig = self._source_rig()
        if rig is None:
            return self._format_error("chk_vfo", erp_prefix, -1)
        try:
            ret = await rig.chk_vfo()
        except Exception:
            ret = None
        if ret is None:
            return self._format_error("chk_vfo", erp_prefix, -1)

        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            # chk_vfo extended response format isn't well documented but following pattern
            records = [f"chk_vfo: {ret}", "RPRT 0"]
            return _records_to_bytes(records, sep)
            
        if is_raw:
            return f"{ret}\n".encode()
            
        return f"CHKVFO {ret}\n".encode()

    async def _cmd_dump_state(self, erp_prefix: Optional[str]) -> bytes:
        rig = self._source_rig()
        if rig is None:
            return self._format_error("dump_state", erp_prefix, -1)
        try:
            lines = await rig.dump_state()
        except Exception:
            lines = []
        
        if not lines:
             return self._format_error("dump_state", erp_prefix, -1)

        # dump_state output is raw lines.
        # If extended, maybe wrap it? But dump_state is special.
        # Usually it's just raw dump.
        # If we received it from backend, it's a list of strings.
        
        content = "\n".join(lines) + "\n"
        
        if erp_prefix:
            # Extended mode dump_state
            sep = _sep_for_erp(erp_prefix)
            records = ["dump_state:", content.strip(), "RPRT 0"]
            return _records_to_bytes(records, sep)

        return content.encode()

    async def _cmd_dump_caps(self, erp_prefix: Optional[str]) -> bytes:
        rig = self._source_rig()
        if rig is None:
            return self._format_error("dump_caps", erp_prefix, -1)
        try:
            lines = await rig.dump_caps()
        except Exception:
            lines = []
        
        if not lines:
             return self._format_error("dump_caps", erp_prefix, -1)
        
        content = "\n".join(lines) + "\n"
        
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["dump_caps:", content.strip(), "RPRT 0"]
            return _records_to_bytes(records, sep)

        return content.encode()
