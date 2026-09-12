from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass

from core.models.trace import TickTrace


@dataclass(frozen=True)
class TickHistoryWindow:
    live_tick_id: int | None
    traces: tuple[TickTrace, ...]


class TickHistoryStore:
    def __init__(self, capacity: int = 1200):
        self._lock = threading.Lock()
        self._ticks: deque[TickTrace] = deque(maxlen=capacity)
        self._live_tick_id: int | None = None

    def update(self, trace: TickTrace) -> None:
        with self._lock:
            self._ticks.append(trace)
            self._live_tick_id = trace.tick_id

    def read_window(self, count: int | None = None) -> TickHistoryWindow:
        with self._lock:
            items = tuple(self._ticks)
            live_tick_id = self._live_tick_id
            if count is not None:
                items = items[-count:]
        return TickHistoryWindow(live_tick_id=live_tick_id, traces=items)
