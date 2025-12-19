from __future__ import annotations

import asyncio
from typing import Optional, List, Tuple

from .rig import RigClient


class SyncService:
    """Broadcast changes from a source rig to all other rigs."""

    def __init__(self, rigs: List[RigClient], interval_ms: int = 750, *, enabled: bool = True, source_index: int = 0):
        self.rigs: List[RigClient] = rigs
        self.interval_ms = interval_ms
        self._task: Optional[asyncio.Task] = None
        self.enabled: bool = enabled
        self.source_index: int = source_index
        # cache of last (freq, mode, pb) to debounce
        self._last: Tuple[Optional[int], Optional[str], Optional[int]] = (None, None, None)

    async def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self):
        interval = max(0.1, self.interval_ms / 1000.0)
        while True:
            try:
                await asyncio.sleep(interval)
                if not self.enabled:
                    continue

                # validate source index
                if not self.rigs:
                    continue
                enabled_idxs = [i for i, r in enumerate(self.rigs) if getattr(r.cfg, "enabled", True)]
                if not enabled_idxs:
                    continue
                src_idx = max(0, min(self.source_index, len(self.rigs) - 1))
                if src_idx not in enabled_idxs:
                    src_idx = enabled_idxs[0]
                src = self.rigs[src_idx]

                status_src = await src.status()
                if not status_src.connected or status_src.frequency_hz is None:
                    continue

                freq = status_src.frequency_hz
                mode = status_src.mode
                pb = status_src.passband

                changed = (freq, mode, pb) != self._last
                if not changed:
                    continue

                # Apply to all targets except source
                tasks = []
                for i, rig in enumerate(self.rigs):
                    if i == src_idx:
                        continue
                    if not getattr(rig.cfg, "enabled", True):
                        continue
                    if not getattr(rig.cfg, "follow_main", True):
                        continue
                    
                    async def _do_update(r=rig, f=freq, m=mode, p=pb):
                        # Clear previous error on attempting sync
                        r._last_error = None
                        freq_ok = True
                        mode_ok = True
                        if f is not None:
                            # set_frequency returns False on band limit violation
                            freq_ok = await r.set_frequency(f)
                            if not freq_ok:
                                r._last_error = "Frequency out of configured band ranges for follower"
                        if m is not None:
                            mode_ok = await r.set_mode(m, p)
                            if not mode_ok and r._last_error is None: # don't overwrite freq error
                                r._last_error = "Failed to set mode for follower"
                        # If both fail and no specific error from set_frequency, set a generic one
                        if not freq_ok and not mode_ok and r._last_error is None:
                            r._last_error = "Failed to sync frequency and mode for follower"

                    tasks.append(_do_update())

                if tasks:
                    await asyncio.gather(*tasks)

                self._last = (freq, mode, pb)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Swallow errors; continue loop
                continue
