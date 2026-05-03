from __future__ import annotations

import copy
import json
import logging
import os
import sys
import threading
import time
from typing import Callable, Dict, List, Optional

from pydantic import BaseModel

from core.actuator import Actuator
from core.context import Context, ContextManager
from core.controller import SchedulingController
from core.diagnostics import SchedulerTickTrace
from core.event_logger import EventLogger, EventType
from core.executor import WEExecutor
from core.matcher import Matcher
from core.policies import POLICY_REGISTRY, Policy
from core.sensors import SENSOR_REGISTRY
from utils.app_context import get_data_dir
from utils.config_loader import ConfigLoader

logger = logging.getLogger("WEScheduler.Core")

_STATE_FILE = os.path.join(get_data_dir(), "state.json")


class SchedulerState(BaseModel):
    """Persisted scheduler state (state.json)."""

    paused: bool = False
    pause_until: float = 0.0
    current_playlist: str = ""
    last_playlist_switch_time: float = 0.0
    last_wallpaper_switch_time: float = 0.0

    @staticmethod
    def load_state(path: str = _STATE_FILE) -> SchedulerState:
        try:
            with open(path, "r", encoding="utf-8") as f:
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


class WEScheduler:
    def __init__(self, config_path: str, history_logger: EventLogger):
        self.config_path = config_path
        self.history_logger: EventLogger = history_logger
        self.initialized = False
        self.running = False
        self.paused = False
        self.pause_until: float = 0
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()

        self.on_auto_resume: Optional[Callable[[], None]] = None
        self.on_tick: Optional[Callable[[SchedulerTickTrace], None]] = None

        self.config_loader: Optional[ConfigLoader] = None
        self.executor: Optional[WEExecutor] = None
        self.context_manager: Optional[ContextManager] = None
        self.matcher: Optional[Matcher] = None
        self.actuator: Optional[Actuator] = None

        self.current_playlist: str = ""
        self.last_status_line: str = ""
        self.last_tick_trace: Optional[SchedulerTickTrace] = None
        self.tick_id: int = 0
        self._config_mtime: float = 0.0

    def initialize(self) -> bool:
        self.config_loader = ConfigLoader(self.config_path)
        config = self.config_loader.load()
        self._config_mtime = os.path.getmtime(self.config_path)
        logger.info("Loaded %d playlists.", len(config.playlists))

        self.executor = WEExecutor(config.wallpaper_engine_path)
        self._build_runtime_components()
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

    def pause(self, seconds: Optional[int] = None):
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
        self.paused = False
        self.pause_until = 0
        logger.info("Scheduler resumed.")
        self.history_logger.write(EventType.RESUME, {})
        SchedulerState.save_state(self._build_state())

    def get_pause_remaining(self) -> Optional[float]:
        if not self.paused or self.pause_until == 0:
            return None
        remaining = self.pause_until - time.time()
        return max(0.0, remaining)

    def _run_loop(self):
        while not self.stop_event.is_set():
            if self.paused:
                if self.pause_until > 0 and time.time() >= self.pause_until:
                    logger.info("Timed pause expired. Resuming scheduler.")
                    self.resume()
                    if self.on_auto_resume:
                        try:
                            self.on_auto_resume()
                        except Exception:
                            logger.exception("on_auto_resume hook failed")
                else:
                    time.sleep(1)
                    continue

            try:
                self._check_hot_reload()

                live_context = self.context_manager.refresh()
                context_snapshot = copy.deepcopy(live_context)
                match = self.matcher.evaluate(context_snapshot)
                active_playlist_before = self.current_playlist
                action = self.actuator.act(
                    context_snapshot,
                    match,
                    active_playlist_before,
                )

                self.tick_id += 1
                trace = SchedulerTickTrace(
                    tick_id=self.tick_id,
                    ts=time.time(),
                    paused=self.paused,
                    pause_until=self.pause_until,
                    active_playlist_before=active_playlist_before,
                    active_playlist_after=action.active_playlist_after,
                    context=context_snapshot,
                    match=match,
                    action=action,
                )
                self.last_tick_trace = trace

                if action.active_playlist_after != self.current_playlist:
                    self.current_playlist = action.active_playlist_after
                    SchedulerState.save_state(self._build_state())

                self._update_status(trace)

                if self.on_tick:
                    try:
                        self.on_tick(trace)
                    except Exception:
                        logger.exception("on_tick hook failed")

            except Exception as exc:
                logger.error("Error in main loop: %s", exc)

            time.sleep(1)

    def _check_hot_reload(self) -> None:
        try:
            mtime = os.path.getmtime(self.config_path)
        except OSError:
            return
        if mtime != self._config_mtime:
            self._config_mtime = mtime
            self._hot_reload()

    def _build_runtime_components(self) -> None:
        config = self.config_loader.config

        context_manager = ContextManager()
        for sensor_cls in SENSOR_REGISTRY:
            context_manager.register_sensor(sensor_cls.create(config))

        policies: List[Policy] = [
            cls(getattr(config.policies, cls.config_key))
            for cls in POLICY_REGISTRY
            if getattr(config.policies, cls.config_key) is not None
        ]

        self.context_manager = context_manager
        self.matcher = Matcher(config.playlists, policies, config.tags)
        self.actuator = Actuator(
            self.executor,
            SchedulingController(config.scheduling),
            history_logger=self.history_logger,
        )
        self.display_of = {pl.name: pl.display or pl.name for pl in config.playlists}

    def _hot_reload(self) -> None:
        try:
            policy_states: Dict[str, Dict] = {
                type(policy).__name__: policy.export_state()
                for policy in self.matcher.policies
            }
            controller_state = self.actuator.controller.export_state()

            self.config_loader.load()
            config = self.config_loader.config
            logger.info("Hot reload: config changed, rebuilding components.")

            self._build_runtime_components()

            for policy in self.matcher.policies:
                saved = policy_states.get(type(policy).__name__)
                if saved:
                    policy.import_state(saved)

            self.actuator.controller.import_state(controller_state)

            logger.info("Hot reload complete. %d playlists loaded.", len(config.playlists))
        except Exception:
            logger.exception("Hot reload failed, keeping previous config")

    def _build_state(self) -> SchedulerState:
        controller = self.actuator.controller
        return SchedulerState(
            paused=self.paused,
            pause_until=self.pause_until,
            current_playlist=self.current_playlist,
            last_playlist_switch_time=controller.last_playlist_switch_time,
            last_wallpaper_switch_time=controller.last_wallpaper_switch_time,
        )

    def _restore_state(self, state: SchedulerState) -> None:
        self.current_playlist = state.current_playlist
        self.actuator.controller.import_state(
            {
                "last_playlist_switch_time": state.last_playlist_switch_time,
                "last_wallpaper_switch_time": state.last_wallpaper_switch_time,
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
        best_playlist = trace.match.best_playlist
        tags = trace.match.raw_context_vector
        sorted_tags = sorted(tags.items(), key=lambda x: x[1], reverse=True)[:3]

        label = self.display_of.get(best_playlist) if best_playlist else None

        tag_parts = []
        for tag, weight in sorted_tags:
            bar_len = int(min(weight, 1.5) * 5)
            bar = "■" * bar_len
            tag_parts.append(f"{tag} {weight:.2f} {bar}")

        tag_str = " | ".join(tag_parts)
        gap_str = f" gap={trace.match.similarity_gap:.2f}" if trace.match.playlist_matches else ""
        self.last_status_line = (
            f"[{label or 'WAITING'}] {process_name}({idle_time:.0f}s) >> {tag_str}{gap_str}"
        )
        if not getattr(sys, "frozen", False):
            print(f"\r{self.last_status_line:<110}", end="", flush=True)
