from __future__ import annotations

import logging
import time
from typing import Any, Dict

from core.context import Context
from core.diagnostics import (
    ActionKind,
    ActionReasonCode,
    ControllerBlocker,
    ControllerDecision,
    ControllerEvaluation,
    ControllerOperation,
    MatchEvaluation,
)
from utils.runtime_config import SchedulingConfig

logger = logging.getLogger("WEScheduler.Controller")


_REASON_PRIORITY: tuple[ControllerBlocker, ...] = (
    ControllerBlocker.COOLDOWN,
    ControllerBlocker.FULLSCREEN,
    ControllerBlocker.CPU,
    ControllerBlocker.IDLE,
)


class CpuGate:
    def __init__(self, threshold: float):
        self.threshold = threshold

    def evaluate(self, context: Context) -> ControllerBlocker | None:
        if self.threshold > 0 and context.cpu >= self.threshold:
            logger.debug(
                "CPU gate: %.1f%% >= %.0f%%, deferring",
                context.cpu,
                self.threshold,
            )
            return ControllerBlocker.CPU
        return None


class FullscreenGate:
    def evaluate(self, context: Context) -> ControllerBlocker | None:
        if context.fullscreen:
            logger.debug("Fullscreen gate: deferring switch")
            return ControllerBlocker.FULLSCREEN
        return None


def _blocked_reason(
    blockers: list[ControllerBlocker],
    *,
    operation: ControllerOperation,
) -> ActionReasonCode:
    for blocker in _REASON_PRIORITY:
        if blocker not in blockers:
            continue
        if operation == "switch":
            mapping = {
                ControllerBlocker.COOLDOWN: ActionReasonCode.SWITCH_BLOCKED_COOLDOWN,
                ControllerBlocker.FULLSCREEN: ActionReasonCode.SWITCH_BLOCKED_FULLSCREEN,
                ControllerBlocker.CPU: ActionReasonCode.SWITCH_BLOCKED_CPU,
                ControllerBlocker.IDLE: ActionReasonCode.SWITCH_BLOCKED_NOT_IDLE,
            }
        else:
            mapping = {
                ControllerBlocker.COOLDOWN: ActionReasonCode.CYCLE_BLOCKED_COOLDOWN,
                ControllerBlocker.FULLSCREEN: ActionReasonCode.CYCLE_BLOCKED_FULLSCREEN,
                ControllerBlocker.CPU: ActionReasonCode.CYCLE_BLOCKED_CPU,
                ControllerBlocker.IDLE: ActionReasonCode.CYCLE_BLOCKED_NOT_IDLE,
            }
        return mapping[blocker]
    return ActionReasonCode.HOLD_SAME_PLAYLIST


class SchedulingController:
    def __init__(self, config: SchedulingConfig):
        self.idle_threshold = config.idle_threshold
        self.switch_cooldown = config.switch_cooldown
        self.force_after = config.force_after
        self.cycle_cooldown = config.cycle_cooldown
        self.cpu_threshold = config.cpu_threshold
        self.pause_on_fullscreen = config.pause_on_fullscreen

        startup_delay = min(max(config.startup_delay, 0), self.switch_cooldown)
        init_time = time.time() - (self.switch_cooldown - startup_delay)
        self.last_playlist_switch_time = init_time
        self.last_wallpaper_switch_time = init_time
        self._gates: list[CpuGate | FullscreenGate] = []
        if self.cpu_threshold > 0:
            self._gates.append(CpuGate(self.cpu_threshold))
        if self.pause_on_fullscreen:
            self._gates.append(FullscreenGate())

    def _evaluate_operation(
        self,
        context: Context,
        *,
        operation: ControllerOperation,
    ) -> ControllerEvaluation:
        current_time = time.time()
        if operation == "switch":
            time_since_last = current_time - self.last_playlist_switch_time
            cooldown_remaining = max(0.0, self.switch_cooldown - time_since_last)
            force_after_remaining = max(0.0, self.force_after - time_since_last)
        else:
            time_since_last = current_time - self.last_wallpaper_switch_time
            cooldown_remaining = max(0.0, self.cycle_cooldown - time_since_last)
            force_after_remaining = None

        blocked_by: list[ControllerBlocker] = []
        if cooldown_remaining > 0:
            blocked_by.append(ControllerBlocker.COOLDOWN)
        blocked_by.extend(self._evaluate_gates(context))

        idle_seconds = context.idle
        if operation == "switch":
            idle_ready = idle_seconds >= self.idle_threshold
            force_ready = time_since_last >= self.force_after
            if not idle_ready and not force_ready:
                blocked_by.append(ControllerBlocker.IDLE)
        elif idle_seconds < self.idle_threshold:
            blocked_by.append(ControllerBlocker.IDLE)

        return ControllerEvaluation(
            operation=operation,
            allowed=not blocked_by,
            blocked_by=blocked_by,
            cooldown_remaining=cooldown_remaining,
            idle_seconds=idle_seconds,
            idle_threshold=self.idle_threshold,
            cpu_percent=context.cpu,
            cpu_threshold=self.cpu_threshold if self.cpu_threshold > 0 else None,
            fullscreen=context.fullscreen,
            force_after_remaining=force_after_remaining,
        )

    def decide_action(
        self,
        context: Context,
        match: MatchEvaluation,
        active_playlist: str,
    ) -> ControllerDecision:
        matched_playlist = match.best_playlist

        if matched_playlist is None:
            return ControllerDecision(
                kind=ActionKind.HOLD if active_playlist else ActionKind.NONE,
                reason_code=ActionReasonCode.NO_MATCH,
                matched_playlist=None,
            )

        if matched_playlist != active_playlist:
            evaluation = self._evaluate_operation(context, operation="switch")
            if evaluation.allowed:
                return ControllerDecision(
                    kind=ActionKind.SWITCH,
                    reason_code=ActionReasonCode.SWITCH_ALLOWED,
                    matched_playlist=matched_playlist,
                    evaluation=evaluation,
                )
            return ControllerDecision(
                kind=ActionKind.HOLD,
                reason_code=_blocked_reason(evaluation.blocked_by, operation="switch"),
                matched_playlist=matched_playlist,
                evaluation=evaluation,
            )

        evaluation = self._evaluate_operation(context, operation="cycle")
        if evaluation.allowed:
            return ControllerDecision(
                kind=ActionKind.CYCLE,
                reason_code=ActionReasonCode.CYCLE_ALLOWED,
                matched_playlist=matched_playlist,
                evaluation=evaluation,
            )
        if evaluation.blocked_by:
            return ControllerDecision(
                kind=ActionKind.HOLD,
                reason_code=_blocked_reason(evaluation.blocked_by, operation="cycle"),
                matched_playlist=matched_playlist,
                evaluation=evaluation,
            )
        return ControllerDecision(
            kind=ActionKind.HOLD,
            reason_code=ActionReasonCode.HOLD_SAME_PLAYLIST,
            matched_playlist=matched_playlist,
            evaluation=evaluation,
        )

    def decide_manual_action(
        self,
        match: MatchEvaluation,
        active_playlist: str,
    ) -> ControllerDecision:
        matched_playlist = match.best_playlist

        if matched_playlist is None:
            return ControllerDecision(
                kind=ActionKind.HOLD if active_playlist else ActionKind.NONE,
                reason_code=ActionReasonCode.NO_MATCH,
                matched_playlist=None,
            )

        if matched_playlist != active_playlist:
            return ControllerDecision(
                kind=ActionKind.SWITCH,
                reason_code=ActionReasonCode.MANUAL_APPLY_REQUESTED,
                matched_playlist=matched_playlist,
            )

        if active_playlist:
            return ControllerDecision(
                kind=ActionKind.CYCLE,
                reason_code=ActionReasonCode.MANUAL_APPLY_REQUESTED,
                matched_playlist=matched_playlist,
            )

        return ControllerDecision(
            kind=ActionKind.HOLD,
            reason_code=ActionReasonCode.HOLD_SAME_PLAYLIST,
            matched_playlist=matched_playlist,
        )

    def _evaluate_gates(self, context: Context) -> list[ControllerBlocker]:
        blocked_by: list[ControllerBlocker] = []
        for gate in self._gates:
            blocker = gate.evaluate(context)
            if blocker is not None:
                blocked_by.append(blocker)
        return blocked_by

    def notify_playlist_switch(self):
        now = time.time()
        self.last_playlist_switch_time = now
        self.last_wallpaper_switch_time = now

    def notify_wallpaper_cycle(self):
        self.last_wallpaper_switch_time = time.time()

    def export_state(self) -> Dict[str, Any]:
        return {
            "last_playlist_switch_time": self.last_playlist_switch_time,
            "last_wallpaper_switch_time": self.last_wallpaper_switch_time,
        }

    def import_state(self, state: Dict[str, Any]) -> None:
        self.last_playlist_switch_time = state.get(
            "last_playlist_switch_time",
            self.last_playlist_switch_time,
        )
        self.last_wallpaper_switch_time = state.get(
            "last_wallpaper_switch_time",
            self.last_wallpaper_switch_time,
        )
