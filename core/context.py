from __future__ import annotations

import dataclasses
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from core.sensors import Sensor

logger = logging.getLogger("WEScheduler.Context")

@dataclass
class WindowData:
    """Active-window snapshot provided by WindowSensor."""
    title: str = ""
    process: str = ""


@dataclass
class WeatherData:
    """Weather snapshot provided by WeatherSensor (OWM /weather)."""
    id: int = 0
    main: str = ""
    sunrise: int = 0  # UTC unix timestamp
    sunset: int = 0   # UTC unix timestamp


@dataclass
class Context:
    """Typed snapshot of all sensor readings for one scheduler tick.

    Field names match sensor keys in ``_SENSOR_REGISTRY``.  Any sensor whose
    key is not listed here will be rejected at registration time; add the
    field here first, then add the sensor.
    """
    window: WindowData = field(default_factory=WindowData)
    idle: float = 0.0
    cpu: float = 0.0
    fullscreen: bool = False
    weather: Optional[WeatherData] = None
    time: time.struct_time = field(default_factory=time.localtime)
    extra: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ContextManager
# ---------------------------------------------------------------------------

# Authoritative set of keys that sensors may populate directly on Context.
# Derived from the dataclass at import time so it stays in sync automatically.
_CONTEXT_FIELD_NAMES: frozenset = frozenset(
    f.name for f in dataclasses.fields(Context) if f.name != "extra"
)


class ContextManager:
    def __init__(self):
        self._sensors: List[Tuple[str, Sensor]] = []
        self._context: Context = Context()

    def register_sensor(self, sensor: Optional[Sensor]) -> None:
        """Register a sensor.

        The sensor's ``key`` class attribute must match a field on
        :class:`Context` (excluding ``extra``).  This enforces ``Context``
        as the single authoritative schema: add a field there first, then
        register the sensor.  Passing ``None`` is a no-op so sensor factories
        can return ``None`` to signal "do not register".
        """
        if sensor is None:
            return
        key = sensor.key
        if key not in _CONTEXT_FIELD_NAMES:
            raise ValueError(
                f"Sensor key {key!r} has no corresponding field on Context. "
                "Add the field to core/context.py before registering."
            )
        self._sensors.append((key, sensor))

    def refresh(self) -> Context:
        """Poll all registered sensors and update the context snapshot."""
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

