from __future__ import annotations

import ctypes

from configurations.runtime_models import SchedulerConfig
from core.sensors.base import Sensor


class FullscreenSensor(Sensor):
    key = "fullscreen"

    _FULLSCREEN_STATES = frozenset(
        {
            2,  # QUNS_BUSY — full-screen app running or Presentation Settings applied
            3,  # QUNS_RUNNING_D3D_FULL_SCREEN — D3D exclusive fullscreen
            4,  # QUNS_PRESENTATION_MODE — presentation mode active
        }
    )

    def collect(self) -> bool:
        try:
            state = ctypes.c_int(0)
            ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state))
            return state.value in self._FULLSCREEN_STATES
        except Exception:
            return False

    @classmethod
    def create(cls, config: SchedulerConfig) -> FullscreenSensor | None:
        """Return a new instance only when fullscreen-defer is enabled."""
        if not config.scheduling.pause_on_fullscreen:
            return None
        return cls()
