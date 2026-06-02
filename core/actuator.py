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
from core.executor import WEExecutor
from core.playlist import Playlists

logger = logging.getLogger("WEScheduler.Actuator")

ActuatorAction = ControllerAction


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
    ):
        self.executor = executor
        self.controller = controller

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
        return self._act_from_decision(active_playlists, decision)

    def _act_from_decision(
        self,
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
        executed = bool(self.executor.open_playlist(target_playlist))

        active_playlists_after = active_playlists
        if executed:
            self.controller.notify_executed(decision)
            if decision.kind == Kind.SWITCH:
                active_playlists_after = decision.matched_playlists
        return Outcomes.make(decision, active_playlists, active_playlists_after, target_playlist, executed)
