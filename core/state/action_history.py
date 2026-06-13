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
        decision = trace.decision

        match decision.action, result.executed:
            case Action.SWITCH, True:
                self._history.write(
                    EventType.PLAYLISTS_SWITCH,
                    {
                        "playlists_from": trace.active_playlists.names(),
                        "playlists_to": trace.target.names(),
                        "target_playlist": result.target_playlist,
                        "tags": _tag_dict(match.raw_context_vector),
                        "similarity": round(match.similarity, 4),
                        "similarity_gap": round(match.similarity_gap, 4),
                        "max_policy_magnitude": round(match.max_policy_magnitude, 4),
                    },
                )
            case Action.CYCLE, True:
                self._history.write(
                    EventType.PLAYLISTS_CYCLE,
                    {
                        "playlists": trace.active_playlists.names(),
                        "target_playlist": result.target_playlist,
                        "tags": _tag_dict(match.raw_context_vector),
                    },
                )
            case ((Action.SWITCH | Action.CYCLE), False):
                self._history.write(
                    EventType.ACTUATION_FAILED,
                    {
                        "action": decision.action.value,
                        "matched_playlists": decision.target.names(),
                        "active_playlists": trace.active_playlists.names(),
                    },
                )
