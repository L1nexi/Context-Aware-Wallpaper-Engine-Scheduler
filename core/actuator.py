from __future__ import annotations

import logging

from core.context import Context
from core.controller import ControllerAction, SchedulingController
from core.diagnostics import ActionKind as Kind
from core.diagnostics import (
    ActuationOutcome,
    ControllerDecision,
    MatchEvaluation,
)
from core.event_logger import EventLogger, EventType
from core.executor import WEExecutor
from core.playlist import Playlists

logger = logging.getLogger("WEScheduler.Actuator")

ActuatorAction = ControllerAction


def _sorted_tags(tags: dict[str, float], top: int = 8):
    return sorted(tags.items(), key=lambda x: x[1], reverse=True)[:top]


def _tag_dict(tags: dict[str, float], top: int = 8):
    return {k: round(v, 4) for k, v in _sorted_tags(tags, top)}


def _log_tags(tags: dict[str, float]):
    tag_str = ", ".join([f"{k}:{v:.2f}" for k, v in _sorted_tags(tags)])
    logger.info(f"Trigger Context: [{tag_str}]")


class Outcomes:
    @staticmethod
    def make(
        decision: ControllerDecision,
        active_playlists_before: Playlists,
        active_playlists_after: Playlists | None = None,
        target_playlist: str | None = None,
        executed: bool = False,
    ) -> ActuationOutcome:
        return ActuationOutcome(
            decision=decision,
            active_playlists_before=active_playlists_before,
            active_playlists_after=active_playlists_before if active_playlists_after is None else active_playlists_after,
            target_playlist=target_playlist,
            executed=executed,
        )


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
        action: ActuatorAction,
        *,
        match: MatchEvaluation,
        active_playlists: Playlists,
        context: Context | None = None,
    ) -> ActuationOutcome:
        decision = self.controller.decide_action(
            action,
            match=match,
            active_playlists=active_playlists,
            context=context,
        )
        return self._act_from_decision(match, active_playlists, decision)

    def _act_from_decision(
        self,
        match: MatchEvaluation,
        active_playlists: Playlists,
        decision: ControllerDecision,
    ) -> ActuationOutcome:
        target_playlists = Playlists([])
        if decision.kind == Kind.SWITCH:
            target_playlists = decision.matched_playlists
        elif decision.kind == Kind.CYCLE:
            target_playlists = active_playlists

        # No execution needed or no valid target
        if not target_playlists:
            return Outcomes.make(decision, active_playlists)

        target_playlist = target_playlists.select_target()
        logger.info("Applying playlist pool '%s' via playlist '%s'", target_playlists, target_playlist)
        _log_tags(match.raw_context_vector)
        executed = bool(self.executor.open_playlist(target_playlist))

        active_playlists_after = active_playlists
        if executed:
            self.controller.notify_executed(decision)
            if decision.kind == Kind.SWITCH:
                active_playlists_after = decision.matched_playlists
        outcome = Outcomes.make(decision, active_playlists, active_playlists_after, target_playlist, executed)
        self._write_outcome_history(outcome, match, target_playlists)
        return outcome

    def _write_outcome_history(
        self,
        outcome: ActuationOutcome,
        match: MatchEvaluation,
        target_playlists: Playlists,
    ) -> None:
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
                    "playlists": target_playlists.names(),
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
