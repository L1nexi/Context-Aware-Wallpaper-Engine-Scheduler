from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


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

    Field names match the keys in ``_SENSOR_REGISTRY``.  Any sensor that
    writes a key not listed here is stored in ``extra``.
    """
    window: WindowData = field(default_factory=WindowData)
    idle: float = 0.0
    cpu: float = 0.0
    fullscreen: bool = False
    weather: Optional[WeatherData] = None
    time: time.struct_time = field(default_factory=time.localtime)
    extra: Dict[str, Any] = field(default_factory=dict)
