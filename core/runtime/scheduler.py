from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from configurations.errors import ConfigLoadError
from core.models.event import EventLogger, EventType
from core.models.playlist import Playlists
from core.models.trace import TickTrace
from core.runtime.act_plan import plan_actuation
from core.runtime.engine import Engine
from core.state.action_history import ActionHistoryWriter
from core.state.persisted import PersistedState
from core.state.scheduler import SchedulerState

logger = logging.getLogger("WEScheduler.Core")
type TickListener = Callable[[TickTrace], None]


class WEScheduler:
    def __init__(
        self,
        config_dir: str,
        history_logger: EventLogger,
    ):
        self.config_dir = config_dir
        self.history_logger = history_logger
        self.initialized = False
        self.running = False
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self._runtime_lock = threading.RLock()

        self.on_auto_resume: Callable[[], None] | None = None
        self.on_reload_error: Callable[[ConfigLoadError], None] | None = None
        self._tick_listeners: list[TickListener] = []
        self.add_tick_listener(ActionHistoryWriter(history_logger).on_tick)

        self.engine: Engine | None = None
        self.state = SchedulerState()

    @property
    def paused(self) -> bool:
        return self.state.paused

    @property
    def cached_playlists(self) -> Playlists:
        return self.state.cached_playlists

    @property
    def last_tick_trace(self) -> TickTrace | None:
        return self.state.last_tick_trace

    def initialize(self) -> bool:
        self.engine = Engine.load(self.config_dir)
        self.state.restore_persisted(PersistedState.load())

        logger.info("Scheduler initialized successfully.")
        self.initialized = True
        return True

    def start(self) -> None:
        if self.running:
            logger.warning("Scheduler is already running.")
            return

        assert self.initialized, "Scheduler must be initialized before start."

        self.running = True
        self.stop_event.clear()
        self.history_logger.write(EventType.START, {})
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("Scheduler started.")

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
        self.state.save()
        self.history_logger.write(EventType.STOP, {})
        logger.info("Scheduler stopped.")

    def pause(self, seconds: int | None = None) -> None:
        with self._runtime_lock:
            self.state.pause(seconds)
            self.state.save()
            self.history_logger.write(EventType.PAUSE, {"duration": seconds})

    def resume(self) -> None:
        with self._runtime_lock:
            self.state.resume()
            self.history_logger.write(EventType.RESUME, {})
            self.state.save()

    def add_tick_listener(self, listener: TickListener) -> None:
        self._tick_listeners.append(listener)

    def get_pause_remaining(self) -> float | None:
        return self.state.get_pause_remaining()

    def _run_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                with self._runtime_lock:
                    self._check_hot_reload()
                    self._maybe_auto_resume()
                    trace = self._run_tick()
                    self._commit_tick(trace)

            except Exception:
                logger.exception("Error in main loop")

            time.sleep(1)

    def _check_hot_reload(self) -> None:
        assert self.engine is not None
        try:
            self.engine.reload_if_changed()
        except ConfigLoadError as exc:
            if self.on_reload_error is not None:
                try:
                    self.on_reload_error(exc)
                except Exception:
                    logger.exception("on_reload_error hook failed")

    def _maybe_auto_resume(self) -> None:
        if not self.state.maybe_auto_resume():
            return

        self.history_logger.write(EventType.RESUME, {})
        self.state.save()
        if self.on_auto_resume:
            try:
                self.on_auto_resume()
            except Exception:
                logger.exception("on_auto_resume hook failed")

    def _run_tick(self) -> TickTrace:
        assert self.engine is not None
        engine = self.engine
        context = engine.sense()
        match = engine.think(context)

        plan = plan_actuation(
            factual=engine.probe_playlist(),
            cached_playlists=self.state.cached_playlists,
            paused=self.state.paused,
            manual_requested=self.state.consume_manual_apply_request(),
        )

        action = engine.act(plan, match, context)
        return self.state.build_tick_trace(context, match, action)

    def apply_current_match_now(self) -> None:
        logger.info("Manual apply requested.")
        self.state.request_manual_apply()

    def _commit_tick(self, trace: TickTrace) -> None:
        self.state.commit_tick(trace)

        for listener in list(self._tick_listeners):
            try:
                listener(trace)
            except Exception:
                logger.exception("tick listener failed")
