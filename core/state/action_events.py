from __future__ import annotations

from core.models.event import EventLogger, EventType
from core.models.trace import Action, TickTrace


def _sorted_tags(tags: dict[str, float], top: int = 8) -> list[tuple[str, float]]:
    return sorted(tags.items(), key=lambda x: x[1], reverse=True)[:top]


def _tag_dict(tags: dict[str, float], top: int = 8) -> dict[str, float]:
    return {k: round(v, 4) for k, v in _sorted_tags(tags, top)}


class ActionEventWriter:
    def __init__(self, event_logger: EventLogger):
        self._events = event_logger

    def on_tick(self, trace: TickTrace) -> None:
        result = trace.action
        match = trace.match
        decision = trace.decision

        if decision.action == Action.SWITCH and result.executed:
            self._events.write(
                EventType.SCENES_SWITCH,
                {
                    "scenes_from": [scene_id.value for scene_id in trace.active_scenes.ids()],
                    "scenes_to": [scene_id.value for scene_id in trace.target.ids()],
                    "target_playlist": result.target_playlist,
                    "tags": _tag_dict(match.raw_context_vector),
                    "similarity": round(match.similarity, 4),
                    "similarity_gap": round(match.similarity_gap, 4),
                    "max_policy_magnitude": round(match.max_policy_magnitude, 4),
                },
            )
        elif decision.action == Action.CYCLE and result.executed:
            self._events.write(
                EventType.SCENES_CYCLE,
                {
                    "scenes": [scene_id.value for scene_id in trace.active_scenes.ids()],
                    "target_playlist": result.target_playlist,
                    "tags": _tag_dict(match.raw_context_vector),
                },
            )
        elif decision.action in {Action.SWITCH, Action.CYCLE} and not result.executed:
            self._events.write(
                EventType.ACTUATION_FAILED,
                {
                    "action": decision.action.value,
                    "matched_scenes": [scene_id.value for scene_id in decision.target.ids()],
                    "active_scenes": [scene_id.value for scene_id in trace.active_scenes.ids()],
                },
            )
