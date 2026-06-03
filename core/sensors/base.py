from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from configurations.runtime_models import SchedulerConfig

logger = logging.getLogger("WEScheduler.Sensor")


class Sensor(ABC):
    key: ClassVar[str]

    @abstractmethod
    def collect(self) -> Any:
        """Collects data from the sensor."""
        pass

    @classmethod
    @abstractmethod
    def create(cls, config: SchedulerConfig) -> Sensor | None:
        """Factory method: return a ready instance, or None to skip registration."""
        pass
