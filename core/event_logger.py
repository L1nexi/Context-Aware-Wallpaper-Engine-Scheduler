from __future__ import annotations
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class EventLogger(Protocol):
    """Structural interface for history event logging.

    Implemented by HistoryLogger in utils/ — no import dependency
    from core/ to utils/.  Dependency direction: utils → core.
    """

    def write(self, event_type: str, data: dict) -> int: ...
    def read(self, limit: int = 100, from_ts: Optional[str] = None,
             to_ts: Optional[str] = None) -> dict: ...
    @property
    def last_event_id(self) -> int: ...
