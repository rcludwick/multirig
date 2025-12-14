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
                src_idx = max(0, min(self.source_index, len(self.rigs) - 1))
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
                for i, rig in enumerate(self.rigs):
                    if i == src_idx:
                        continue
                    if freq is not None:
                        try:
                            await rig.set_frequency(freq)
                        except Exception:
                            pass
                    if mode is not None:
                        try:
                            await rig.set_mode(mode, pb)
                        except Exception:
                            pass

                self._last = (freq, mode, pb)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Swallow errors; continue loop
                continue
