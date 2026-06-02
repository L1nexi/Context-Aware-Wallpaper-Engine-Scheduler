from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from core.context import Context
from core.playlist import Playlists
from core.trace import (
    Action,
    ActionReason,
    Blocker,
    BlockerEvaluation,
    Decision,
    Match,
)
from utils.runtime_config import SchedulingConfig

logger = logging.getLogger("WEScheduler.Controller")

_REASON_PRIORITY: tuple[Blocker, ...] = (
    Blocker.COOLDOWN,
    Blocker.FULLSCREEN,
    Blocker.CPU,
    Blocker.IDLE,
)

REFERENCE_PARTIAL_OVERLAP_SCORE = 1.0 / 3.0
CONTINUITY_HOLD_TICKS = 120
CONTINUITY_DECAY_PER_TICK = 0.99
CONTINUITY_THRESHOLD = math.nextafter(
    REFERENCE_PARTIAL_OVERLAP_SCORE * (CONTINUITY_DECAY_PER_TICK**CONTINUITY_HOLD_TICKS),
    math.inf,
)


class DecisionMode(StrEnum):
    NORMAL = "normal"
    MANUAL = "manual"
    RECOVERY = "recovery"
    PAUSE = "pause"


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


def _blocked_reason(
    blockers: list[Blocker],
    intent: Intent,
) -> ActionReason:
    for blocker in _REASON_PRIORITY:
        if blocker not in blockers:
            continue
        if intent == Intent.SWITCH:
            mapping = {
                Blocker.COOLDOWN: ActionReason.SWITCH_BLOCKED_COOLDOWN,
                Blocker.FULLSCREEN: ActionReason.SWITCH_BLOCKED_FULLSCREEN,
                Blocker.CPU: ActionReason.SWITCH_BLOCKED_CPU,
                Blocker.IDLE: ActionReason.SWITCH_BLOCKED_NOT_IDLE,
            }
        else:
            mapping = {
                Blocker.COOLDOWN: ActionReason.CYCLE_BLOCKED_COOLDOWN,
                Blocker.FULLSCREEN: ActionReason.CYCLE_BLOCKED_FULLSCREEN,
                Blocker.CPU: ActionReason.CYCLE_BLOCKED_CPU,
                Blocker.IDLE: ActionReason.CYCLE_BLOCKED_NOT_IDLE,
            }
        return mapping[blocker]
    return ActionReason.HOLD_SAME_PLAYLIST


class Decisions:
    @staticmethod
    def make(
        action: Action,
        reason: ActionReason,
        matched: Playlists,
        evaluation: BlockerEvaluation | None = None,
    ) -> Decision:
        return Decision(
            action=action,
            reason=reason,
            matched=matched,
            evaluation=evaluation,
        )

    @classmethod
    def no_match(cls, active: Playlists) -> Decision:
        return cls.make(
            Action.HOLD if active else Action.NONE,
            ActionReason.NO_MATCH,
            Playlists([]),
        )

    @classmethod
    def allowed(
        cls,
        intent: Intent,
        matched: Playlists,
        evaluation: BlockerEvaluation,
    ) -> Decision:
        if intent == Intent.SWITCH:
            return cls.make(Action.SWITCH, ActionReason.SWITCH_ALLOWED, matched, evaluation)
        else:
            return cls.make(Action.CYCLE, ActionReason.CYCLE_ALLOWED, matched, evaluation)

    @classmethod
    def blocked(
        cls,
        intent: Intent,
        matched: Playlists,
        evaluation: BlockerEvaluation,
    ) -> Decision:
        return cls.make(
            Action.HOLD,
            _blocked_reason(evaluation.blocked_by, intent),
            matched,
            evaluation,
        )

    @classmethod
    def hold(
        cls,
        reason: ActionReason,
        matched: Playlists,
        evaluation: BlockerEvaluation | None = None,
    ) -> Decision:
        return cls.make(Action.HOLD, reason, matched, evaluation)

    @classmethod
    def manual_apply(cls, matched: Playlists, active: Playlists) -> Decision:
        if not matched:
            return cls.no_match(active)
        if matched != active:
            return cls.make(Action.SWITCH, ActionReason.MANUAL_APPLY_REQUESTED, matched)
        if active:
            return cls.make(Action.CYCLE, ActionReason.MANUAL_APPLY_REQUESTED, matched)
        return cls.hold(ActionReason.HOLD_SAME_PLAYLIST, matched)

    @classmethod
    def recovery(
        cls,
        matched: Playlists,
        active: Playlists,
    ) -> Decision:
        if not matched:
            return cls.make(
                Action.HOLD if active else Action.NONE,
                ActionReason.RECOVERY_NO_MATCH,
                Playlists([]),
            )
        return cls.make(Action.SWITCH, ActionReason.RECOVERY_UNMANAGED, matched)

    @classmethod
    def pause(cls, matched: Playlists) -> Decision:
        return cls.make(
            Action.PAUSE,
            ActionReason.SCHEDULER_PAUSED,
            matched,
        )


class SchedulingController:
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

        if intent == Intent.SWITCH:
            cooldown_remaining = 0.0
        else:
            cooldown_remaining = max(0.0, self.cycle_cooldown - time_since_last)

        if cooldown_remaining > 0 and Blocker.COOLDOWN not in blocked_by:
            blocked_by.append(Blocker.COOLDOWN)

        idle_seconds = context.idle
        if intent == Intent.SWITCH:
            idle_ready = idle_seconds >= self.idle_threshold
            force_ready = time_since_last >= self.force_after
            if not idle_ready and not force_ready:
                blocked_by.append(Blocker.IDLE)
        elif idle_seconds < self.idle_threshold:
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

    def decide_action(
        self,
        mode: DecisionMode,
        match: Match,
        active_playlists: Playlists,
        context: Context | None = None,
    ) -> Decision:
        if mode == DecisionMode.NORMAL:
            if context is None:
                raise ValueError("context is required for normal scheduling decisions")
            return self._decide_normal(context, match, active_playlists)
        if mode == DecisionMode.MANUAL:
            return Decisions.manual_apply(match.best_playlists, active_playlists)
        if mode == DecisionMode.RECOVERY:
            return Decisions.recovery(match.best_playlists, active_playlists)
        if mode == DecisionMode.PAUSE:
            return Decisions.pause(match.best_playlists)

    def _decide_normal(
        self,
        context: Context,
        match: Match,
        active_playlists: Playlists,
    ) -> Decision:
        matched = match.best_playlists

        if not matched:
            self.semantic_continuity_score = 0.0
            return Decisions.no_match(active_playlists)

        if matched == active_playlists:
            self.semantic_continuity_score = 1.0
            intent = Intent.CYCLE
        else:
            overlap_score = weighted_jaccard(matched, active_playlists)
            # TODO 采用更合理的可缩放函数。目前的衰减值 0.99^120 ≈ 0.3。可以考虑用更明确的函数（如指数衰减）来控制
            self.semantic_continuity_score *= CONTINUITY_DECAY_PER_TICK

            is_continuous = self.semantic_continuity_score * overlap_score > CONTINUITY_THRESHOLD
            intent = Intent.CYCLE if is_continuous else Intent.SWITCH

        evaluation = self._evaluate_blockers(context, intent)
        if evaluation.allowed:
            return Decisions.allowed(intent, matched, evaluation)
        else:
            return Decisions.blocked(intent, matched, evaluation)

    def _evaluate_gates(self, context: Context) -> list[Blocker]:
        blocked_by: list[Blocker] = []
        for gate in self._gates:
            blocker = gate.evaluate(context)
            if blocker is not None:
                blocked_by.append(blocker)
        return blocked_by

    def notify_executed(self, decision: Decision) -> None:
        self.last_action_time = self._clock()
        plain_cycle = decision.action == Action.CYCLE and decision.reason == ActionReason.CYCLE_ALLOWED
        if not plain_cycle:
            self.semantic_continuity_score = 1.0

    def export_state(self) -> dict[str, Any]:
        return {
            "last_action_time": self.last_action_time,
            "semantic_continuity_score": self.semantic_continuity_score,
        }

    def import_state(self, state: dict[str, Any]) -> None:
        self.last_action_time = state.get("last_action_time", self.last_action_time)
        self.semantic_continuity_score = state.get("semantic_continuity_score", self.semantic_continuity_score)


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
