from __future__ import annotations

import copy
import json
import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from core.actuator import Actuator
from core.context import ContextManager
from core.controller import SchedulingController
from core.diagnostics import (
    ActionKind,
    ActionReasonCode,
    ActuationOutcome,
    ControllerDecision,
    MatchEvaluation,
    SchedulerTickTrace,
)
from core.event_logger import EventLogger, EventType
from core.executor import WEExecutor
from core.matcher import Matcher
from core.playlist import Playlists
from core.playlist_state import resolve_playlist_state
from core.policies import POLICY_REGISTRY, Policy
from core.sensors import SENSOR_REGISTRY
from utils.app_context import get_data_dir
from utils.config_errors import ConfigLoadError
from utils.config_loader import ConfigLoader
from utils.runtime_config import PlaylistConfig, SchedulerConfig
from utils.we_config import WEConfigProber

logger = logging.getLogger("WEScheduler.Core")

_STATE_FILE = os.path.join(get_data_dir(), "state.json")


class SchedulerState(BaseModel):
    paused: bool = False
    pause_until: float = 0.0
    cached_playlists: list[str] = []
    last_action_time: float = 0.0

    @staticmethod
    def load_state(path: str = _STATE_FILE) -> SchedulerState:
        try:
            with open(path, encoding="utf-8") as f:
                return SchedulerState.model_validate(json.load(f))
        except Exception:
            return SchedulerState()

    @staticmethod
    def save_state(state: SchedulerState, path: str = _STATE_FILE) -> None:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(state.model_dump_json(indent=2))
        except Exception:
            logger.warning("Failed to write state.json", exc_info=True)


@dataclass(frozen=True)
class _RuntimeComponents:
    executor: WEExecutor
    context_manager: ContextManager
    matcher: Matcher
    actuator: Actuator
    playlist_configs: dict[str, PlaylistConfig]
    we_config_prober: WEConfigProber


class WEScheduler:
    def __init__(self, config_dir: str, history_logger: EventLogger):
        self.config_dir = config_dir
        self.history_logger: EventLogger = history_logger
        self.initialized = False
        self.running = False
        self.paused = False
        self.pause_until: float = 0
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self._runtime_lock = threading.RLock()

        self.on_auto_resume: Callable[[], None] | None = None
        self.on_tick: Callable[[SchedulerTickTrace], None] | None = None
        self.on_reload_error: Callable[[ConfigLoadError], None] | None = None

        self.config_loader: ConfigLoader | None = None
        self.executor: WEExecutor | None = None
        self.context_manager: ContextManager | None = None
        self.matcher: Matcher | None = None
        self.actuator: Actuator | None = None
        self.we_config_prober: WEConfigProber | None = None

        self.cached_playlists: Playlists = Playlists([])
        self.last_status_line: str = ""
        self.last_tick_trace: SchedulerTickTrace | None = None
        self.last_reload_error: ConfigLoadError | None = None
        self.tick_id: int = 0
        self._config_fingerprint: tuple[tuple[str, bool, int], ...] = ()

    def initialize(self) -> bool:
        self.config_loader = ConfigLoader(self.config_dir)
        config = self.config_loader.load_verified_config()
        self._config_fingerprint = self.config_loader.fingerprint()
        logger.info("Loaded %d playlists.", len(config.playlists))

        self._install_runtime_components(self._build_runtime_components(config))
        self._restore_state(SchedulerState.load_state())

        logger.info("Scheduler initialized successfully.")
        self.initialized = True
        return True

    def start(self):
        if self.running:
            logger.warning("Scheduler is already running.")
            return

        if not getattr(self, "initialized", False):
            logger.error("Scheduler not initialized. Call initialize() first.")
            return

        self.running = True
        self.stop_event.clear()
        self.history_logger.write(EventType.START, {})
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("Scheduler started.")

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
        SchedulerState.save_state(self._build_state())
        self.history_logger.write(EventType.STOP, {})
        logger.info("Scheduler stopped.")

    def pause(self, seconds: int | None = None):
        with self._runtime_lock:
            self.paused = True
            if seconds is not None:
                self.pause_until = time.time() + seconds
                logger.info(
                    "Scheduler paused for %ss (until %s).",
                    seconds,
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.pause_until)),
                )
            else:
                self.pause_until = 0
                logger.info("Scheduler paused (indefinitely).")
            SchedulerState.save_state(self._build_state())
            self.history_logger.write(EventType.PAUSE, {"duration": seconds})

    def resume(self):
        with self._runtime_lock:
            self.paused = False
            self.pause_until = 0
            logger.info("Scheduler resumed.")
            self.history_logger.write(EventType.RESUME, {})
            SchedulerState.save_state(self._build_state())

    def get_pause_remaining(self) -> float | None:
        if not self.paused or self.pause_until == 0:
            return None
        remaining = self.pause_until - time.time()
        return max(0.0, remaining)

    def _run_loop(self):
        while not self.stop_event.is_set():
            try:
                with self._runtime_lock:
                    self._check_hot_reload()
                    self._maybe_auto_resume()
                    trace = self._run_tick()
                    self._commit_tick(trace)

            except Exception as exc:
                logger.error("Error in main loop: %s", exc)

            time.sleep(1)

    def _maybe_auto_resume(self) -> None:
        if not self.paused or self.pause_until <= 0:
            return
        if time.time() < self.pause_until:
            return

        logger.info("Timed pause expired. Resuming scheduler.")
        self.resume()
        if self.on_auto_resume:
            try:
                self.on_auto_resume()
            except Exception:
                logger.exception("on_auto_resume hook failed")

    def _run_tick(self) -> SchedulerTickTrace:
        live_context = self.context_manager.refresh()
        context_snapshot = copy.deepcopy(live_context)
        match = self.matcher.evaluate(context_snapshot)
        cached_playlists_before = self.cached_playlists
        factual = self.we_config_prober.probe_playlist()
        resolution = resolve_playlist_state(
            factual,
            cached_playlists=cached_playlists_before,
            paused=self.paused,
        )

        if self.paused:
            action = self._build_paused_actuation_outcome(match, resolution.effective_playlists)
        elif resolution.recovery_needed and resolution.recovery_reason is not None:
            action = self.actuator.act_recovery(
                match,
                resolution.effective_playlists,
                resolution.recovery_reason,
            )
        else:
            action = self.actuator.act(
                context_snapshot,
                match,
                resolution.effective_playlists,
            )

        self.tick_id += 1
        return SchedulerTickTrace(
            tick_id=self.tick_id,
            ts=time.time(),
            paused=self.paused,
            pause_until=self.pause_until,
            context=context_snapshot,
            match=match,
            action=action,
        )

    def apply_current_match_now(self) -> SchedulerTickTrace | None:
        with self._runtime_lock:
            logger.info("Manual apply requested.")
            trace = self._run_manual_apply_tick()
            self._commit_tick(trace)
            return trace

    def _run_manual_apply_tick(self) -> SchedulerTickTrace:
        live_context = self.context_manager.refresh()
        context_snapshot = copy.deepcopy(live_context)
        match = self.matcher.evaluate(context_snapshot)
        action = self.actuator.act_manual(match, self.cached_playlists)

        self.tick_id += 1
        return SchedulerTickTrace(
            tick_id=self.tick_id,
            ts=time.time(),
            paused=self.paused,
            pause_until=self.pause_until,
            context=context_snapshot,
            match=match,
            action=action,
        )

    def _build_paused_actuation_outcome(
        self,
        match: MatchEvaluation,
        effective_playlists: Playlists,
    ) -> ActuationOutcome:
        return ActuationOutcome(
            decision=ControllerDecision(
                kind=ActionKind.PAUSE,
                reason_code=ActionReasonCode.SCHEDULER_PAUSED,
                matched_playlists=match.best_playlists,
                evaluation=None,
            ),
            effective_playlists_before=effective_playlists,
            effective_playlists_after=effective_playlists,
            executed=False,
        )

    def _commit_tick(self, trace: SchedulerTickTrace) -> None:
        self.last_tick_trace = trace

        should_save_state = False
        next_cached_playlists = self._resolve_cached_playlists_after(trace.action)
        if next_cached_playlists != self.cached_playlists:
            self.cached_playlists = next_cached_playlists
            should_save_state = True

        if trace.action.executed:
            should_save_state = True

        if should_save_state:
            SchedulerState.save_state(self._build_state())

        self._update_status(trace)

        if self.on_tick:
            try:
                self.on_tick(trace)
            except Exception:
                logger.exception("on_tick hook failed")

    def _resolve_cached_playlists_after(self, action: ActuationOutcome) -> Playlists:
        if action.kind == ActionKind.SWITCH and action.executed:
            return action.effective_playlists_after
        if action.effective_playlists_before:
            return action.effective_playlists_before
        return self.cached_playlists

    def _check_hot_reload(self) -> None:
        fingerprint = self.config_loader.fingerprint()
        if fingerprint != self._config_fingerprint:
            self._hot_reload(fingerprint)

    def _build_runtime_components(self, config: SchedulerConfig) -> _RuntimeComponents:
        executor = WEExecutor(config.wallpaper_engine_path)

        context_manager = ContextManager()
        for sensor_cls in SENSOR_REGISTRY:
            context_manager.register_sensor(sensor_cls.create(config))

        policies: list[Policy] = [
            cls(getattr(config.policies, cls.config_key)) for cls in POLICY_REGISTRY if getattr(config.policies, cls.config_key) is not None
        ]

        matcher = Matcher(config.playlists, policies, config.tags)
        actuator = Actuator(
            executor,
            SchedulingController(config.scheduling),
            history_logger=self.history_logger,
        )

        return _RuntimeComponents(
            executor=executor,
            context_manager=context_manager,
            matcher=matcher,
            actuator=actuator,
            playlist_configs=config.playlists,
            we_config_prober=WEConfigProber(config.wallpaper_engine_path),
        )

    def _install_runtime_components(self, runtime: _RuntimeComponents) -> None:
        self.executor = runtime.executor
        self.context_manager = runtime.context_manager
        self.matcher = runtime.matcher
        self.actuator = runtime.actuator
        self.we_config_prober = runtime.we_config_prober
        Playlists.configure(runtime.playlist_configs)

    def _hot_reload(self, fingerprint: tuple[tuple[str, bool, int], ...]) -> None:
        previous_config = self.config_loader.config
        try:
            policy_states: dict[str, dict] = {type(policy).__name__: policy.export_state() for policy in self.matcher.policies}
            controller_state = self.actuator.controller.export_state()

            config = self.config_loader.load_verified_config()
            logger.info("Hot reload: config changed, rebuilding components.")

            next_runtime = self._build_runtime_components(config)

            for policy in next_runtime.matcher.policies:
                saved = policy_states.get(type(policy).__name__)
                if saved:
                    policy.import_state(saved)

            next_runtime.actuator.controller.import_state(controller_state)
            self._install_runtime_components(next_runtime)
            self.last_reload_error = None

            logger.info("Hot reload complete. %d playlists loaded.", len(config.playlists))
        except ConfigLoadError as exc:
            self.config_loader.config = previous_config
            self.last_reload_error = exc
            logger.warning("Hot reload rejected. Keeping previous runtime.\n%s", exc)
            if self.on_reload_error:
                try:
                    self.on_reload_error(exc)
                except Exception:
                    logger.exception("on_reload_error hook failed")
        except Exception:
            self.config_loader.config = previous_config
            logger.exception("Hot reload failed unexpectedly, keeping previous runtime")
        finally:
            # in all cases, we update fingerprint to avoid repeated reloads.
            self._config_fingerprint = fingerprint

    def _build_state(self) -> SchedulerState:
        controller = self.actuator.controller
        return SchedulerState(
            paused=self.paused,
            pause_until=self.pause_until,
            cached_playlists=self.cached_playlists.names(),
            last_action_time=controller.last_action_time,
        )

    def _restore_state(self, state: SchedulerState) -> None:
        self.cached_playlists = Playlists(list(state.cached_playlists))
        self.actuator.controller.import_state(
            {
                "last_action_time": state.last_action_time,
            }
        )

        if state.pause_until > time.time():
            self.paused = True
            self.pause_until = state.pause_until
            logger.info(
                "Restored timed pause (until %s).",
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state.pause_until)),
            )
        elif state.paused and state.pause_until == 0:
            self.paused = True
            self.pause_until = 0
            logger.info("Restored indefinite pause.")

    def _update_status(self, trace: SchedulerTickTrace) -> None:
        process_name = trace.context.window.process or "N/A"
        idle_time = trace.context.idle
        best_playlists = trace.match.best_playlists
        tags = trace.match.raw_context_vector
        sorted_tags = sorted(tags.items(), key=lambda x: x[1], reverse=True)[:3]

        displays = Playlists.managed().displays()
        if best_playlists:
            primary = displays.get(best_playlists[0], best_playlists[0])
            label = f"{primary}(+{len(best_playlists) - 1})" if len(best_playlists) > 1 else primary
        else:
            label = None

        tag_parts = []
        for tag, weight in sorted_tags:
            bar_len = int(min(weight, 1.5) * 5)
            bar = "■" * bar_len
            tag_parts.append(f"{tag} {weight:.2f} {bar}")

        tag_str = " | ".join(tag_parts)
        gap_str = f" gap={trace.match.similarity_gap:.2f}" if trace.match.playlist_matches else ""
        prefix = "PAUSED " if trace.paused else ""
        self.last_status_line = f"{prefix}[{label or 'WAITING'}] {process_name}({idle_time:.0f}s) >> {tag_str}{gap_str}"
        if not getattr(sys, "frozen", False):
            print(f"\r{self.last_status_line:<110}", end="", flush=True)
