from __future__ import annotations

import logging

from core.context import Context
from core.controller import DecisionMode, SchedulingController
from core.executor import WEExecutor
from core.playlist import Playlists
from core.trace import (
    Action,
    ActionResult,
    Decision,
    Match,
)

logger = logging.getLogger("WEScheduler.Actuator")


class ActResult:
    @staticmethod
    def make(
        decision: Decision,
        active_playlists_before: Playlists,
        active_playlists_after: Playlists | None = None,
        target_playlist: str | None = None,
        executed: bool = False,
    ) -> ActionResult:
        return ActionResult(
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
        mode: DecisionMode,
        match: Match,
        active_playlists: Playlists,
        context: Context,
    ) -> ActionResult:
        decision = self.controller.decide_action(mode, match, active_playlists, context)
        return self._act_from_decision(active_playlists, decision)

    def _act_from_decision(
        self,
        active_playlists: Playlists,
        decision: Decision,
    ) -> ActionResult:
        target_playlists = Playlists()
        if decision.action == Action.SWITCH:
            target_playlists = decision.matched
        elif decision.action == Action.CYCLE:
            target_playlists = active_playlists

        # No execution needed or no valid target
        if not target_playlists:
            return ActResult.make(decision, active_playlists)

        target_playlist = target_playlists.select_target()
        logger.info("Applying playlist pool '%s' via playlist '%s'", target_playlists, target_playlist)
        executed = bool(self.executor.open_playlist(target_playlist))

        active_playlists_after = active_playlists
        if executed:
            self.controller.notify_executed(decision)
            if decision.action == Action.SWITCH:
                active_playlists_after = decision.matched
        return ActResult.make(decision, active_playlists, active_playlists_after, target_playlist, executed)
