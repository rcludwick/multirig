"""
Sync Engine - Propagates state changes from source rig to followers.

The sync engine watches the source rig for state changes and automatically
copies those changes to follower rigs based on configuration.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, Set

from multirig.messages import RigState, RigCommand, SyncState
from multirig.zenoh import keys
from multirig.zenoh.session import get_session, Publisher, Subscriber
from multirig.zenoh.serialization import deserialize

logger = logging.getLogger(__name__)


class SyncEngine:
    """
    Sync Engine - Propagates changes from source rig to followers.
    
    Responsibilities:
    1. Subscribe to all rig state updates
    2. Watch source rig for changes
    3. Publish commands to follower rigs
    4. Publish sync state
    5. Handle debouncing to avoid command floods
    """
    
    def __init__(self, debounce_ms: float = 100):
        """
        Initialize the sync engine.
        
        Args:
            debounce_ms: Debounce time in milliseconds to avoid command floods
        """
        self.debounce_ms = debounce_ms
        
        # Sync configuration
        self.enabled = False
        self.source_rig_id: Optional[str] = None
        self.follower_rig_ids: Set[str] = set()
        
        # What to sync
        self.sync_frequency = True
        self.sync_mode = True
        self.sync_ptt = False
        
        # Last known state of source rig
        self._last_source_state: Optional[RigState] = None
        
        # Debouncing
        self._debounce_task: Optional[asyncio.Task] = None
        self._pending_commands: dict[str, list[RigCommand]] = {}
        
        # Zenoh
        self._state_subscriber: Optional[Subscriber] = None
        self._sync_state_publisher: Optional[Publisher] = None
        
        # Status tracking
        self._last_sync_timestamp: Optional[float] = None
        self._error: Optional[str] = None
        
        # Running flag
        self._running = False
    
    def configure(
        self,
        enabled: bool = False,
        source_rig_id: Optional[str] = None,
        follower_rig_ids: Optional[list[str]] = None,
        sync_frequency: bool = True,
        sync_mode: bool = True,
        sync_ptt: bool = False
    ):
        """
        Configure the sync engine.
        
        Args:
            enabled: Whether sync is enabled
            source_rig_id: ID of the source rig to watch
            follower_rig_ids: List of follower rig IDs
            sync_frequency: Whether to sync frequency
            sync_mode: Whether to sync mode
            sync_ptt: Whether to sync PTT
        """
        self.enabled = enabled
        self.source_rig_id = source_rig_id
        self.follower_rig_ids = set(follower_rig_ids or [])
        self.sync_frequency = sync_frequency
        self.sync_mode = sync_mode
        self.sync_ptt = sync_ptt
        
        logger.info(
            f"Sync engine configured: enabled={enabled}, source={source_rig_id}, "
            f"followers={self.follower_rig_ids}, freq={sync_frequency}, "
            f"mode={sync_mode}, ptt={sync_ptt}"
        )
        
        # Publish updated state
        if self._running:
            self._publish_sync_state()
    
    def set_source(self, rig_id: Optional[str]):
        """Set the source rig ID."""
        self.source_rig_id = rig_id
        self._last_source_state = None  # Reset state tracking
        if self._running:
            self._publish_sync_state()
    
    def add_follower(self, rig_id: str):
        """Add a follower rig."""
        self.follower_rig_ids.add(rig_id)
        if self._running:
            self._publish_sync_state()
    
    def remove_follower(self, rig_id: str):
        """Remove a follower rig."""
        self.follower_rig_ids.discard(rig_id)
        if self._running:
            self._publish_sync_state()
    
    async def start(self):
        """Start the sync engine."""
        logger.info("Starting sync engine")
        
        self._running = True
        
        # Initialize Zenoh publishers/subscribers
        self._sync_state_publisher = Publisher(keys.SYNC_STATE)
        
        # Subscribe to all rig states
        self._state_subscriber = Subscriber(
            keys.RIG_STATE_ALL,
            self._on_rig_state
        )
        self._state_subscriber.start()
        
        # Publish initial sync state
        self._publish_sync_state()
        
        logger.info("Sync engine started")
    
    async def stop(self):
        """Stop the sync engine."""
        logger.info("Stopping sync engine")
        
        self._running = False
        
        # Cancel debounce task
        if self._debounce_task:
            self._debounce_task.cancel()
            try:
                await self._debounce_task
            except asyncio.CancelledError:
                pass
        
        # Cleanup Zenoh
        if self._state_subscriber:
            self._state_subscriber.stop()
        if self._sync_state_publisher:
            self._sync_state_publisher.close()
        
        logger.info("Sync engine stopped")
    
    async def _on_rig_state(self, sample):
        """Handle rig state updates."""
        try:
            state = deserialize(sample.payload.to_bytes(), RigState)
            
            # Only process if sync is enabled and this is the source rig
            if not self.enabled or not self.source_rig_id:
                return
            
            if state.rig_id != self.source_rig_id:
                return
            
            # Check if this is a connected state
            if not state.connected:
                return
            
            # Check if state changed from last known
            if self._state_changed(state):
                logger.debug(f"Source rig {self.source_rig_id} state changed")
                await self._sync_to_followers(state)
                self._last_source_state = state
                
        except Exception as e:
            logger.error(f"Error handling rig state in sync engine: {e}")
            self._error = str(e)
            self._publish_sync_state()
    
    def _state_changed(self, new_state: RigState) -> bool:
        """Check if state has changed in ways we care about."""
        if self._last_source_state is None:
            return True
        
        changed = False
        
        if self.sync_frequency and new_state.frequency != self._last_source_state.frequency:
            changed = True
        
        if self.sync_mode and (
            new_state.mode != self._last_source_state.mode or
            new_state.bandwidth != self._last_source_state.bandwidth
        ):
            changed = True
        
        if self.sync_ptt and new_state.ptt != self._last_source_state.ptt:
            changed = True
        
        return changed
    
    async def _sync_to_followers(self, state: RigState):
        """Sync state to follower rigs."""
        if not self.follower_rig_ids:
            return
        
        # Generate commands for each follower
        for follower_id in self.follower_rig_ids:
            commands = []
            
            # Frequency command
            if self.sync_frequency and state.frequency is not None:
                cmd = RigCommand.set_frequency(state.frequency, source="sync")
                commands.append(cmd)
            
            # Mode command
            if self.sync_mode and state.mode is not None:
                cmd = RigCommand.set_mode(state.mode, state.bandwidth, source="sync")
                commands.append(cmd)
            
            # PTT command
            if self.sync_ptt and state.ptt is not None:
                cmd = RigCommand.set_ptt(state.ptt, source="sync")
                commands.append(cmd)
            
            # Queue commands for debouncing
            if commands:
                self._pending_commands[follower_id] = commands
        
        # Trigger debounced send
        await self._debounce_send()
    
    async def _debounce_send(self):
        """Debounce command sending to avoid floods."""
        # Cancel existing debounce task
        if self._debounce_task:
            self._debounce_task.cancel()
            try:
                await self._debounce_task
            except asyncio.CancelledError:
                pass
        
        # Create new debounce task
        self._debounce_task = asyncio.create_task(self._send_after_delay())
    
    async def _send_after_delay(self):
        """Send commands after debounce delay."""
        try:
            await asyncio.sleep(self.debounce_ms / 1000.0)
            
            # Send all pending commands
            session = get_session()
            
            for follower_id, commands in self._pending_commands.items():
                command_key = keys.rig_command_key(follower_id)
                
                for cmd in commands:
                    from multirig.zenoh.serialization import serialize
                    session.put(command_key, serialize(cmd))
                    logger.debug(
                        f"Synced {cmd.command_type} from {self.source_rig_id} to {follower_id}"
                    )
            
            # Clear pending commands
            self._pending_commands.clear()
            
            # Update sync timestamp
            self._last_sync_timestamp = datetime.now().timestamp()
            self._error = None
            self._publish_sync_state()
            
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error sending sync commands: {e}")
            self._error = str(e)
            self._publish_sync_state()
    
    def _publish_sync_state(self):
        """Publish current sync state."""
        if not self._sync_state_publisher:
            return
        
        state = SyncState(
            enabled=self.enabled,
            source_rig_id=self.source_rig_id,
            follower_rig_ids=list(self.follower_rig_ids),
            sync_frequency=self.sync_frequency,
            sync_mode=self.sync_mode,
            sync_ptt=self.sync_ptt,
            last_sync_timestamp=self._last_sync_timestamp,
            error=self._error
        )
        
        self._sync_state_publisher.publish(state)
