from __future__ import annotations

import time

from configurations.runtime_models import SchedulerConfig
from core.sensors.base import Sensor


class TimeSensor(Sensor):
    key = "time"

    @classmethod
    def create(cls, config: SchedulerConfig) -> TimeSensor | None:
        return cls()

    def collect(self) -> time.struct_time:
        """Returns the current local time as a struct_time."""
        return time.localtime()
