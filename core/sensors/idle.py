from __future__ import annotations

import win32api

from configurations.runtime_models import SchedulerConfig
from core.sensors.base import Sensor


class IdleSensor(Sensor):
    key = "idle"

    @classmethod
    def create(cls, config: SchedulerConfig) -> IdleSensor | None:
        return cls()

    def collect(self) -> float:
        """
        Returns the number of seconds the user has been idle.
        """
        return self.get_idle_duration()

    def get_idle_duration(self) -> float:
        """
        Calculates idle time based on GetLastInputInfo.
        """
        try:
            last_input_info = win32api.GetLastInputInfo()
            tick_count = win32api.GetTickCount()
            idle_milliseconds = tick_count - last_input_info
            return idle_milliseconds / 1000.0
        except Exception:
            return 0.0
