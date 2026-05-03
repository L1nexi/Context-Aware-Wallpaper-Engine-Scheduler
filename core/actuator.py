from __future__ import annotations

import logging

from core.context import Context
from core.controller import SchedulingController
from core.diagnostics import (
    ActionKind,
    ActuationOutcome,
    MatchEvaluation,
)
from core.event_logger import EventLogger, EventType
from core.executor import WEExecutor

logger = logging.getLogger("WEScheduler.Actuator")


def _sorted_tags(tags: dict[str, float], top: int = 8):
    return sorted(tags.items(), key=lambda x: x[1], reverse=True)[:top]


def _tag_dict(tags: dict[str, float], top: int = 8):
    return {k: round(v, 4) for k, v in _sorted_tags(tags, top)}


def _log_tags(tags: dict[str, float]):
    tag_str = ", ".join([f"{k}:{v:.2f}" for k, v in _sorted_tags(tags)])
    logger.info(f"Trigger Context: [{tag_str}]")


class Actuator:
    def __init__(
        self,
        executor: WEExecutor,
        controller: SchedulingController,
        history_logger: EventLogger,
    ):
        self.executor = executor
        self.controller = controller
        self._history: EventLogger = history_logger

    def act(
        self,
        context: Context,
        match: MatchEvaluation,
        current_playlist: str,
    ) -> ActuationOutcome:
        decision = self.controller.decide_action(
            context,
            match,
            current_playlist,
        )
        matched_playlist = decision.matched_playlist
        active_playlist_after = current_playlist
        executed = False

        if decision.kind == ActionKind.SWITCH and matched_playlist is not None:
            logger.info(
                "[Action] Switching Playlist from '%s' to '%s'",
                current_playlist,
                matched_playlist,
            )
            _log_tags(match.raw_context_vector)
            self.executor.open_playlist(matched_playlist)
            self.controller.notify_playlist_switch()
            active_playlist_after = matched_playlist
            executed = True
        elif decision.kind == ActionKind.CYCLE and current_playlist:
            logger.info("[Action] Cycling Wallpaper in '%s'", current_playlist)
            self.executor.next_wallpaper()
            self.controller.notify_wallpaper_cycle()
            executed = True

        outcome = ActuationOutcome(
            decision=decision,
            active_playlist_before=current_playlist,
            active_playlist_after=active_playlist_after,
            executed=executed,
        )

        if outcome.kind == ActionKind.SWITCH and matched_playlist is not None:
            self._history.write(
                EventType.PLAYLIST_SWITCH,
                {
                    "playlist_from": current_playlist,
                    "playlist_to": matched_playlist,
                    "tags": _tag_dict(match.raw_context_vector),
                    "similarity": round(match.similarity, 4),
                    "similarity_gap": round(match.similarity_gap, 4),
                    "max_policy_magnitude": round(match.max_policy_magnitude, 4),
                    "reason_code": outcome.reason_code.value,
                },
            )
        elif outcome.kind == ActionKind.CYCLE:
            self._history.write(
                EventType.WALLPAPER_CYCLE,
                {
                    "playlist": current_playlist,
                    "tags": _tag_dict(match.raw_context_vector),
                    "reason_code": outcome.reason_code.value,
                },
            )

        return outcome
