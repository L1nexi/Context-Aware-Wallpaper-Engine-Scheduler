from __future__ import annotations

import logging
from typing import List, Tuple, Optional, TYPE_CHECKING

from core.context_types import Context

if TYPE_CHECKING:
    from core.sensors import Sensor

logger = logging.getLogger("WEScheduler.Context")

class ContextManager:
    def __init__(self):
        self._sensors: List[Tuple[str, Sensor]] = []
        self._context: Context = Context()

    def register_sensor(self, key: str, sensor: Optional[Sensor]) -> None:
        """Registers a sensor with a specific key in the context.
        Passing ``None`` is a no-op, allowing sensor factories to signal
        'do not register' without any conditional logic at the call site.
        """
        if sensor is not None:
            self._sensors.append((key, sensor))

    def refresh(self) -> Context:
        """Polls all registered sensors and updates the context."""
        for key, sensor in self._sensors:
            try:
                value = sensor.collect()
                if hasattr(self._context, key):
                    setattr(self._context, key, value)
                else:
                    self._context.extra[key] = value
            except Exception as e:
                logger.warning(f"Error collecting from sensor '{key}': {e}")
        return self._context

    def get_context(self) -> Context:
        return self._context

