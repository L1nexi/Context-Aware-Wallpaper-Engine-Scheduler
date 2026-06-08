from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging

from configurations.runtime_models import SchedulerConfig
from core.sensors.base import Sensor

logger = logging.getLogger("WEScheduler.Sensor")

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.UINT),
        ("dwTime", ctypes.wintypes.DWORD),
    ]


class IdleSensor(Sensor):
    key = "idle"

    @classmethod
    def create(cls, config: SchedulerConfig) -> IdleSensor | None:
        return cls()

    def collect(self) -> float:
        """Return the number of seconds the user has been idle."""
        return self.get_idle_duration()

    @staticmethod
    def get_idle_duration() -> float:
        """Calculate idle time via GetLastInputInfo + GetTickCount64."""
        try:
            lii = _LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
            if not _user32.GetLastInputInfo(ctypes.byref(lii)):
                logger.warning("GetLastInputInfo failed")
                return 0.0

            tick = _kernel32.GetTickCount64()
            return (tick - lii.dwTime) / 1000.0
        except Exception as e:
            logger.warning("IdleSensor collect failed: %s", e)
            return 0.0
