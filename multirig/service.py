from __future__ import annotations

import asyncio
from typing import Optional

from .rig import RigClient


class SyncService:
    def __init__(self, rig_a: RigClient, rig_b: RigClient, interval_ms: int = 750):
        self.a = rig_a
        self.b = rig_b
        self.interval_ms = interval_ms
        self._task: Optional[asyncio.Task] = None
        self.enabled: bool = True
        self._last_freq: Optional[int] = None
        self._last_mode: Optional[str] = None
        self._last_pb: Optional[int] = None

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

                status_a = await self.a.status()
                if not status_a.connected or status_a.frequency_hz is None:
                    continue

                freq = status_a.frequency_hz
                mode = status_a.mode
                pb = status_a.passband

                changed = (
                    freq != self._last_freq or mode != self._last_mode or pb != self._last_pb
                )
                if not changed:
                    continue

                # Apply to B
                if freq is not None:
                    try:
                        await self.b.set_frequency(freq)
                    except Exception:
                        pass
                if mode is not None:
                    try:
                        await self.b.set_mode(mode, pb)
                    except Exception:
                        pass

                self._last_freq = freq
                self._last_mode = mode
                self._last_pb = pb
            except asyncio.CancelledError:
                raise
            except Exception:
                # Swallow errors; continue loop
                continue
