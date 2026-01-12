"""
Central message router for MultiRig.

All rig communication flows through this router, which handles:
- Command dispatch to appropriate RigClients
- Response routing back to requestors
- Status caching for HTTP queries
- WebSocket push on status changes
- Sync logic (autodetect on commands + polling for direct rig changes)
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Optional, Dict, List, Any, Set, TYPE_CHECKING
from weakref import WeakSet

from .hamlib.messages import (
    HamlibCommand, SetFreq, SetMode, SetVfo, SetPtt,
    GetFreq, GetMode, GetVfo, GetPtt, GetLevel, GetSplitVfo,
    GetPowerstat, DumpState, DumpCaps, GetInfo, ChkVfo
)
from .hamlib.responses import (
    HamlibResponse, BaseResponse, FreqResponse, ModeResponse,
    SuccessResponse
)

if TYPE_CHECKING:
    from .rig import RigClient


class RigStatus:
    """Cached status for a single rig."""
    
    def __init__(self):
        self.connected: bool = False
        self.frequency_hz: Optional[int] = None
        self.mode: Optional[str] = None
        self.passband: Optional[int] = None
        self.error: Optional[str] = None
        self.last_update: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "frequency_hz": self.frequency_hz,
            "mode": self.mode,
            "passband": self.passband,
            "error": self.error,
        }
    
    def update_from_response(self, resp: HamlibResponse) -> bool:
        """Update status from a response. Returns True if status changed."""
        changed = False
        self.last_update = time.time()
        
        if resp.result == 0:
            self.connected = True
            self.error = None
            
            if isinstance(resp, FreqResponse):
                if self.frequency_hz != resp.frequency:
                    self.frequency_hz = resp.frequency
                    changed = True
            elif isinstance(resp, ModeResponse):
                if self.mode != resp.mode or self.passband != resp.passband:
                    self.mode = resp.mode
                    self.passband = resp.passband
                    changed = True
        else:
            self.error = f"Error code: {resp.result}"
        
        return changed


class MessageRouter:
    """Central async message router for all rig communication.
    
    This router:
    - Receives HamlibCommand from frontends (RigctlServer, HTTP, WebSocket)
    - Dispatches commands to appropriate RigClient(s)
    - Caches status and pushes updates to WebSocket subscribers
    - Handles sync (autodetect + polling)
    """
    
    def __init__(
        self,
        poll_interval_ms: int = 750,
        sync_enabled: bool = True,
        source_index: int = 0,
    ):
        self._rigs: List[RigClient] = []
        self._status_cache: Dict[int, RigStatus] = {}
        self._ws_subscribers: Set[asyncio.Queue] = set()
        
        # Sync configuration
        self.poll_interval_ms = poll_interval_ms
        self.sync_enabled = sync_enabled
        self.source_index = source_index
        self.rigctl_to_main_enabled: bool = True
        
        # Pending request tracking for request/response correlation
        self._pending: Dict[str, asyncio.Future] = {}
        
        # Background tasks
        self._poll_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Last known state for sync change detection
        self._last_sync_state: tuple = (None, None, None)
    
    def set_rigs(self, rigs: List[RigClient]) -> None:
        """Set the list of RigClients to manage."""
        self._rigs = rigs
        self._status_cache = {i: RigStatus() for i in range(len(rigs))}
    
    @property
    def rigs(self) -> List[RigClient]:
        return self._rigs
    
    async def start(self) -> None:
        """Start the router's background tasks."""
        if self._running:
            return
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
    
    async def stop(self) -> None:
        """Stop the router's background tasks."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
    
    def subscribe_ws(self) -> asyncio.Queue:
        """Subscribe to status updates. Returns a queue that receives status dicts."""
        q: asyncio.Queue = asyncio.Queue(maxsize=10)
        self._ws_subscribers.add(q)
        return q
    
    def unsubscribe_ws(self, q: asyncio.Queue) -> None:
        """Unsubscribe from status updates."""
        self._ws_subscribers.discard(q)
    
    async def _broadcast_status(self) -> None:
        """Push current status to all WebSocket subscribers."""
        status = await self.get_full_status()
        dead_queues = []
        
        for q in self._ws_subscribers:
            try:
                # Non-blocking put, drop if queue is full
                q.put_nowait(status)
            except asyncio.QueueFull:
                pass
            except Exception:
                dead_queues.append(q)
        
        for q in dead_queues:
            self._ws_subscribers.discard(q)
    
    async def get_full_status(self) -> Dict[str, Any]:
        """Get full status for all rigs.
        
        Uses rig.safe_status() which has its own caching. The router's cache
        is primarily for detecting changes to trigger WebSocket broadcasts.
        """
        rigs_status = []
        for idx, rig in enumerate(self._rigs):
            rig_data = await rig.safe_status()
            rig_data["index"] = idx
            rigs_status.append(rig_data)
        
        return {
            "rigs": rigs_status,
            "sync_enabled": self.sync_enabled,
            "sync_source_index": self.source_index,
            "rigctl_to_main_enabled": self.rigctl_to_main_enabled,
            "all_rigs_enabled": bool(rigs_status) and all(
                r.get("enabled", True) is not False for r in rigs_status
            ),
        }
    
    async def submit(
        self,
        cmd: HamlibCommand,
        rig_index: Optional[int] = None,
        broadcast: bool = False,
    ) -> HamlibResponse:
        """Submit a command and await response.
        
        Args:
            cmd: The command to execute.
            rig_index: Target rig index. If None, uses source_index.
            broadcast: If True, send to all enabled rigs (for sync).
            
        Returns:
            Response from the rig (or first rig if broadcast).
        """
        # Assign request ID if not present
        if not cmd.request_id:
            cmd.request_id = str(uuid.uuid4())
        
        if broadcast:
            return await self._broadcast_command(cmd)
        
        # Determine target rig
        idx = rig_index if rig_index is not None else self.source_index
        if idx < 0 or idx >= len(self._rigs):
            return BaseResponse(
                cmd=cmd.cmd,
                request_id=cmd.request_id,
                result=-11,
                raw_response="Invalid rig index",
            )
        
        rig = self._rigs[idx]
        resp = await self._execute_on_rig(rig, cmd, idx)
        
        # Handle sync: if this is a set command to the source rig, broadcast
        if self.sync_enabled and idx == self.source_index:
            if isinstance(cmd, (SetFreq, SetMode)):
                await self._sync_from_command(cmd)
        
        return resp
    
    async def _execute_on_rig(
        self,
        rig: RigClient,
        cmd: HamlibCommand,
        rig_index: int,
    ) -> HamlibResponse:
        """Execute a command on a specific rig and update cache."""
        resp = await rig.execute(cmd)
        
        # Update cache
        cached = self._status_cache.get(rig_index)
        if cached:
            changed = cached.update_from_response(resp)
            if changed:
                await self._broadcast_status()
        
        return resp
    
    async def _broadcast_command(self, cmd: HamlibCommand) -> HamlibResponse:
        """Send command to all enabled follower rigs."""
        tasks = []
        first_resp: Optional[HamlibResponse] = None
        
        for idx, rig in enumerate(self._rigs):
            if not getattr(rig.cfg, "enabled", True):
                continue
            if not getattr(rig.cfg, "follow_main", True):
                continue
            
            tasks.append(self._execute_on_rig(rig, cmd, idx))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, BaseResponse) and r.result == 0:
                    first_resp = r
                    break
            if first_resp is None and results:
                first_resp = results[0] if isinstance(results[0], BaseResponse) else None
        
        return first_resp or BaseResponse(
            cmd=cmd.cmd,
            request_id=cmd.request_id,
            result=-11,
            raw_response="No rigs available",
        )
    
    async def _sync_from_command(self, cmd: HamlibCommand) -> None:
        """Broadcast a set command to follower rigs (autodetect sync)."""
        for idx, rig in enumerate(self._rigs):
            if idx == self.source_index:
                continue
            if not getattr(rig.cfg, "enabled", True):
                continue
            if not getattr(rig.cfg, "follow_main", True):
                continue
            
            try:
                await rig.execute(cmd)
            except Exception:
                pass
    
    async def _poll_loop(self) -> None:
        """Background polling loop for detecting direct rig changes."""
        while self._running:
            try:
                interval = max(0.1, self.poll_interval_ms / 1000.0)
                await asyncio.sleep(interval)
                
                # Check capabilities for all rigs
                for rig in self._rigs:
                    if getattr(rig.cfg, "enabled", True):
                        try:
                            await rig.check_and_refresh_caps()
                        except Exception:
                            pass
                
                if not self.sync_enabled:
                    # Still update status cache even if sync disabled
                    await self._update_all_status()
                    continue
                
                # Poll source rig for sync
                await self._poll_source_for_sync()
                
            except asyncio.CancelledError:
                raise
            except Exception:
                continue
    
    async def _update_all_status(self) -> None:
        """Update status cache for all rigs."""
        for idx, rig in enumerate(self._rigs):
            if not getattr(rig.cfg, "enabled", True):
                continue
            try:
                status = await rig.status()
                cached = self._status_cache.get(idx)
                if cached:
                    cached.connected = status.connected
                    cached.frequency_hz = status.frequency_hz
                    cached.mode = status.mode
                    cached.passband = status.passband
                    cached.error = status.error
                    cached.last_update = time.time()
            except Exception:
                pass
    
    async def _poll_source_for_sync(self) -> None:
        """Poll the source rig and sync to followers if changed."""
        if not self._rigs:
            return
        
        # Validate source index
        enabled_idxs = [
            i for i, r in enumerate(self._rigs)
            if getattr(r.cfg, "enabled", True)
        ]
        if not enabled_idxs:
            return
        
        src_idx = max(0, min(self.source_index, len(self._rigs) - 1))
        if src_idx not in enabled_idxs:
            src_idx = enabled_idxs[0]
        
        src = self._rigs[src_idx]
        status = await src.status()
        
        if not status.connected or status.frequency_hz is None:
            return
        
        freq = status.frequency_hz
        mode = status.mode
        pb = status.passband
        
        current_state = (freq, mode, pb)
        if current_state == self._last_sync_state:
            return
        
        # State changed - sync to followers
        for idx, rig in enumerate(self._rigs):
            if idx == src_idx:
                continue
            if not getattr(rig.cfg, "enabled", True):
                continue
            if not getattr(rig.cfg, "follow_main", True):
                continue
            
            try:
                rig._last_error = None
                if freq is not None:
                    freq_ok = await rig.set_frequency(freq)
                    if not freq_ok:
                        rig._last_error = "Frequency out of configured band ranges"
                if mode is not None:
                    mode_ok = await rig.set_mode(mode, pb)
                    if not mode_ok and rig._last_error is None:
                        rig._last_error = "Failed to set mode"
            except Exception:
                pass
        
        self._last_sync_state = current_state
        await self._broadcast_status()
