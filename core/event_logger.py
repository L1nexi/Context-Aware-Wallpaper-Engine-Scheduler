from __future__ import annotations
from enum import StrEnum
from typing import Optional, Protocol, runtime_checkable


class EventType(StrEnum):
    """Tagged union discriminant for history events.

    Shared by scheduler, actuator, history_logger, and the frontend
    TypeScript types.  Adding a new event type only requires adding
    a member here — all consumers update from this single source.
    """
    START = "start"
    STOP = "stop"
    PAUSE = "pause"
    RESUME = "resume"
    PLAYLIST_SWITCH = "playlist_switch"
    WALLPAPER_CYCLE = "wallpaper_cycle"


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
