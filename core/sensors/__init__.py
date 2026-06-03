from core.sensors.base import Sensor
from core.sensors.cpu import CpuSensor
from core.sensors.fullscreen import FullscreenSensor
from core.sensors.idle import IdleSensor
from core.sensors.time import TimeSensor
from core.sensors.weather import WeatherSensor
from core.sensors.window import WindowSensor

SENSOR_REGISTRY: list[type[Sensor]] = [
    WindowSensor,
    IdleSensor,
    CpuSensor,
    FullscreenSensor,
    WeatherSensor,
    TimeSensor,
]

__all__ = [
    "Sensor",
    "WindowSensor",
    "IdleSensor",
    "CpuSensor",
    "FullscreenSensor",
    "WeatherSensor",
    "TimeSensor",
    "SENSOR_REGISTRY",
]
