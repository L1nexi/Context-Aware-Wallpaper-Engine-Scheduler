from __future__ import annotations

import copy
import dataclasses
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.sensors import Sensor

logger = logging.getLogger("WEScheduler.Context")


@dataclass
class WindowData:
    title: str = ""
    process: str = ""


@dataclass
class WeatherData:
    id: int = 0
    main: str = ""
    sunrise: int = 0  # UTC unix timestamp
    sunset: int = 0  # UTC unix timestamp
    fetched_at: float = 0.0
    stale: bool = False


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
    weather: WeatherData | None = None
    time: time.struct_time = field(default_factory=time.localtime)


_CONTEXT_FIELD_NAMES: frozenset[str] = frozenset(f.name for f in dataclasses.fields(Context))


class ContextManager:
    def __init__(self):
        self._sensors: list[tuple[str, Sensor]] = []
        self._context: Context = Context()

    def register_sensor(self, sensor: Sensor | None) -> None:
        """Register a sensor.

        The sensor's ``key`` class attribute must match a field on
        :class:`Context`.  This enforces ``Context`` as the single
        authoritative schema: add a field there first, then register the
        sensor.  Passing ``None`` is a no-op so sensor factories can return
        ``None`` to signal "do not register".
        """
        if sensor is None:
            return
        key = sensor.key
        if key not in _CONTEXT_FIELD_NAMES:
            raise ValueError(f"Sensor key {key!r} has no corresponding field on Context. Add the field to core/context.py before registering.")
        self._sensors.append((key, sensor))

    def refresh(self) -> Context:
        """Poll all registered sensors and update the context snapshot."""
        for key, sensor in self._sensors:
            try:
                value = sensor.collect()
                setattr(self._context, key, value)
            except Exception as e:
                logger.warning(f"Error collecting from sensor '{key}': {e}")
        return self._context

    def sense(self) -> Context:
        return copy.deepcopy(self.refresh())
