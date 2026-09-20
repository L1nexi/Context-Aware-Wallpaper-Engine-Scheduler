from __future__ import annotations

import logging

from core.models.scene import Scenes
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
            target_scenes = decision.target
        else:
            target_scenes = Scenes()

        if not target_scenes:
            return ActionResult()

        target_playlist = target_scenes.select_target_playlist()
        logger.info("Applying scene pool '%s' via playlist '%s'", target_scenes, target_playlist)
        executed = bool(self.executor.open_playlist(target_playlist))

        return ActionResult(
            target_playlist=target_playlist,
            executed=executed,
        )
