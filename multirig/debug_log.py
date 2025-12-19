from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional


@dataclass
class DebugEvent:
    ts: float
    kind: str
    data: Dict[str, Any]


class DebugLog:
    def __init__(self, maxlen: int = 200):
        self._events: Deque[DebugEvent] = deque(maxlen=maxlen)

    def add(self, kind: str, **data: Any) -> None:
        self._events.append(DebugEvent(ts=time.time(), kind=kind, data=data))

    def snapshot(self) -> List[Dict[str, Any]]:
        return [
            {
                "ts": e.ts,
                "kind": e.kind,
                **e.data,
            }
            for e in list(self._events)
        ]


class DebugStore:
    def __init__(self, rig_count: int, *, rig_maxlen: int = 3000, server_maxlen: int = 400):
        self.server = DebugLog(maxlen=server_maxlen)
        self.rigs: List[DebugLog] = [DebugLog(maxlen=rig_maxlen) for _ in range(max(0, rig_count))]

    def ensure_rigs(self, rig_count: int, *, rig_maxlen: int = 3000) -> None:
        if rig_count < 0:
            rig_count = 0
        while len(self.rigs) < rig_count:
            self.rigs.append(DebugLog(maxlen=rig_maxlen))
        if len(self.rigs) > rig_count:
            self.rigs = self.rigs[:rig_count]

    def rig(self, idx: int) -> Optional[DebugLog]:
        if idx < 0 or idx >= len(self.rigs):
            return None
        return self.rigs[idx]
