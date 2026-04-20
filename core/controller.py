import time
import logging
from typing import Dict, Any, List

from core.context import Context
from utils.config_loader import DisturbanceConfig

logger = logging.getLogger("WEScheduler.Controller")


# ── Gate classes ─────────────────────────────────────────────────────────
# Each gate decides whether a switch should be *deferred* (not permanently
# blocked).  ``last_switch_time`` is NOT reset, so ``force_interval`` keeps
# ticking and will fire once the deferral condition clears.

class CpuGate:
    """Defers switching while rolling-average CPU utilisation exceeds *threshold*."""

    def __init__(self, threshold: float) -> None:
        self.threshold = threshold  # 0 = disabled

    def should_defer(self, context: Context) -> bool:
        if self.threshold <= 0:
            return False
        cpu_avg = context.cpu
        if cpu_avg >= self.threshold:
            logger.debug(
                "CPU gate: %.1f%% >= %.0f%%, deferring",
                cpu_avg, self.threshold,
            )
            return True
        return False


class FullscreenGate:
    """Defers switching while a fullscreen / presentation-mode app is detected."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def should_defer(self, context: Context) -> bool:
        if not self.enabled:
            return False
        if context.fullscreen:
            logger.debug("Fullscreen gate: deferring switch")
            return True
        return False


class DisturbanceController:
    def __init__(self, config: DisturbanceConfig):
        self.idle_threshold = config.idle_threshold

        # Playlist Switching & Cycling Config
        self.playlist_min_interval   = config.min_interval
        self.playlist_force_interval = config.force_interval
        self.wallpaper_min_interval  = config.wallpaper_interval

        # Build gate chain from config
        self._gates: List = []
        if config.cpu_threshold > 0:
            self._gates.append(CpuGate(config.cpu_threshold))
        if config.fullscreen_defer:
            self._gates.append(FullscreenGate())

        # Initialize startup_delay by backdating the last switch times,
        # so that the system is effectively "cooling down" during startup.
        # Clamped to [0, min_interval]: values above min_interval would push
        # init_time into the future, breaking can_switch_playlist() logic.
        startup_delay = min(max(config.startup_delay, 0), self.playlist_min_interval)
        init_time = time.time() - (self.playlist_min_interval - startup_delay)
        self.last_playlist_switch_time = init_time
        self.last_wallpaper_switch_time = init_time

    def _any_gate_defers(self, context: Context) -> bool:
        """Returns True if any gate wants to defer the current switch."""
        for gate in self._gates:
            if gate.should_defer(context):
                return True
        return False

    def can_switch_playlist(self, context: Context) -> bool:
        """
        Determines if switching to a NEW playlist is allowed.
        """
        current_time = time.time()
        time_since_last = current_time - self.last_playlist_switch_time
        
        # 1. Cooling Down Check
        if time_since_last < self.playlist_min_interval:
            return False

        # 2. Gate chain — defer (not permanently block)
        if self._any_gate_defers(context):
            return False

        # 3. Idle Check
        idle_time = context.idle
        if idle_time >= self.idle_threshold:
            return True
        
        # 4. Force Switch Check
        if time_since_last >= self.playlist_force_interval:
            return True
            
        return False

    def can_cycle_wallpaper(self, context: Context) -> bool:
        """
        Determines if cycling to the NEXT wallpaper within the SAME playlist is allowed.
        """
        current_time = time.time()
        time_since_last = current_time - self.last_wallpaper_switch_time
        
        # 1. Cooling Down Check
        if time_since_last < self.wallpaper_min_interval:
            return False

        # 2. Gate chain — same defer semantics as playlist switching
        if self._any_gate_defers(context):
            return False

        # 3. Idle Check
        # We only cycle wallpaper when user is idle to avoid distraction
        idle_time = context.idle
        if idle_time >= self.idle_threshold:
            return True
            
        return False

    def notify_playlist_switch(self):
        self.last_playlist_switch_time = time.time()
        # Switching playlist also counts as switching wallpaper
        self.last_wallpaper_switch_time = time.time()

    def notify_wallpaper_cycle(self):
        self.last_wallpaper_switch_time = time.time()

    def export_state(self) -> Dict[str, Any]:
        """Export cooldown timestamps for hot-reload preservation."""
        return {
            "last_playlist_switch_time": self.last_playlist_switch_time,
            "last_wallpaper_switch_time": self.last_wallpaper_switch_time,
        }

    def import_state(self, state: Dict[str, Any]) -> None:
        """Restore cooldown timestamps after a hot reload."""
        self.last_playlist_switch_time = state.get(
            "last_playlist_switch_time", self.last_playlist_switch_time
        )
        self.last_wallpaper_switch_time = state.get(
            "last_wallpaper_switch_time", self.last_wallpaper_switch_time
        )
