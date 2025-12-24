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



class BaseTcpServer:
    """Base class for TCP servers using asyncio."""

    def __init__(self, host: str, port: int, debug: Any = None):
        """Initialize the TCP server.

        Args:
            host: The host address to bind to.
            port: The port number to bind to.
            debug: Optional debug store for logging traffic.
        """
        self.host = host
        self.port = port
        self._debug = debug
        self._server: Optional[asyncio.base_events.Server] = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the TCP server.

        This method is idempotent; calling it on an already running server does nothing.
        """
        if self._server is not None:
            return
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)

    async def stop(self) -> None:
        """Stop the TCP server and close all connections.

        This method is idempotent.
        """
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle an incoming client connection.

        Args:
            reader: The stream reader for the client.
            writer: The stream writer for the client.
        
        Raises:
            NotImplementedError: Must be implemented by subclasses.
        """
        raise NotImplementedError 


class RigctlServer(BaseTcpServer):
    """TCP server that implements the hamlib `rigctl` protocol.
    
    This server allows external applications (like WSJT-X) to control the rig
    via the standard hamlib TCP protocol. It supports both standard and extended
    (ERP) response formats.
    """
    
    def __init__(
        self,
        config: Optional[RigctlServerConfig] = None,
        debug: Any = None,
    ):
        self._cfg = config or _default_server_config()
        super().__init__(self._cfg.host, self._cfg.port, debug)
        
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

    # Data access methods to be overridden by subclasses
    def get_rigs(self) -> Sequence[RigClient]:
        """Return the list of active RigClients."""
        raise NotImplementedError

    def get_source_index(self) -> int:
        """Return the current sync source index."""
        return 0

    def get_rigctl_to_main_enabled(self) -> bool:
        """Return whether rigctl changes should propagate to main rigs."""
        return True

    def get_sync_enabled(self) -> bool:
        """Return whether sync is enabled."""
        return True

    def _source_rig(self) -> Optional[RigClient]:
        rigs = self.get_rigs()
        idx = self.get_source_index()
        if not rigs or idx < 0 or idx >= len(rigs):
            return None
        return rigs[idx]

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

    def _format_error(self, cmd: str, erp_prefix: Optional[str], code: int) -> bytes:
        if erp_prefix:
            return f"{erp_prefix}RPRT {code}\n".encode()
        return f"RPRT {code}\n".encode()

    async def _cmd_set_freq(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'set_freq' (F) command."""
        if not args:
            return self._format_error("set_freq", erp_prefix, -1)
        try:
            hz = int(float(args[0]))
        except ValueError:
            return self._format_error("set_freq", erp_prefix, -1)

        rigs = self.get_rigs()
        if not rigs:
            return self._format_error("set_freq", erp_prefix, -11)

        # If sync enabled, set on all relevant rigs
        if self.get_rigctl_to_main_enabled() and self.get_sync_enabled():
            tasks = []
            for r in rigs:
                if getattr(r.cfg, "enabled", True) and getattr(r.cfg, "follow_main", True):
                    tasks.append(r.set_frequency(hz))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # Naive success check: if any succeeded, we're good? Or if source succeeded?
            # Let's check source rig specifically if possible, otherwise generic success.
            is_ok = any(r is True for r in results)
            code = 0 if is_ok else -11
        else:
            # Only set on source rig
            rig = self._source_rig()
            if rig:
                ok = await rig.set_frequency(hz)
                code = 0 if ok else -11
            else:
                code = -11
        
        return f"RPRT {code}\n".encode()

    async def _cmd_get_freq(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'get_freq' (f) command."""
        rig = self._source_rig()
        if rig is None:
            return self._format_error("get_freq", erp_prefix, -1)
        
        hz = await rig.get_frequency()
        if hz is None:
            return self._format_error("get_freq", erp_prefix, -11)
        
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_freq:", f"Frequency: {hz}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{hz}\n".encode()

    async def _cmd_set_mode(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'set_mode' (M) command."""
        if not args:
            return self._format_error("set_mode", erp_prefix, -1)
        mode = args[0]
        passband: Optional[int]
        if len(args) >= 2:
            try:
                passband = int(float(args[1]))
            except Exception:
                passband = None
        else:
            passband = None
        
        # Similar logic to set_freq for sync
        rigs = self.get_rigs()
        if not rigs:
            return self._format_error("set_mode", erp_prefix, -11)

        if self.get_rigctl_to_main_enabled() and self.get_sync_enabled():
            tasks = []
            for r in rigs:
                if getattr(r.cfg, "enabled", True) and getattr(r.cfg, "follow_main", True):
                    tasks.append(r.set_mode(mode, passband))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            is_ok = any(r is True for r in results)
            code = 0 if is_ok else -11
        else:
            rig = self._source_rig()
            if rig:
                ok = await rig.set_mode(mode, passband)
                code = 0 if ok else -11
            else:
                code = -11

        return f"RPRT {code}\n".encode()

    async def _cmd_get_mode(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'get_mode' (m) command."""
        rig = self._source_rig()
        if rig is None:
            return self._format_error("get_mode", erp_prefix, -1)
        
        try:
            ret = await rig.get_mode()
        except Exception:
            ret = None, None

        if not ret or ret[0] is None:
            return self._format_error("get_mode", erp_prefix, -11)
        
        mode, passband = ret
        # Convert None passband to 0
        pb_out = passband if passband is not None else 0
        return f"{mode}\n{pb_out}\n".encode()

    async def _cmd_set_vfo(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'set_vfo' (V) command."""
        if not args:
            return self._format_error("set_vfo", erp_prefix, -1)
        vfo = args[0]
        
        # Determine if we should broadcast VFO change. Usually VFO is specific to oper,
        # but let's assume we just pass it valid rigs.
        # Actually VFO set is often just 'VFOA' or 'VFOB' to switch focus.
        # For multirig, maybe we switch source index? For now, standard Hamlib pass-through.
        rig = self._source_rig()
        if rig:
            ok = await rig.set_vfo(vfo)
            code = 0 if ok else -11
        else:
            code = -11
            
        return f"RPRT {code}\n".encode()

    async def _cmd_get_vfo(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'get_vfo' (v) command."""
        rig = self._source_rig()
        if rig is None:
            return self._format_error("get_vfo", erp_prefix, -1)
        
        try:
            vfo = await rig.get_vfo()
        except Exception:
            vfo = None

        if vfo is None:
            return self._format_error("get_vfo", erp_prefix, -11)
            
        return f"{vfo}\n".encode()

    async def _cmd_set_ptt(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'set_ptt' (T) command."""
        if not args:
            return self._format_error("set_ptt", erp_prefix, -1)
        try:
            ptt = int(args[0])
        except ValueError:
            return self._format_error("set_ptt", erp_prefix, -1)

        # PTT should probably be sync'd if enabled?
        rigs = self.get_rigs()
        if not rigs:
             return self._format_error("set_ptt", erp_prefix, -11)
             
        if self.get_rigctl_to_main_enabled() and self.get_sync_enabled():
            tasks = []
            for r in rigs:
                 if getattr(r.cfg, "enabled", True) and getattr(r.cfg, "follow_main", True):
                    tasks.append(r.set_ptt(ptt))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            is_ok = any(r is True for r in results)
            code = 0 if is_ok else -11
        else:
            rig = self._source_rig()
            if rig:
                ok = await rig.set_ptt(ptt)
                code = 0 if ok else -11
            else:
                code = -11

        return f"RPRT {code}\n".encode()

    async def _cmd_get_ptt(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'get_ptt' (t) command."""
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
            if erp_prefix:
                sep = _sep_for_erp(erp_prefix)
                records = ["get_ptt:", f"PTT: {ptt}", "RPRT 0"]
                return _records_to_bytes(records, sep)
            return self._format_error("get_ptt", erp_prefix, -11)
            
        return f"{ptt}\n".encode()

    async def _cmd_get_level(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'get_level' (l) command."""
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
        """Handle 'get_split_vfo' (s) command."""
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
        """Handle 'get_powerstat' command."""
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
        """Handle 'chk_vfo' command."""
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
        """Handle 'dump_state' command."""
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
        """Handle 'dump_caps' command."""
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
