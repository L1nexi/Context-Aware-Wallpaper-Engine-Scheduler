import time
import logging
from typing import Dict, Any, List

logger = logging.getLogger("WEScheduler.Controller")

# Default interval constants (seconds)
_DEFAULT_IDLE_THRESHOLD      = 60
_DEFAULT_PLAYLIST_MIN        = 1800   # 30 min  – cooldown between playlist switches
_DEFAULT_PLAYLIST_FORCE      = 14400  # 4 h     – force a switch even without idle
_DEFAULT_WALLPAPER_MIN       = 600    # 10 min  – cooldown between wallpaper cycles
_DEFAULT_CPU_THRESHOLD       = 85     # %       – defer any switch above this average; 0 = disabled


# ── Gate classes ─────────────────────────────────────────────────────────
# Each gate decides whether a switch should be *deferred* (not permanently
# blocked).  ``last_switch_time`` is NOT reset, so ``force_interval`` keeps
# ticking and will fire once the deferral condition clears.

class CpuGate:
    """Defers switching while rolling-average CPU utilisation exceeds *threshold*."""

    def __init__(self, threshold: float) -> None:
        self.threshold = threshold  # 0 = disabled

    def should_defer(self, context: Dict[str, Any]) -> bool:
        if self.threshold <= 0:
            return False
        cpu_avg = context.get("cpu", 0.0)
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

    def should_defer(self, context: Dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        if context.get("fullscreen", False):
            logger.debug("Fullscreen gate: deferring switch")
            return True
        return False


class DisturbanceController:
    def __init__(self, config: Dict[str, Any]):
        self.idle_threshold = config.get("idle_threshold", _DEFAULT_IDLE_THRESHOLD)

        # Playlist Switching Config
        self.playlist_min_interval   = config.get("min_interval",      _DEFAULT_PLAYLIST_MIN)
        self.playlist_force_interval = config.get("force_interval",    _DEFAULT_PLAYLIST_FORCE)

        # Wallpaper Cycling Config
        self.wallpaper_min_interval  = config.get("wallpaper_interval", _DEFAULT_WALLPAPER_MIN)

        # Build gate chain from config
        self._gates: List = []
        cpu_threshold = config.get("cpu_threshold", _DEFAULT_CPU_THRESHOLD)
        if cpu_threshold > 0:
            self._gates.append(CpuGate(cpu_threshold))
        if config.get("fullscreen_defer", True):
            self._gates.append(FullscreenGate())

        # If switch_on_start is False, pretend we just switched — the cooldown
        # will naturally block the first switch attempt.
        switch_on_start = config.get("switch_on_start", True)
        init_time = 0 if switch_on_start else time.time()
        self.last_playlist_switch_time = init_time
        self.last_wallpaper_switch_time = init_time

    def _any_gate_defers(self, context: Dict[str, Any]) -> bool:
        """Returns True if any gate wants to defer the current switch."""
        for gate in self._gates:
            if gate.should_defer(context):
                return True
        return False

    def can_switch_playlist(self, context: Dict[str, Any]) -> bool:
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
        idle_time = context.get("idle", 0.0)
        if idle_time >= self.idle_threshold:
            return True
        
        # 4. Force Switch Check
        if time_since_last >= self.playlist_force_interval:
            return True
            
        return False

    def can_cycle_wallpaper(self, context: Dict[str, Any]) -> bool:
        """
        Determines if cycling to the NEXT wallpaper within the SAME playlist is allowed.
        """
        current_time = time.time()
        time_since_last = current_time - self.last_wallpaper_switch_time
        
        # 1. Cooling Down Check (Strict)
        if time_since_last < self.wallpaper_min_interval:
            return False

        # 2. Gate chain — same defer semantics as playlist switching
        if self._any_gate_defers(context):
            return False

        # 3. Idle Check (Strict)
        # We only cycle wallpaper when user is idle to avoid distraction
        idle_time = context.get("idle", 0.0)
        if idle_time >= self.idle_threshold:
            return True
            
        return False

    def notify_playlist_switch(self):
        self.last_playlist_switch_time = time.time()
        # Switching playlist also counts as switching wallpaper
        self.last_wallpaper_switch_time = time.time()

    def notify_wallpaper_cycle(self):
        self.last_wallpaper_switch_time = time.time()
