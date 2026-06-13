from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from configurations.runtime_models import SchedulingConfig
from core.models.context import Context
from core.models.playlist import Playlists
from core.models.trace import (
    Action,
    ActPlan,
    Blocker,
    BlockerEvaluation,
    Decision,
    DecisionMode,
    Match,
)

logger = logging.getLogger("WEScheduler.Controller")

CONTINUITY_REFERENCE_OVERLAP = 1.0 / 3.0
CONTINUITY_REFERENCE_HOLD_TICKS = 120
CONTINUITY_THRESHOLD = 0.2

CONTINUITY_DECAY_PER_TICK = (CONTINUITY_THRESHOLD / CONTINUITY_REFERENCE_OVERLAP) ** (1.0 / CONTINUITY_REFERENCE_HOLD_TICKS)
CONTINUITY_SWITCH_BOUNDARY = math.nextafter(
    CONTINUITY_REFERENCE_OVERLAP * (CONTINUITY_DECAY_PER_TICK**CONTINUITY_REFERENCE_HOLD_TICKS),
    math.inf,
)


class Intent(StrEnum):
    SWITCH = "switch"
    CYCLE = "cycle"


class CpuGate:
    def __init__(self, threshold: float):
        self.threshold = threshold

    def evaluate(self, context: Context) -> Blocker | None:
        if self.threshold > 0 and context.cpu >= self.threshold:
            logger.debug(
                "CPU gate: %.1f%% >= %.0f%%, deferring",
                context.cpu,
                self.threshold,
            )
            return Blocker.CPU
        return None


class FullscreenGate:
    def evaluate(self, context: Context) -> Blocker | None:
        if context.fullscreen:
            logger.debug("Fullscreen gate: deferring switch")
            return Blocker.FULLSCREEN
        return None


class Decisions:
    @staticmethod
    def make(
        action: Action,
        target: Playlists,
        evaluation: BlockerEvaluation | None = None,
        semantic_continuity: bool = False,
    ) -> Decision:
        return Decision(
            action=action,
            target=target,
            evaluation=evaluation,
            semantic_continuity=semantic_continuity,
        )

    @classmethod
    def no_match(cls, active: Playlists) -> Decision:
        return cls.make(
            Action.HOLD if active else Action.NONE,
            Playlists(),
        )

    @classmethod
    def allowed(
        cls,
        intent: Intent,
        matched: Playlists,
        evaluation: BlockerEvaluation,
        active_playlists: Playlists,
        semantic_continuity: bool = False,
    ) -> Decision:
        target = matched if intent == Intent.SWITCH else active_playlists
        action = Action.SWITCH if intent == Intent.SWITCH else Action.CYCLE
        return cls.make(action, target, evaluation, semantic_continuity)

    @classmethod
    def blocked(
        cls,
        intent: Intent,
        matched: Playlists,
        evaluation: BlockerEvaluation,
        active_playlists: Playlists,
        semantic_continuity: bool = False,
    ) -> Decision:
        target = matched if intent == Intent.SWITCH else active_playlists
        return cls.make(Action.HOLD, target, evaluation, semantic_continuity)

    @classmethod
    def pause(cls, target: Playlists) -> Decision:
        return cls.make(Action.PAUSE, target)


class Controller:
    def __init__(self, config: SchedulingConfig, clock: Callable[[], float] | None = None):
        self._clock = clock if clock is not None else time.monotonic
        self.idle_threshold = config.idle_threshold
        self.force_after = config.force_after
        self.cycle_cooldown = config.cycle_cooldown
        self.cpu_threshold = config.cpu_threshold
        self.pause_on_fullscreen = config.pause_on_fullscreen

        startup_delay = max(config.startup_delay, 0)
        now = self._clock()
        self.startup_end = now + startup_delay
        self.last_action_time = now
        self._gates: list[CpuGate | FullscreenGate] = []
        if self.cpu_threshold > 0:
            self._gates.append(CpuGate(self.cpu_threshold))
        if self.pause_on_fullscreen:
            self._gates.append(FullscreenGate())
        self.semantic_continuity_score = 1.0

    def decide_action(
        self,
        plan: ActPlan,
        context: Context,
        match: Match,
    ) -> Decision:
        match plan.mode:
            case DecisionMode.NORMAL:
                return self._decide_normal(match, plan.active_playlists, context)
            case DecisionMode.MANUAL:
                return self._decide_manual(match, plan.active_playlists)
            case DecisionMode.RECOVERY:
                return self._decide_recovery(match, plan.active_playlists)
            case DecisionMode.PAUSE:
                return self._decide_pause(match)

    def _decide_normal(
        self,
        match: Match,
        active_playlists: Playlists,
        context: Context,
    ) -> Decision:
        matched = match.best_playlists

        if not matched:
            self.semantic_continuity_score = 0.0
            return Decisions.no_match(active_playlists)

        if matched == active_playlists:
            self.semantic_continuity_score = 1.0
            intent = Intent.CYCLE
            semantic_continuity = False
        else:
            overlap_score = weighted_jaccard(matched, active_playlists)
            self.semantic_continuity_score *= CONTINUITY_DECAY_PER_TICK
            is_continuous = self.semantic_continuity_score * overlap_score > CONTINUITY_SWITCH_BOUNDARY
            intent = Intent.CYCLE if is_continuous else Intent.SWITCH
            semantic_continuity = is_continuous

        evaluation = self._evaluate_blockers(context, intent)
        if evaluation.allowed:
            return Decisions.allowed(intent, matched, evaluation, active_playlists, semantic_continuity)
        return Decisions.blocked(intent, matched, evaluation, active_playlists, semantic_continuity)

    def _decide_manual(
        self,
        match: Match,
        active_playlists: Playlists,
    ) -> Decision:
        matched = match.best_playlists

        if not matched:
            self.semantic_continuity_score = 0.0
            return Decisions.no_match(active_playlists)

        if matched == active_playlists:
            self.semantic_continuity_score = 1.0
            return Decisions.make(Action.CYCLE, active_playlists)

        self.semantic_continuity_score = 1.0
        return Decisions.make(Action.SWITCH, matched)

    def _decide_recovery(
        self,
        match: Match,
        active_playlists: Playlists,
    ) -> Decision:
        matched = match.best_playlists
        if not matched:
            return Decisions.make(
                Action.HOLD if active_playlists else Action.NONE,
                Playlists(),
            )
        self.semantic_continuity_score = 1.0
        return Decisions.make(Action.SWITCH, matched)

    def _decide_pause(
        self,
        match: Match,
    ) -> Decision:
        return Decisions.pause(match.best_playlists)

    def _evaluate_blockers(
        self,
        context: Context,
        intent: Intent,
    ) -> BlockerEvaluation:
        current_time = self._clock()

        blocked_by: list[Blocker] = []
        warmup_remaining = max(0.0, self.startup_end - current_time)
        if warmup_remaining > 0:
            blocked_by.append(Blocker.COOLDOWN)
        blocked_by.extend(self._evaluate_gates(context))

        time_since_last = current_time - self.last_action_time
        force_after_remaining = max(0.0, self.force_after - time_since_last)

        match intent:
            case Intent.SWITCH:
                cooldown_remaining = 0.0
            case Intent.CYCLE:
                cooldown_remaining = max(0.0, self.cycle_cooldown - time_since_last)

        if cooldown_remaining > 0 and Blocker.COOLDOWN not in blocked_by:
            blocked_by.append(Blocker.COOLDOWN)

        idle_seconds = context.idle
        match intent:
            case Intent.SWITCH:
                idle_ready = idle_seconds >= self.idle_threshold
                force_ready = time_since_last >= self.force_after
                if not idle_ready and not force_ready:
                    blocked_by.append(Blocker.IDLE)
            case Intent.CYCLE if idle_seconds < self.idle_threshold:
                blocked_by.append(Blocker.IDLE)

        return BlockerEvaluation(
            blocked_by=blocked_by,
            cooldown_remaining=warmup_remaining if warmup_remaining > 0 else cooldown_remaining,
            idle_seconds=idle_seconds,
            idle_threshold=self.idle_threshold,
            cpu_percent=context.cpu,
            cpu_threshold=self.cpu_threshold if self.cpu_threshold > 0 else None,
            fullscreen=context.fullscreen,
            force_after_remaining=force_after_remaining,
        )

    def _evaluate_gates(self, context: Context) -> list[Blocker]:
        blocked_by: list[Blocker] = []
        for gate in self._gates:
            blocker = gate.evaluate(context)
            if blocker is not None:
                blocked_by.append(blocker)
        return blocked_by

    def notify_executed(self, decision: Decision) -> None:
        self.last_action_time = self._clock()

    def export_state(self) -> dict[str, Any]:
        return {
            "last_action_time": self.last_action_time,
            "semantic_continuity_score": self.semantic_continuity_score,
            "startup_end": self.startup_end,
        }

    def import_state(self, state: dict[str, Any]) -> None:
        self.last_action_time = state.get("last_action_time", self.last_action_time)
        self.semantic_continuity_score = state.get("semantic_continuity_score", self.semantic_continuity_score)
        self.startup_end = state.get("startup_end", self.startup_end)


def weighted_jaccard(left: Playlists, right: Playlists) -> float:
    left_names = set(left.names())
    right_names = set(right.names())
    union = left_names | right_names
    intersection = left_names & right_names

    if not union:
        return 0.0

    item_counts = Playlists.managed().item_counts()
    intersection_weight = sum(math.sqrt(item_counts.get(name, 1)) for name in intersection)
    union_weight = sum(math.sqrt(item_counts.get(name, 1)) for name in union)
    return intersection_weight / union_weight
