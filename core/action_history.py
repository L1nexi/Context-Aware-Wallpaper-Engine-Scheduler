from __future__ import annotations

from core.diagnostics import ActionKind as Kind
from core.diagnostics import SchedulerTickTrace
from core.event_logger import EventLogger, EventType


def _sorted_tags(tags: dict[str, float], top: int = 8) -> list[tuple[str, float]]:
    return sorted(tags.items(), key=lambda x: x[1], reverse=True)[:top]


def _tag_dict(tags: dict[str, float], top: int = 8) -> dict[str, float]:
    return {k: round(v, 4) for k, v in _sorted_tags(tags, top)}


class ActionHistoryWriter:
    def __init__(self, history_logger: EventLogger):
        self._history = history_logger

    def on_tick(self, trace: SchedulerTickTrace) -> None:
        outcome = trace.action
        match = trace.match

        if outcome.kind == Kind.SWITCH and outcome.executed:
            self._history.write(
                EventType.PLAYLISTS_SWITCH,
                {
                    "playlists_from": outcome.active_playlists_before.names(),
                    "playlists_to": outcome.active_playlists_after.names(),
                    "target_playlist": outcome.target_playlist,
                    "tags": _tag_dict(match.raw_context_vector),
                    "similarity": round(match.similarity, 4),
                    "similarity_gap": round(match.similarity_gap, 4),
                    "max_policy_magnitude": round(match.max_policy_magnitude, 4),
                    "reason_code": outcome.reason_code.value,
                },
            )
        elif outcome.kind == Kind.CYCLE and outcome.executed:
            self._history.write(
                EventType.PLAYLISTS_CYCLE,
                {
                    "playlists": outcome.active_playlists_before.names(),
                    "target_playlist": outcome.target_playlist,
                    "tags": _tag_dict(match.raw_context_vector),
                    "reason_code": outcome.reason_code.value,
                },
            )
        elif outcome.kind in {Kind.SWITCH, Kind.CYCLE} and not outcome.executed:
            self._history.write(
                EventType.ACTUATION_FAILED,
                {
                    "operation": outcome.kind.value,
                    "reason_code": outcome.reason_code.value,
                    "matched_playlists": outcome.decision.matched_playlists.names(),
                    "active_playlists_before": outcome.active_playlists_before.names(),
                },
            )
