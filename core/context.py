import logging
from typing import Dict, Any, List, Tuple
import time
from core.sensors import Sensor

logger = logging.getLogger("WEScheduler.Context")

class ContextManager:
    def __init__(self):
        self._sensors: List[Tuple[str, Sensor]] = []
        self._context: Dict[str, Any] = {}

    def register_sensor(self, key: str, sensor: Sensor) -> None:
        """Registers a sensor with a specific key in the context."""
        self._sensors.append((key, sensor))

    def refresh(self) -> Dict[str, Any]:
        """
        Polls all registered sensors and updates the context.
        Also adds global context like time.
        """
        # 1. Collect from Sensors
        for key, sensor in self._sensors:
            try:
                self._context[key] = sensor.collect()
            except Exception as e:
                logger.warning("Error collecting from sensor '%s': %s", key, e)
                self._context[key] = {}

        # 2. Add Global/System Context
        # In a real system, Time might be its own sensor, but it's simple enough to keep here for now
        self._context["time"] = time.localtime()
        
        return self._context

    def get_context(self) -> Dict[str, Any]:
        return self._context
