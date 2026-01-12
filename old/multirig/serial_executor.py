from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional, Tuple


WorkItem = Tuple[Callable[[], Awaitable[Any]], "asyncio.Future[Any]"]


class SerialExecutor:
    def __init__(self, *, maxsize: int = 0):
        self._maxsize = maxsize
        self._queue: Optional[asyncio.Queue[Optional[WorkItem]]] = None
        self._task: Optional[asyncio.Task[None]] = None
        self._closed = False

    def _ensure_started(self) -> None:
        loop = asyncio.get_running_loop()
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=self._maxsize)
        if self._task is None or self._task.done():
            self._task = loop.create_task(self._run())

    async def run(self, fn: Callable[[], Awaitable[Any]]) -> Any:
        if self._closed:
            raise RuntimeError("SerialExecutor is closed")
        self._ensure_started()
        assert self._queue is not None
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        await self._queue.put((fn, fut))
        return await fut

    async def close(self) -> None:
        self._closed = True
        if self._queue is None or self._task is None:
            return
        await self._queue.put(None)
        try:
            await self._task
        finally:
            self._task = None
            self._queue = None

    async def _run(self) -> None:
        assert self._queue is not None
        while True:
            item = await self._queue.get()
            if item is None:
                return
            fn, fut = item
            if fut.cancelled():
                continue
            try:
                res = await fn()
            except Exception as e:  # noqa: BLE001
                if not fut.cancelled():
                    fut.set_exception(e)
            else:
                if not fut.cancelled():
                    fut.set_result(res)
