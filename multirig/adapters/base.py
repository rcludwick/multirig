"""
Base rig adapter interface.

Defines the abstract interface that all rig adapters must implement.
Handles Zenoh pub/sub, state polling, command execution, and safety checks.
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from multirig.messages import RigState, RigCommand, RigCaps
from multirig.zenoh import keys
from multirig.zenoh.session import get_session, Publisher, Subscriber
from multirig.zenoh.serialization import deserialize

logger = logging.getLogger(__name__)


class BaseRigAdapter(ABC):
    """
    Base class for all rig adapters.
    
    Responsibilities:
    1. Connect to rig (via hamlib or other means)
    2. Poll rig state periodically
    3. Publish state changes to multirig/rig/{id}/state
    4. Subscribe to commands on multirig/rig/{id}/command
    5. Execute commands with safety checks
    6. Publish capabilities to multirig/rig/{id}/caps
    """
    
    def __init__(self, rig_id: str, poll_interval: float = 0.1):
        """
        Initialize the adapter.
        
        Args:
            rig_id: Unique identifier for this rig
            poll_interval: How often to poll the rig (seconds)
        """
        self.rig_id = rig_id
        self.poll_interval = poll_interval
        
        # Connection state
        self._connected = False
        self._running = False
        
        # Last known state (for change detection)
        self._last_state: Optional[RigState] = None
        
        # Zenoh publishers/subscribers
        self._state_publisher: Optional[Publisher] = None
        self._caps_publisher: Optional[Publisher] = None
        self._command_subscriber: Optional[Subscriber] = None
        
        # Polling task
        self._poll_task: Optional[asyncio.Task] = None
        
        # Safety configuration (to be set by config)
        self._allow_out_of_band = True
        self._band_limits: Optional[dict] = None
    
    def set_safety_config(self, allow_out_of_band: bool = True, 
                         band_limits: Optional[dict] = None):
        """
        Configure safety checks for this adapter.
        
        Args:
            allow_out_of_band: Whether to allow frequencies outside configured bands
            band_limits: Dictionary of band limits (if any)
        """
        self._allow_out_of_band = allow_out_of_band
        self._band_limits = band_limits
    
    async def start(self):
        """Start the adapter: connect, subscribe, and begin polling."""
        logger.info(f"Starting adapter for rig {self.rig_id}")
        
        # Initialize Zenoh publishers/subscribers
        self._state_publisher = Publisher(keys.rig_state_key(self.rig_id))
        self._caps_publisher = Publisher(keys.rig_caps_key(self.rig_id))
        self._command_subscriber = Subscriber(
            keys.rig_command_key(self.rig_id),
            self._on_command
        )
        self._command_subscriber.start()
        
        # Connect to rig
        try:
            await self._connect()
            self._connected = True
            logger.info(f"Connected to rig {self.rig_id}")
            
            # Publish capabilities
            caps = await self._get_capabilities()
            if caps:
                self._caps_publisher.publish(caps)
            
        except Exception as e:
            logger.error(f"Failed to connect to rig {self.rig_id}: {e}")
            self._connected = False
            # Publish disconnected state
            state = RigState.disconnected(self.rig_id, str(e))
            self._state_publisher.publish(state)
        
        # Start polling loop
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
    
    async def stop(self):
        """Stop the adapter: disconnect and cleanup."""
        logger.info(f"Stopping adapter for rig {self.rig_id}")
        
        self._running = False
        
        # Stop polling
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        
        # Disconnect from rig
        if self._connected:
            await self._disconnect()
            self._connected = False
        
        # Cleanup Zenoh
        if self._command_subscriber:
            self._command_subscriber.stop()
        if self._state_publisher:
            self._state_publisher.close()
        if self._caps_publisher:
            self._caps_publisher.close()
        
        logger.info(f"Stopped adapter for rig {self.rig_id}")
    
    async def _poll_loop(self):
        """Continuously poll the rig for state changes."""
        while self._running:
            try:
                if self._connected:
                    # Get current state
                    state = await self._poll_state()
                    
                    # Check if state changed
                    if self._state_changed(state):
                        self._last_state = state
                        self._state_publisher.publish(state)
                
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                logger.error(f"Error polling rig {self.rig_id}: {e}")
                # Publish error state
                state = RigState.disconnected(self.rig_id, str(e))
                self._state_publisher.publish(state)
                self._connected = False
                await asyncio.sleep(1.0)  # Back off on error
    
    def _state_changed(self, new_state: RigState) -> bool:
        """Check if state has changed from last known state."""
        if self._last_state is None:
            return True
        
        # Compare relevant fields
        return (
            new_state.connected != self._last_state.connected or
            new_state.frequency != self._last_state.frequency or
            new_state.mode != self._last_state.mode or
            new_state.bandwidth != self._last_state.bandwidth or
            new_state.vfo != self._last_state.vfo or
            new_state.ptt != self._last_state.ptt or
            new_state.power_status != self._last_state.power_status or
            new_state.error != self._last_state.error
        )
    
    async def _on_command(self, sample):
        """Handle incoming command from Zenoh."""
        try:
            command = deserialize(sample.payload.to_bytes(), RigCommand)
            logger.debug(f"Received command for rig {self.rig_id}: {command.command_type}")
            
            if not self._connected:
                logger.warning(f"Ignoring command - rig {self.rig_id} not connected")
                return
            
            # Safety check
            if not self._check_safety(command):
                logger.warning(f"Command blocked by safety check: {command}")
                return
            
            # Execute command
            await self._execute_command(command)
            
        except Exception as e:
            logger.error(f"Error handling command for rig {self.rig_id}: {e}")
    
    def _check_safety(self, command: RigCommand) -> bool:
        """
        Check if command is safe to execute.
        
        Args:
            command: Command to check
            
        Returns:
            True if safe, False if blocked
        """
        # Check frequency limits
        if command.command_type == "set_frequency":
            freq = command.params.get("frequency")
            if freq and not self._allow_out_of_band and self._band_limits:
                # Check if frequency is within any configured band
                in_band = False
                for band_name, limits in self._band_limits.items():
                    if limits["min"] <= freq <= limits["max"]:
                        in_band = True
                        break
                
                if not in_band:
                    logger.warning(
                        f"Frequency {freq} Hz outside configured bands for rig {self.rig_id}"
                    )
                    return False
        
        return True
    
    # Abstract methods to be implemented by subclasses
    
    @abstractmethod
    async def _connect(self):
        """Connect to the rig. Must be implemented by subclass."""
        pass
    
    @abstractmethod
    async def _disconnect(self):
        """Disconnect from the rig. Must be implemented by subclass."""
        pass
    
    @abstractmethod
    async def _poll_state(self) -> RigState:
        """
        Poll the rig for current state.
        
        Returns:
            Current rig state
        """
        pass
    
    @abstractmethod
    async def _execute_command(self, command: RigCommand):
        """
        Execute a command on the rig.
        
        Args:
            command: Command to execute
        """
        pass
    
    @abstractmethod
    async def _get_capabilities(self) -> Optional[RigCaps]:
        """
        Get rig capabilities.
        
        Returns:
            Rig capabilities or None if unavailable
        """
        pass
