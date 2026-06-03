from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from core.models.context import Context
from core.models.playlist import Playlists
from core.models.trace import ActionResult, Match, TickTrace
from core.state.persisted import PersistedState

logger = logging.getLogger("WEScheduler.State")


@dataclass
class SchedulerState:
    paused: bool = False
    pause_until: float = 0.0
    cached_playlists: Playlists = field(default_factory=Playlists)
    last_tick_trace: TickTrace | None = None
    tick_id: int = 0
    _manual_apply_pending: bool = False

    def pause(self, seconds: int | None = None) -> None:
        self.paused = True
        if seconds is not None:
            self.pause_until = time.time() + seconds
            logger.info(
                "Scheduler paused for %ss (until %s).",
                seconds,
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.pause_until)),
            )
        else:
            self.pause_until = 0.0
            logger.info("Scheduler paused indefinitely.")

    def resume(self) -> None:
        self.paused = False
        self.pause_until = 0.0
        logger.info("Scheduler resumed.")

    def get_pause_remaining(self) -> float | None:
        if not self.paused or self.pause_until == 0:
            return None
        remaining = self.pause_until - time.time()
        return max(0.0, remaining)

    def maybe_auto_resume(self) -> bool:
        if not self.paused or self.pause_until <= 0:
            return False

        if time.time() < self.pause_until:
            return False

        logger.info("Timed pause expired.")
        self.resume()
        return True

    def request_manual_apply(self) -> None:
        self._manual_apply_pending = True

    def consume_manual_apply_request(self) -> bool:
        if not self._manual_apply_pending:
            return False
        self._manual_apply_pending = False
        return True

    def build_tick_trace(self, context: Context, match: Match, action: ActionResult) -> TickTrace:
        self.tick_id += 1
        return TickTrace(
            tick_id=self.tick_id,
            ts=time.time(),
            paused=self.paused,
            pause_until=self.pause_until,
            context=context,
            match=match,
            action=action,
        )

    def commit_tick(self, trace: TickTrace) -> None:
        self.last_tick_trace = trace

        next_cached = trace.action.cache_update
        if next_cached is not None and next_cached != self.cached_playlists:
            self.cached_playlists = next_cached
            self.save()

    def to_persisted(self) -> PersistedState:
        return PersistedState(
            paused=self.paused,
            pause_until=self.pause_until,
            cached_playlists=self.cached_playlists.names(),
        )

    def save(self) -> None:
        self.to_persisted().save()

    def restore_persisted(self, state: PersistedState) -> None:
        self.cached_playlists = Playlists(list(state.cached_playlists))
        self.paused = False
        self.pause_until = 0.0

        if state.pause_until > time.time():
            self.paused = True
            self.pause_until = state.pause_until
            logger.info(
                "Restored timed pause (until %s).",
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state.pause_until)),
            )
        elif state.paused and state.pause_until == 0:
            self.paused = True
            self.pause_until = 0.0
            logger.info("Restored indefinite pause.")
