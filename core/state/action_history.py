from __future__ import annotations

from core.models.event import EventLogger, EventType
from core.models.trace import Action, TickTrace


def _sorted_tags(tags: dict[str, float], top: int = 8) -> list[tuple[str, float]]:
    return sorted(tags.items(), key=lambda x: x[1], reverse=True)[:top]


def _tag_dict(tags: dict[str, float], top: int = 8) -> dict[str, float]:
    return {k: round(v, 4) for k, v in _sorted_tags(tags, top)}


class ActionHistoryWriter:
    def __init__(self, history_logger: EventLogger):
        self._history = history_logger

    def on_tick(self, trace: TickTrace) -> None:
        result = trace.action
        match = trace.match

        if result.action == Action.SWITCH and result.executed:
            self._history.write(
                EventType.PLAYLISTS_SWITCH,
                {
                    "playlists_from": result.active_playlists_before.names(),
                    "playlists_to": result.active_playlists_after.names(),
                    "target_playlist": result.target_playlist,
                    "tags": _tag_dict(match.raw_context_vector),
                    "similarity": round(match.similarity, 4),
                    "similarity_gap": round(match.similarity_gap, 4),
                    "max_policy_magnitude": round(match.max_policy_magnitude, 4),
                    "reason_code": result.reason.value,
                },
            )
        elif result.action == Action.CYCLE and result.executed:
            self._history.write(
                EventType.PLAYLISTS_CYCLE,
                {
                    "playlists": result.active_playlists_before.names(),
                    "target_playlist": result.target_playlist,
                    "tags": _tag_dict(match.raw_context_vector),
                    "reason_code": result.reason.value,
                },
            )
        elif result.action in {Action.SWITCH, Action.CYCLE} and not result.executed:
            self._history.write(
                EventType.ACTUATION_FAILED,
                {
                    "action": result.action.value,
                    "reason_code": result.reason.value,
                    "matched_playlists": result.decision.matched.names(),
                    "active_playlists_before": result.active_playlists_before.names(),
                },
            )
