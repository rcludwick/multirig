"""
Rigctl TCP server that allows external apps (WSJT-X, etc.) to control rigs.

This server bridges the rigctl protocol to Zenoh, allowing external apps to
control rigs through the MultiRig system.

Key features:
- Full command map support (dump_caps, get_level, etc.)
- Optimistic updates to prevent UI jumping in WSJT-X
- Extended response protocol (ERP) support
- State caching for fast responses
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable, Sequence
from datetime import datetime

from multirig.messages import RigState, RigCommand, RigCaps
from multirig.zenoh import keys
from multirig.zenoh.session import get_session, Publisher, Subscriber
from multirig.zenoh.serialization import serialize, deserialize

logger = logging.getLogger(__name__)


@dataclass
class RigctlServerConfig:
    """Configuration for the rigctl server."""
    host: str = "127.0.0.1"
    port: int = 4532
    target_rig_id: str = "rig1"  # Which rig to control


def _is_erp_prefix(ch: str) -> bool:
    """Check if a character is an extended response protocol prefix.
    
    Args:
        ch: Character to check
        
    Returns:
        True if the character is an ERP prefix
    """
    if not ch:
        return False
    if ch.isalnum() or ch.isspace():
        return False
    if ch in r"\?_":
        return False
    return True


def _sep_for_erp(prefix: str) -> str:
    """Get the separator for an ERP prefix.
    
    Args:
        prefix: ERP prefix character
        
    Returns:
        Separator string
    """
    return "\n" if prefix == "+" else prefix


def _records_to_bytes(records: Sequence[str], sep: str) -> bytes:
    """Convert records to bytes with the given separator.
    
    Args:
        records: List of record strings
        sep: Separator string
        
    Returns:
        Encoded bytes
    """
    if sep == "\n":
        return ("\n".join(records) + "\n").encode()
    return (sep.join(records) + sep).encode()


class RigctlServer:
    """
    Rigctl TCP server that bridges rigctl protocol to Zenoh.
    
    This server:
    1. Listens on a TCP port for rigctl commands
    2. Maintains a cached copy of rig state for fast responses
    3. Publishes commands to Zenoh
    4. Subscribes to rig state updates from Zenoh
    5. Implements optimistic updates for commands
    
    Example:
        server = RigctlServer(config)
        await server.start()
        # ... server runs ...
        await server.stop()
    """
    
    def __init__(self, config: Optional[RigctlServerConfig] = None):
        """Initialize the rigctl server.
        
        Args:
            config: Server configuration
        """
        self._cfg = config or RigctlServerConfig()
        self.host = self._cfg.host
        self.port = self._cfg.port
        self._target_rig_id = self._cfg.target_rig_id
        
        # TCP server
        self._server: Optional[asyncio.Server] = None
        
        # State cache for optimistic updates
        self._cached_state: Optional[RigState] = None
        self._cached_caps: Optional[RigCaps] = None
        
        # Zenoh publishers/subscribers
        self._command_publisher: Optional[Publisher] = None
        self._state_subscriber: Optional[Subscriber] = None
        self._caps_subscriber: Optional[Subscriber] = None
        
        # Command map
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
            "get_info": self._cmd_get_info,
            "model": self._cmd_model,
            "version": self._cmd_version,
            "token": self._cmd_token,
            "set_conf": self._cmd_set_conf,
            "get_conf": self._cmd_get_conf,
        }
    
    async def start(self) -> None:
        """Start the rigctl server."""
        if self._server is not None:
            logger.warning("Rigctl server already running")
            return
        
        logger.info(f"Starting rigctl server on {self.host}:{self.port}")
        
        # Set up Zenoh publishers/subscribers
        self._command_publisher = Publisher(keys.rig_command_key(self._target_rig_id))
        
        self._state_subscriber = Subscriber(
            keys.rig_state_key(self._target_rig_id),
            self._on_state_update
        )
        self._state_subscriber.start()
        
        self._caps_subscriber = Subscriber(
            keys.rig_caps_key(self._target_rig_id),
            self._on_caps_update
        )
        self._caps_subscriber.start()
        
        # Query for initial state and caps
        session = get_session()
        
        # Query for current state
        try:
            replies = session.get(keys.rig_state_key(self._target_rig_id))
            for reply in replies:
                if reply.ok:
                    state = deserialize(reply.ok.payload.to_bytes(), RigState)
                    self._cached_state = state
                    logger.info(f"Loaded initial state: freq={state.frequency}, mode={state.mode}")
                    break
        except Exception as e:
            logger.warning(f"Could not query initial state: {e}")
        
        # Query for current caps
        try:
            replies = session.get(keys.rig_caps_key(self._target_rig_id))
            for reply in replies:
                if reply.ok:
                    caps = deserialize(reply.ok.payload.to_bytes(), RigCaps)
                    self._cached_caps = caps
                    logger.info(f"Loaded initial caps: model={caps.model_name}")
                    break
        except Exception as e:
            logger.warning(f"Could not query initial caps: {e}")
        
        # Start TCP server
        self._server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port
        )
        logger.info(f"Rigctl server listening on {self.host}:{self.port}")
    
    async def stop(self) -> None:
        """Stop the rigctl server."""
        if self._server is None:
            return
        
        logger.info("Stopping rigctl server")
        
        # Stop TCP server
        self._server.close()
        await self._server.wait_closed()
        self._server = None
        
        # Clean up Zenoh
        if self._state_subscriber:
            self._state_subscriber.stop()
        if self._caps_subscriber:
            self._caps_subscriber.stop()
        if self._command_publisher:
            self._command_publisher.close()
    
    async def _on_state_update(self, sample):
        """Handle rig state updates from Zenoh.
        
        Args:
            sample: Zenoh sample containing rig state
        """
        try:
            state = deserialize(sample.payload.to_bytes(), RigState)
            if state.rig_id == self._target_rig_id:
                self._cached_state = state
                logger.debug(f"Updated cached state: freq={state.frequency}, mode={state.mode}")
        except Exception as e:
            logger.error(f"Error handling state update: {e}")
    
    async def _on_caps_update(self, sample):
        """Handle rig capabilities updates from Zenoh.
        
        Args:
            sample: Zenoh sample containing rig capabilities
        """
        try:
            caps = deserialize(sample.payload.to_bytes(), RigCaps)
            if caps.rig_id == self._target_rig_id:
                self._cached_caps = caps
                logger.debug(f"Updated cached caps: model={caps.model_name}")
        except Exception as e:
            logger.error(f"Error handling caps update: {e}")
    
    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle an incoming client connection.
        
        Args:
            reader: Stream reader for the client
            writer: Stream writer for the client
        """
        addr = writer.get_extra_info('peername')
        logger.info(f"Client connected from {addr}")
        
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break
                
                line = data.decode('utf-8').strip()
                if not line:
                    continue
                
                logger.debug(f"Received command: {line}")
                response = await self._handle_command_line(line)
                
                writer.write(response)
                await writer.drain()
                
        except asyncio.CancelledError:
            logger.info(f"Client {addr} connection cancelled")
        except Exception as e:
            logger.error(f"Error handling client {addr}: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
            logger.info(f"Client {addr} disconnected")
    
    async def _handle_command_line(self, line: str) -> bytes:
        """Handle a single command line.
        
        Args:
            line: Command line from client
            
        Returns:
            Response bytes
        """
        erp_prefix: Optional[str] = None
        cmdline = line.lstrip()
        
        # Check for extended response protocol prefix
        if cmdline and _is_erp_prefix(cmdline[0]):
            erp_prefix = cmdline[0]
            cmdline = cmdline[1:].lstrip()
        
        if not cmdline:
            return b""
        
        # Parse command
        parts = cmdline.split()
        cmd = parts[0]
        args = parts[1:]
        
        # Check for raw command prefix
        is_raw = cmd.startswith(r"\\"[0])
        if is_raw:
            cmd_key = cmd[1:]
        else:
            cmd_key = cmd
        
        # Dispatch command
        handler = self._command_map.get(cmd_key)
        if handler:
            return await handler(args, erp_prefix)
        
        # Special handling for chk_vfo (requires is_raw)
        if cmd_key == "chk_vfo":
            return await self._cmd_chk_vfo(erp_prefix, is_raw)
        
        return self._format_error("unknown", erp_prefix, -4)
    
    def _format_error(self, cmd: str, erp_prefix: Optional[str], code: int) -> bytes:
        """Format an error response.
        
        Args:
            cmd: Command name
            erp_prefix: ERP prefix if any
            code: Error code
            
        Returns:
            Formatted error bytes
        """
        if erp_prefix:
            return f"{erp_prefix}RPRT {code}\n".encode()
        return f"RPRT {code}\n".encode()
    
    def _publish_command(self, command: RigCommand):
        """Publish a command to Zenoh and optimistically update cache.
        
        Args:
            command: Command to publish
        """
        if self._command_publisher:
            self._command_publisher.publish(command)
            
            # Optimistic update - immediately update cache
            if command.command_type == "set_frequency":
                if self._cached_state:
                    self._cached_state.frequency = command.params.get("frequency")
            elif command.command_type == "set_mode":
                if self._cached_state:
                    self._cached_state.mode = command.params.get("mode")
                    bandwidth = command.params.get("bandwidth")
                    if bandwidth:
                        self._cached_state.bandwidth = bandwidth
            elif command.command_type == "set_ptt":
                if self._cached_state:
                    self._cached_state.ptt = command.params.get("ptt")
            elif command.command_type == "set_vfo":
                if self._cached_state:
                    self._cached_state.vfo = command.params.get("vfo")
    
    # ===== Command Handlers =====
    
    async def _cmd_set_freq(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'set_freq' (F) command."""
        if not args:
            return self._format_error("set_freq", erp_prefix, -1)
        
        try:
            hz = int(float(args[0]))
        except ValueError:
            return self._format_error("set_freq", erp_prefix, -1)
        
        command = RigCommand.set_frequency(hz, source="rigctl")
        self._publish_command(command)
        
        return f"RPRT 0\n".encode()
    
    async def _cmd_get_freq(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'get_freq' (f) command."""
        if self._cached_state is None or self._cached_state.frequency is None:
            return self._format_error("get_freq", erp_prefix, -11)
        
        hz = self._cached_state.frequency
        
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
        bandwidth = int(args[1]) if len(args) > 1 else None
        
        command = RigCommand.set_mode(mode, bandwidth, source="rigctl")
        self._publish_command(command)
        
        return f"RPRT 0\n".encode()
    
    async def _cmd_get_mode(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'get_mode' (m) command."""
        if self._cached_state is None or self._cached_state.mode is None:
            return self._format_error("get_mode", erp_prefix, -11)
        
        mode = self._cached_state.mode
        bandwidth = self._cached_state.bandwidth or 0
        
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_mode:", f"Mode: {mode}", f"Passband: {bandwidth}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        
        return f"{mode}\n{bandwidth}\n".encode()
    
    async def _cmd_set_vfo(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'set_vfo' (V) command."""
        if not args:
            return self._format_error("set_vfo", erp_prefix, -1)
        
        vfo = args[0]
        command = RigCommand.set_vfo(vfo, source="rigctl")
        self._publish_command(command)
        
        return f"RPRT 0\n".encode()
    
    async def _cmd_get_vfo(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'get_vfo' (v) command."""
        if self._cached_state is None or self._cached_state.vfo is None:
            # Default to VFOA if not set
            vfo = "VFOA"
        else:
            vfo = self._cached_state.vfo
        
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_vfo:", f"VFO: {vfo}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        
        return f"{vfo}\n".encode()
    
    async def _cmd_set_ptt(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'set_ptt' (T) command."""
        if not args:
            return self._format_error("set_ptt", erp_prefix, -1)
        
        try:
            ptt = bool(int(args[0]))
        except ValueError:
            return self._format_error("set_ptt", erp_prefix, -1)
        
        command = RigCommand.set_ptt(ptt, source="rigctl")
        self._publish_command(command)
        
        return f"RPRT 0\n".encode()
    
    async def _cmd_get_ptt(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'get_ptt' (t) command."""
        if self._cached_state is None or self._cached_state.ptt is None:
            ptt = 0
        else:
            ptt = 1 if self._cached_state.ptt else 0
        
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_ptt:", f"PTT: {ptt}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        
        return f"{ptt}\n".encode()
    
    async def _cmd_get_level(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'get_level' (l) command.
        
        This is a stub that returns 0 for any level request.
        Satisfies WSJT-X's KEYSPD query.
        """
        if not args:
            return self._format_error("get_level", erp_prefix, -1)
        
        level_name = args[0]
        value = 0  # Stub: always return 0
        
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_level:", f"Level {level_name}: {value}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        
        return f"{value}\n".encode()
    
    async def _cmd_get_split_vfo(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'get_split_vfo' (s) command.
        
        Stub that returns split off and VFOB.
        """
        split = 0
        tx_vfo = "VFOB"
        
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_split_vfo:", f"Split: {split}", f"TX VFO: {tx_vfo}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        
        return f"{split}\n{tx_vfo}\n".encode()
    
    async def _cmd_get_powerstat(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'get_powerstat' command.
        
        Returns 1 if connected, 0 otherwise.
        """
        if self._cached_state is None:
            stat = 0
        else:
            stat = 1 if self._cached_state.connected else 0
        
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_powerstat:", f"Power Status: {stat}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        
        return f"{stat}\n".encode()
    
    async def _cmd_chk_vfo(self, erp_prefix: Optional[str], is_raw: bool = False) -> bytes:
        """Handle 'chk_vfo' command.
        
        Returns the current VFO or VFOA if not available.
        """
        if self._cached_state is None or self._cached_state.vfo is None:
            vfo = "VFOA"
        else:
            vfo = self._cached_state.vfo
        
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = [f"chk_vfo: {vfo}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        
        if is_raw:
            return f"{vfo}\n".encode()
        
        return f"CHKVFO {vfo}\n".encode()
    
    async def _cmd_dump_state(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'dump_state' command.
        
        Returns a simplified dump_state output.
        """
        # Simplified dump_state
        lines = [
            "0",  # Protocol version
            "2",  # Model: Hamlib NET rigctl
            "2",  # ITU region
            "150000.000000 30000000.000000 0x1ff -1 -1 0x10000003 0x3",  # RX ranges
            "0 0 0 0 0 0 0",  # TX ranges
            "0 0",  # Mode list terminator
            "0 0",  # Filter list terminator
            "0",  # Max RIT
            "0",  # Max XIT
            "0",  # Max IF shift
            "0",  # Announces
            "0 0",  # Preamp
            "0 0",  # Attenuator
            "0x0",  # Has get functions
            "0x0",  # Has set functions
            "0x0",  # Has get level
            "0x0",  # Has set level
            "0x0",  # Has get parm
            "0x0",  # Has set parm
            "0x0",  # Has get trn
            "0x0",  # Has set trn
        ]
        
        content = "\n".join(lines) + "\n"
        
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["dump_state:", content.strip(), "RPRT 0"]
            return _records_to_bytes(records, sep)
        
        return content.encode()
    
    async def _cmd_dump_caps(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'dump_caps' command.
        
        Returns simplified capabilities based on cached caps if available.
        """
        if self._cached_caps is None:
            # Return minimal caps
            lines = [
                "Caps dump for model: 2 (NET rigctl)",
                "Model name:\tNET rigctl",
                "Mfg name:\tHamlib",
                "Backend version:\t1.0",
                "Backend status:\tStable",
            ]
        else:
            # Use cached caps
            lines = [
                f"Caps dump for model: {self._cached_caps.model_id}",
                f"Model name:\t{self._cached_caps.model_name}",
                f"Mfg name:\t{self._cached_caps.manufacturer}",
                "Backend version:\t1.0",
                "Backend status:\tStable",
            ]
        
        content = "\n".join(lines) + "\n"
        
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["dump_caps:", content.strip(), "RPRT 0"]
            return _records_to_bytes(records, sep)
        
        return content.encode()
    
    async def _cmd_get_info(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'get_info' command."""
        info = "MultiRig Zenoh Bridge v1.0"
        
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_info:", f"Info: {info}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        
        return f"{info}\n".encode()
    
    async def _cmd_model(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'model' command."""
        model_id = self._cached_caps.model_id if self._cached_caps else 2
        
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["model:", f"Model: {model_id}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        
        return f"{model_id}\n".encode()
    
    async def _cmd_version(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'version' command."""
        version = "1.0"
        
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["version:", f"Version: {version}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        
        return f"{version}\n".encode()
    
    async def _cmd_token(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'token' command (configuration tokens).
        
        Stub implementation - returns success.
        """
        return f"RPRT 0\n".encode()
    
    async def _cmd_set_conf(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'set_conf' command (set configuration).
        
        Stub implementation - returns success.
        """
        return f"RPRT 0\n".encode()
    
    async def _cmd_get_conf(self, args: list[str], erp_prefix: Optional[str]) -> bytes:
        """Handle 'get_conf' command (get configuration).
        
        Stub implementation - returns empty.
        """
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_conf:", "RPRT 0"]
            return _records_to_bytes(records, sep)
        
        return f"\nRPRT 0\n".encode()
