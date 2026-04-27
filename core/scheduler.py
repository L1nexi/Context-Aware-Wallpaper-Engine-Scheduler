from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from typing import Dict, List, Optional, Type

from pydantic import BaseModel

from utils.config_loader import ConfigLoader
from utils.app_context import get_data_dir
from core.executor import WEExecutor
from core.sensors import Sensor, WindowSensor, IdleSensor, CpuSensor, FullscreenSensor, WeatherSensor, TimeSensor
from core.policies import ActivityPolicy, Policy, TimePolicy, SeasonPolicy, WeatherPolicy
from core.context import ContextManager, Context
from core.matcher import Matcher, MatchResult
from core.controller import SchedulingController
from core.actuator import Actuator

logger = logging.getLogger("WEScheduler.Core")

# Registry of Policy classes in evaluation order.
# To add a new policy: import its class above and append it here.
_POLICY_REGISTRY: List[Type[Policy]] = [
    ActivityPolicy,
    TimePolicy,
    SeasonPolicy,
    WeatherPolicy,
]

# Registry of Sensor classes.
# Each sensor carries its own context key (Sensor.key) and activation logic
# (Sensor.create(config))
_SENSOR_REGISTRY: List[Type[Sensor]] = [
    WindowSensor,
    IdleSensor,
    CpuSensor,
    FullscreenSensor,
    WeatherSensor,
    TimeSensor,
]


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
        """Load persisted state from state.json. Returns defaults on any error."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return SchedulerState.model_validate(json.load(f))
        except Exception:
            return SchedulerState()
        
    @staticmethod
    def save_state(state: SchedulerState, path: str = _STATE_FILE) -> None:
        """Persist state to state.json. Silently ignores write errors."""
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(state.model_dump_json(indent=2))
        except Exception:
            logger.warning("Failed to write state.json", exc_info=True)

class WEScheduler:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.initialized = False
        self.running = False
        self.paused = False
        self.pause_until: float = 0
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()

        # Hooks — set externally by the host (main.py) to wire up
        # cross-cutting concerns without the scheduler owning them.
        self.on_auto_resume = None   # called when a timed pause expires
        self.on_tick = None          # called every tick: (scheduler, context, result)

        # Components
        self.config_loader: Optional[ConfigLoader] = None
        self.executor: Optional[WEExecutor] = None
        self.context_manager: Optional[ContextManager] = None
        self.matcher: Optional[Matcher] = None
        self.actuator: Optional[Actuator] = None

        self.current_playlist: str = ""
        self.last_status_line: str = ""
        self._config_mtime: float = 0.0

    def initialize(self) -> bool:
        """Initializes all components. Returns True if successful, raises on failure."""
        # 1. Load Config
        self.config_loader = ConfigLoader(self.config_path)
        config = self.config_loader.load()
        self._config_mtime = os.path.getmtime(self.config_path)
        logger.info(f"Loaded {len(config.playlists)} playlists.")

        # 2. Initialize Executor
        self.executor = WEExecutor(config.wallpaper_engine_path)

        # 3. Build all runtime components (sensors, policies, matcher, controller, actuator)
        self._build_runtime_components()

        # 4. Restore persisted state
        self._restore_state(SchedulerState.load_state())

        logger.info("Scheduler initialized successfully.")
        self.initialized = True
        return True

    def start(self):
        if self.running:
            logger.warning("Scheduler is already running.")
            return
        
        if not getattr(self, 'initialized', False):
            logger.error("Scheduler not initialized. Call initialize() first.")
            return

        self.running = True
        self.stop_event.clear()
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
        logger.info("Scheduler stopped.")

    def pause(self, seconds: Optional[int] = None):
        """
        Pauses the scheduler.
        :param seconds: Duration in seconds. None means indefinite.
        """
        self.paused = True
        if seconds is not None:
            self.pause_until = time.time() + seconds
            logger.info(f"Scheduler paused for {seconds}s (until {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.pause_until))}).")
        else:
            self.pause_until = 0
            logger.info("Scheduler paused (indefinitely).")
        SchedulerState.save_state(self._build_state())

    def resume(self):
        self.paused = False
        self.pause_until = 0
        logger.info("Scheduler resumed.")
        SchedulerState.save_state(self._build_state())

    def get_pause_remaining(self) -> Optional[float]:
        """Returns remaining pause seconds, or None if not in a timed pause."""
        if not self.paused or self.pause_until == 0:
            return None
        remaining = self.pause_until - time.time()
        return max(0.0, remaining)

    def _run_loop(self):
        while not self.stop_event.is_set():
            if self.paused:
                # Check for timed pause expiry
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
                # 0. Hot Reload — check config file mtime
                self._check_hot_reload()

                # 1. Sense
                context = self.context_manager.refresh()
                
                # 2. Think
                result = self.matcher.match(context)
                
                # 3. Act
                new_playlist = self.actuator.act(context, result, self.current_playlist)
                if new_playlist != self.current_playlist:
                    self.current_playlist = new_playlist
                    SchedulerState.save_state(self._build_state())
                
                # Status Update (for console/tray)
                self._update_status(context, result)

                if self.on_tick:
                    try:
                        self.on_tick(self, context, result)
                    except Exception:
                        logger.exception("on_tick hook failed")

            except Exception as e:
                logger.error(f"Error in main loop: {e}")
            
            time.sleep(1)

    def _check_hot_reload(self) -> None:
        """Detect config file changes by mtime and trigger a reload."""
        try:
            mtime = os.path.getmtime(self.config_path)
        except OSError:
            return
        if mtime != self._config_mtime:
            self._config_mtime = mtime
            self._hot_reload()

    def _build_runtime_components(self) -> None:
        """Build/rebuild all runtime components from the current loaded config.

        Assigns ``self.context_manager``, ``self.matcher``, and
        ``self.actuator``.  Called by both ``initialize()`` and
        ``_hot_reload()`` to avoid duplication.
        """
        config = self.config_loader.config

        cm = ContextManager()
        for sensor_cls in _SENSOR_REGISTRY:
            cm.register_sensor(sensor_cls.create(config))

        policies: List[Policy] = [
            cls(getattr(config.policies, cls.config_key))
            for cls in _POLICY_REGISTRY
            if getattr(config.policies, cls.config_key) is not None
        ]

        self.context_manager = cm
        self.matcher = Matcher(config.playlists, policies, config.tags)
        self.actuator = Actuator(self.executor, SchedulingController(config.scheduling))

    def _hot_reload(self) -> None:
        """Reload config and rebuild all runtime components.

        Preserves: current_playlist, pause state, running/thread state.
        Also preserves across rebuild via the export/import_state protocol:
          - Per-policy transient state (e.g. ActivityPolicy EMA smoothing)
          - SchedulingController cooldown timestamps
        """
        try:
            # Snapshot stateful component state before teardown.
            policy_states: Dict[str, Dict] = {
                type(p).__name__: p.export_state()
                for p in self.matcher.policies
            }
            controller_state = self.actuator.controller.export_state()

            self.config_loader.load()
            config = self.config_loader.config
            logger.info("Hot reload: config changed, rebuilding components.")

            self._build_runtime_components()

            # Restore per-policy transient state
            for p in self.matcher.policies:
                saved = policy_states.get(type(p).__name__)
                if saved:
                    p.import_state(saved)

            # Restore controller cooldown timestamps
            self.actuator.controller.import_state(controller_state)

            logger.info(f"Hot reload complete. {len(config.playlists)} playlists loaded.")
        except Exception:
            logger.exception("Hot reload failed, keeping previous config")

    def _build_state(self) -> SchedulerState:
        """Returns a snapshot of the scheduler state suitable for persistence.
        
        Captures the current pause status, current playlist, and controller cooldown timestamps.
        Safe to call any time after _build_runtime_components().
        """
        controller = self.actuator.controller
        return SchedulerState(
            paused=self.paused,
            pause_until=self.pause_until,
            current_playlist=self.current_playlist,
            last_playlist_switch_time=controller.last_playlist_switch_time,
            last_wallpaper_switch_time=controller.last_wallpaper_switch_time,
        )

    def _restore_state(self, state: SchedulerState) -> None:
        """Apply a persisted SchedulerState to the live scheduler and controller.

        Restores pause status, current playlist, and controller cooldown
        timestamps.  Safe to call any time after _build_runtime_components().
        """
        self.current_playlist = state.current_playlist

        # Restore controller cooldown timestamps 
        self.actuator.controller.import_state({
            "last_playlist_switch_time": state.last_playlist_switch_time,
            "last_wallpaper_switch_time": state.last_wallpaper_switch_time,
        })

        # Restore pause state
        if state.pause_until > time.time():
            self.paused = True
            self.pause_until = state.pause_until
            logger.info(
                "Restored timed pause (until %s).",
                time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(state.pause_until)),
            )
        elif state.paused and state.pause_until == 0:
            self.paused = True
            self.pause_until = 0
            logger.info("Restored indefinite pause.")

    def _update_status(self, context: Context, result: Optional[MatchResult]) -> None:
        process_name = context.window.process or "N/A"
        idle_time = context.idle
        decision = result.best_playlist if result is not None else None
        tags = result.aggregated_tags if result is not None else {}
        sorted_tags = sorted(tags.items(), key=lambda x: x[1], reverse=True)[:3]

        tag_parts = []
        for tag, weight in sorted_tags:
            bar_len = int(min(weight, 1.5) * 5)
            bar = "■" * bar_len
            tag_parts.append(f"{tag} {weight:.2f} {bar}")

        tag_str = " | ".join(tag_parts)
        gap_str = f" gap={result.similarity_gap:.2f}" if result is not None else ""
        self.last_status_line = (
            f"[{decision or 'WAITING'}] {process_name}({idle_time:.0f}s) >> {tag_str}{gap_str}"
        )
        if not getattr(sys, 'frozen', False):
            print(f"\r{self.last_status_line:<110}", end="", flush=True)
