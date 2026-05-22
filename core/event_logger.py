from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable


class EventType(StrEnum):
    START = "start"
    STOP = "stop"
    PAUSE = "pause"
    RESUME = "resume"
    PLAYLIST_SWITCH = "playlist_switch"
    WALLPAPER_CYCLE = "wallpaper_cycle"
    ACTUATION_FAILED = "actuation_failed"


@runtime_checkable
class EventLogger(Protocol):
    def write(self, event_type: str, data: dict) -> int: ...
    def read(self, limit: int = 100, from_ts: str | None = None, to_ts: str | None = None) -> dict: ...
    def aggregate(self, from_ts: str | None = None, to_ts: str | None = None, bucket_minutes: int = 60) -> dict: ...
    @property
    def last_event_id(self) -> int: ...
