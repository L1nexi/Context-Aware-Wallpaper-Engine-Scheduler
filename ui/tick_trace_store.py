from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass

from core.models.trace import TickTrace


@dataclass(frozen=True)
class TickTraceWindow:
    live_tick_id: int | None
    traces: list[TickTrace]


class TickTraceStore:
    def __init__(self, tick_history: int = 1200):
        self._lock = threading.Lock()
        self._ticks: deque[TickTrace] = deque(maxlen=tick_history)
        self._live_tick_id: int | None = None

    def update(self, trace: TickTrace) -> None:
        with self._lock:
            self._ticks.append(trace)
            self._live_tick_id = trace.tick_id

    def read_window(self, count: int | None = None) -> TickTraceWindow:
        with self._lock:
            items = list(self._ticks)
            live_tick_id = self._live_tick_id
            if count is not None:
                items = items[-count:]
        return TickTraceWindow(live_tick_id=live_tick_id, traces=items)
