from __future__ import annotations

import logging

from core.models.playlist import Playlists
from core.models.trace import (
    Action,
    ActionResult,
    Decision,
)
from core.runtime.executor import WEExecutor

logger = logging.getLogger("WEScheduler.Actuator")


class Actuator:
    def __init__(self, executor: WEExecutor):
        self.executor = executor

    def act(self, decision: Decision) -> ActionResult:
        return self._act_from_decision(decision)

    def _act_from_decision(self, decision: Decision) -> ActionResult:
        if decision.action in {Action.SWITCH, Action.CYCLE}:
            target_playlists = decision.target
        else:
            target_playlists = Playlists()

        if not target_playlists:
            return ActionResult()

        target_playlist = target_playlists.select_target()
        logger.info("Applying playlist pool '%s' via playlist '%s'", target_playlists, target_playlist)
        executed = bool(self.executor.open_playlist(target_playlist))

        return ActionResult(
            target_playlist=target_playlist,
            executed=executed,
        )
