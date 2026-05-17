from __future__ import annotations

import logging

from core.context import Context
from core.controller import SchedulingController
from core.diagnostics import (
    ActionReasonCode,
    ActionKind,
    ActuationOutcome,
    ControllerDecision,
    MatchEvaluation,
)
from core.event_logger import EventLogger, EventType
from core.executor import WEExecutor
from core.playlist_state import PlaylistRecoveryReason

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
        effective_playlist: str,
    ) -> ActuationOutcome:
        decision = self.controller.decide_action(
            context,
            match,
            effective_playlist,
        )
        return self._act_from_decision(match, effective_playlist, decision)

    def act_manual(
        self,
        match: MatchEvaluation,
        effecitve_playlist: str,
    ) -> ActuationOutcome:
        decision = self.controller.decide_manual_action(
            match,
            effecitve_playlist,
        )
        return self._act_from_decision(match, effecitve_playlist, decision)

    def act_recovery(
        self,
        match: MatchEvaluation,
        effecitve_playlist: str,
        recovery_reason: PlaylistRecoveryReason,
    ) -> ActuationOutcome:
        matched_playlist = match.best_playlist
        if matched_playlist is None:
            decision = ControllerDecision(
                kind=ActionKind.NONE if not effecitve_playlist else ActionKind.HOLD,
                reason_code=ActionReasonCode.RECOVERY_NO_MATCH,
                matched_playlist=None,
            )
            return self._act_from_decision(match, effecitve_playlist, decision)

        reason_code = (
            ActionReasonCode.RECOVERY_NO_PLAYLIST
            if recovery_reason == PlaylistRecoveryReason.NO_PLAYLIST
            else ActionReasonCode.RECOVERY_UNMANAGED_PLAYLIST
        )
        decision = ControllerDecision(
            kind=ActionKind.SWITCH,
            reason_code=reason_code,
            matched_playlist=matched_playlist,
        )
        return self._act_from_decision(match, effecitve_playlist, decision)

    def _act_from_decision(
        self,
        match: MatchEvaluation,
        effecitve_playlist: str,
        decision: ControllerDecision,
    ) -> ActuationOutcome:
        matched_playlist = decision.matched_playlist
        active_playlist_after = effecitve_playlist
        executed = False

        if decision.kind == ActionKind.SWITCH and matched_playlist is not None:
            logger.info(
                "[Action] Switching Playlist from '%s' to '%s'",
                effecitve_playlist,
                matched_playlist,
            )
            _log_tags(match.raw_context_vector)
            if self.executor.open_playlist(matched_playlist):
                self.controller.notify_playlist_switch()
                active_playlist_after = matched_playlist
                executed = True
        elif decision.kind == ActionKind.CYCLE and effecitve_playlist:
            logger.info("[Action] Cycling Wallpaper in '%s'", effecitve_playlist)
            if self.executor.next_wallpaper():
                self.controller.notify_wallpaper_cycle()
                executed = True

        outcome = ActuationOutcome(
            decision=decision,
            effective_playlist_before=effecitve_playlist,
            effective_playlist_after=active_playlist_after,
            executed=executed,
        )

        if outcome.kind == ActionKind.SWITCH and matched_playlist is not None and outcome.executed:
            self._history.write(
                EventType.PLAYLIST_SWITCH,
                {
                    "playlist_from": effecitve_playlist,
                    "playlist_to": matched_playlist,
                    "tags": _tag_dict(match.raw_context_vector),
                    "similarity": round(match.similarity, 4),
                    "similarity_gap": round(match.similarity_gap, 4),
                    "max_policy_magnitude": round(match.max_policy_magnitude, 4),
                    "reason_code": outcome.reason_code.value,
                },
            )
        elif outcome.kind == ActionKind.CYCLE and outcome.executed:
            self._history.write(
                EventType.WALLPAPER_CYCLE,
                {
                    "playlist": effecitve_playlist,
                    "tags": _tag_dict(match.raw_context_vector),
                    "reason_code": outcome.reason_code.value,
                },
            )
        elif outcome.kind in {ActionKind.SWITCH, ActionKind.CYCLE} and not outcome.executed:
            self._history.write(
                EventType.ACTUATION_FAILED,
                {
                    "operation": outcome.kind.value,
                    "reason_code": outcome.reason_code.value,
                    "matched_playlist": matched_playlist,
                    "active_playlist_before": effecitve_playlist,
                },
            )

        return outcome
