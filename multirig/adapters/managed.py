"""
Managed rigctld adapter.

Spawns a rigctld subprocess and connects to it via TCP.
"""
import asyncio
import asyncio.subprocess as asp
import logging
import shlex
import socket
from typing import Optional

from .rigctld import RigctldAdapter
from multirig.messages import RigState, RigCommand, RigCaps

logger = logging.getLogger(__name__)


def _find_free_port() -> int:
    """Find a free port for rigctld to bind to."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class ManagedRigAdapter(RigctldAdapter):
    """
    Managed rigctld adapter.
    
    Spawns rigctld as a subprocess, manages its lifecycle,
    and connects to it via RigctldAdapter.
    """
    
    def __init__(
        self,
        rig_id: str,
        model_id: int,
        device: str,
        baud: Optional[int] = None,
        serial_opts: Optional[str] = None,
        extra_args: Optional[str] = None,
        poll_interval: float = 0.1
    ):
        """
        Initialize the managed adapter.
        
        Args:
            rig_id: Unique identifier for this rig
            model_id: Hamlib model ID
            device: Serial device path (e.g., /dev/ttyUSB0)
            baud: Baud rate for serial connection
            serial_opts: Additional serial options
            extra_args: Extra arguments for rigctld
            poll_interval: How often to poll the rig (seconds)
        """
        # Find a free port for rigctld
        self._port = _find_free_port()
        
        # Initialize parent with localhost connection
        super().__init__(rig_id, "127.0.0.1", self._port, poll_interval)
        
        # Store config for spawning rigctld
        self.model_id = model_id
        self.device = device
        self.baud = baud
        self.serial_opts = serial_opts
        self.extra_args = extra_args
        
        # Process handle
        self._proc: Optional[asp.Process] = None
        self._spawn_lock = asyncio.Lock()
    
    async def _connect(self):
        """Spawn rigctld and connect to it."""
        async with self._spawn_lock:
            # Build rigctld command
            cmd = [
                "rigctld",
                "-m", str(self.model_id),
                "-r", self.device,
                "-t", str(self._port),
                "-T", "127.0.0.1",  # Listen on localhost only
            ]
            
            if self.baud:
                cmd += ["-s", str(self.baud)]
            
            if self.serial_opts:
                cmd += shlex.split(self.serial_opts)
            
            if self.extra_args:
                cmd += shlex.split(self.extra_args)
            
            logger.info(f"Spawning rigctld for rig {self.rig_id}: {' '.join(cmd)}")
            
            try:
                self._proc = await asp.create_subprocess_exec(
                    *cmd,
                    stdout=asp.DEVNULL,
                    stderr=asp.DEVNULL
                )
                
                # Give rigctld time to bind to the port
                await asyncio.sleep(0.5)
                
                # Verify process started
                if self._proc.returncode is not None:
                    raise ConnectionError(f"rigctld process exited immediately with code {self._proc.returncode}")
                
                logger.info(f"rigctld spawned for rig {self.rig_id} on port {self._port}")
                
            except Exception as e:
                logger.error(f"Failed to spawn rigctld for rig {self.rig_id}: {e}")
                raise ConnectionError(f"Failed to spawn rigctld: {e}")
        
        # Now connect via parent class
        try:
            await super()._connect()
        except Exception as e:
            # If connection fails, kill the process
            await self._kill_process()
            raise
    
    async def _disconnect(self):
        """Disconnect and kill the rigctld process."""
        # Disconnect from TCP
        await super()._disconnect()
        
        # Kill the process
        await self._kill_process()
    
    async def _kill_process(self):
        """Kill the rigctld process."""
        if self._proc:
            logger.info(f"Killing rigctld process for rig {self.rig_id}")
            try:
                self._proc.terminate()
                try:
                    await asyncio.wait_for(self._proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning(f"rigctld process did not terminate, killing forcefully")
                    self._proc.kill()
                    await self._proc.wait()
            except Exception as e:
                logger.error(f"Error killing rigctld process: {e}")
            finally:
                self._proc = None
