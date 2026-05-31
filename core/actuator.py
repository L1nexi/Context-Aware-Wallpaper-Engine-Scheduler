from __future__ import annotations

import logging

from core.context import Context
from core.controller import SchedulingController
from core.diagnostics import (
    ActionKind,
    ActionReasonCode,
    ActuationOutcome,
    ControllerDecision,
    MatchEvaluation,
)
from core.event_logger import EventLogger, EventType
from core.executor import WEExecutor
from core.playlist import Playlists
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
        effective_playlists: Playlists,
    ) -> ActuationOutcome:
        decision = self.controller.decide_action(context, match, effective_playlists)
        return self._act_from_decision(match, effective_playlists, decision)

    def act_manual(
        self,
        match: MatchEvaluation,
        effective_playlists: Playlists,
    ) -> ActuationOutcome:
        decision = self.controller.decide_manual_action(match, effective_playlists)
        return self._act_from_decision(match, effective_playlists, decision)

    def act_recovery(
        self,
        match: MatchEvaluation,
        effective_playlists: Playlists,
        recovery_reason: PlaylistRecoveryReason,
    ) -> ActuationOutcome:
        matched = match.best_playlists
        if not matched:
            decision = ControllerDecision(
                kind=ActionKind.NONE if not effective_playlists else ActionKind.HOLD,
                reason_code=ActionReasonCode.RECOVERY_NO_MATCH,
                matched_playlists=Playlists([]),
            )
            return self._act_from_decision(match, effective_playlists, decision)

        reason_code = (
            ActionReasonCode.RECOVERY_NO_PLAYLIST
            if recovery_reason == PlaylistRecoveryReason.NO_PLAYLIST
            else ActionReasonCode.RECOVERY_UNMANAGED_PLAYLIST
        )
        decision = ControllerDecision(
            kind=ActionKind.SWITCH,
            reason_code=reason_code,
            matched_playlists=matched,
        )
        return self._act_from_decision(match, effective_playlists, decision)

    def _act_from_decision(
        self,
        match: MatchEvaluation,
        effective_playlists: Playlists,
        decision: ControllerDecision,
    ) -> ActuationOutcome:
        matched = decision.matched_playlists
        if not matched:
            return ActuationOutcome(
                decision=decision,
                effective_playlists_before=effective_playlists,
                effective_playlists_after=effective_playlists,
                target_playlist=None,
                executed=False,
            )

        target = matched.select_target()
        effective_playlists_after = effective_playlists
        executed = False

        if decision.kind == ActionKind.SWITCH:
            logger.info("[Action] Switching Playlist from '%s' to '%s'", effective_playlists, target)
            _log_tags(match.raw_context_vector)
            if self.executor.open_playlist(target):
                self.controller.notify_action()
                effective_playlists_after = Playlists([target])
                executed = True

        elif decision.kind == ActionKind.CYCLE:
            if Playlists([target]) == effective_playlists:
                # Target is current playlist -> nextWallpaper
                logger.info("[Action] Cycling Wallpaper in '%s'", target)
                if self.executor.next_wallpaper():
                    self.controller.notify_action()
                    executed = True
            else:
                # Target differs from current -> openPlaylist (cycle semantic expansion)
                logger.info("[Action] Cycling to different playlist '%s' from '%s'", target, effective_playlists)
                if self.executor.open_playlist(target):
                    self.controller.notify_action()
                    effective_playlists_after = Playlists([target])
                    executed = True

        outcome = ActuationOutcome(
            decision=decision,
            effective_playlists_before=effective_playlists,
            effective_playlists_after=effective_playlists_after,
            target_playlist=target,
            executed=executed,
        )

        if outcome.kind == ActionKind.SWITCH and executed:
            self._history.write(
                EventType.PLAYLIST_SWITCH,
                {
                    "playlist_from": effective_playlists.names(),
                    "playlist_to": [target],
                    "tags": _tag_dict(match.raw_context_vector),
                    "similarity": round(match.similarity, 4),
                    "similarity_gap": round(match.similarity_gap, 4),
                    "max_policy_magnitude": round(match.max_policy_magnitude, 4),
                    "reason_code": outcome.reason_code.value,
                },
            )
        elif outcome.kind == ActionKind.CYCLE and executed:
            self._history.write(
                EventType.WALLPAPER_CYCLE,
                {
                    "playlist": target,
                    "tags": _tag_dict(match.raw_context_vector),
                    "reason_code": outcome.reason_code.value,
                },
            )
        elif outcome.kind in {ActionKind.SWITCH, ActionKind.CYCLE} and not executed:
            self._history.write(
                EventType.ACTUATION_FAILED,
                {
                    "operation": outcome.kind.value,
                    "reason_code": outcome.reason_code.value,
                    "matched_playlists": matched.names(),
                    "effective_playlists_before": effective_playlists.names(),
                },
            )

        return outcome
