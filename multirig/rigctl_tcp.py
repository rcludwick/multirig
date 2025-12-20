from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Awaitable, Optional, Sequence

from .rig import RigClient, RigctlError
from .protocols import HamlibParser


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
        get_sync_enabled: Callable[[], bool] = lambda: True,
        config: Optional[RigctlServerConfig] = None,
        debug: Any = None,
    ):
        self._get_rigs = get_rigs
        self._get_source_index = get_source_index
        self._get_rigctl_to_main_enabled = get_rigctl_to_main_enabled
        self._get_sync_enabled = get_sync_enabled
        self._cfg = config or _default_server_config()
        self._debug = debug
        self._server: Optional[asyncio.base_events.Server] = None
        self._lock = asyncio.Lock()
        
        self._command_map = {
            "F": self._cmd_set_freq, "set_freq": self._cmd_set_freq,
            "f": self._cmd_get_freq, "get_freq": self._cmd_get_freq,
            "M": self._cmd_set_mode, "set_mode": self._cmd_set_mode,
            "m": self._cmd_get_mode, "get_mode": self._cmd_get_mode,
            "V": self._cmd_set_vfo, "set_vfo": self._cmd_set_vfo,
            "v": self._cmd_get_vfo, "get_vfo": self._cmd_get_vfo,
            "T": self._cmd_set_ptt, "set_ptt": self._cmd_set_ptt,
            "t": self._cmd_get_ptt, "get_ptt": self._cmd_get_ptt,
            "l": self._cmd_get_level, "get_level": self._cmd_get_level,
            "s": self._cmd_get_split_vfo, "get_split_vfo": self._cmd_get_split_vfo,
            "get_powerstat": self._cmd_get_powerstat,
            "dump_state": self._cmd_dump_state,
            "dump_caps": self._cmd_dump_caps,
        }

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
        rigs = self._get_rigs()
        if not rigs:
            return False
            
        src_idx = self._get_source_index()
        if src_idx < 0: src_idx = 0
        if src_idx >= len(rigs): src_idx = len(rigs) - 1
        
        ok = True
        sync_on = self._get_sync_enabled()
        
        for i, rig in enumerate(rigs):
            # Always apply to source rig
            if i == src_idx:
                try:
                    res = await fn(rig)
                    ok = ok and bool(res)
                except Exception:
                    ok = False
                continue
            
            # For others, check sync settings
            # If sync is disabled, do NOT forward.
            # If rig has follow_main=False, do NOT forward.
            if not sync_on:
                continue
            if not getattr(rig.cfg, "follow_main", True):
                continue
                
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

                if self._debug:
                    self._debug.add("server_rx", line=line, semantic=HamlibParser.decode(line))

                async with self._lock:
                    resp = await self._handle_command_line(line)
                
                if self._debug:
                    decoded_resp = resp.decode(errors="ignore").strip()
                    self._debug.add("server_tx", response=decoded_resp, semantic=HamlibParser.decode(decoded_resp))

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

        # Optimized dispatch
        handler = self._command_map.get(cmd_key)
        if handler:
            return await handler(args, erp_prefix)

        # Special handling for chk_vfo (requires is_raw)
        if cmd_key == "chk_vfo":
            return await self._cmd_chk_vfo(erp_prefix, is_raw)

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

        rig = self._source_rig()
        if rig is None:
            return self._format_error("set_freq", erp_prefix, -1)
        
        ok = await rig.set_frequency(hz)
        code = 0 if ok else -1

        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = [f"set_freq: {hz}", f"RPRT {code}"]
            return _records_to_bytes(records, sep)
        return f"RPRT {code}\n".encode()

    async def _cmd_get_freq(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
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

        rig = self._source_rig()
        if rig is None:
            return self._format_error("set_mode", erp_prefix, -1)
            
        ok = await rig.set_mode(mode, pb)
        code = 0 if ok else -1

        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            header = f"set_mode: {mode}" + (f" {pb}" if pb is not None else "")
            records = [header, f"RPRT {code}"]
            return _records_to_bytes(records, sep)
        return f"RPRT {code}\n".encode()

    async def _cmd_get_mode(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
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
        
        rig = self._source_rig()
        if rig is None:
            return self._format_error("set_vfo", erp_prefix, -1)

        ok = await rig.set_vfo(vfo)
        code = 0 if ok else -1

        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = [f"set_vfo: {vfo}", f"RPRT {code}"]
            return _records_to_bytes(records, sep)
        return f"RPRT {code}\n".encode()

    async def _cmd_get_vfo(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
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

        rig = self._source_rig()
        if rig is None:
            return self._format_error("set_ptt", erp_prefix, -1)

        ok = await rig.set_ptt(ptt)
        code = 0 if ok else -1

        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = [f"set_ptt: {ptt}", f"RPRT {code}"]
            return _records_to_bytes(records, sep)
        return f"RPRT {code}\n".encode()

    async def _cmd_get_ptt(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
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

    async def _cmd_get_split_vfo(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
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

    async def _cmd_get_powerstat(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
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

    async def _cmd_dump_state(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
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

    async def _cmd_dump_caps(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
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
