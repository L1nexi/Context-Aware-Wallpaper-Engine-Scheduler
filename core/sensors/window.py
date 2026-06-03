from __future__ import annotations

import logging

import psutil
import win32gui
import win32process

from configurations.runtime_models import SchedulerConfig
from core.models.context import WindowData
from core.sensors.base import Sensor

logger = logging.getLogger("WEScheduler.Sensor")


class WindowSensor(Sensor):
    key = "window"

    @classmethod
    def create(cls, config: SchedulerConfig) -> WindowSensor | None:
        return cls()

    def collect(self) -> WindowData:
        """Returns the active window's title and process name."""
        return self.get_active_window_info()

    def get_active_window_info(self) -> WindowData:
        """Returns active window info as a WindowData instance."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return WindowData()

            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)

            try:
                process = psutil.Process(pid)
                process_name = process.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                process_name = "Unknown"

            return WindowData(title=title, process=process_name)
        except Exception as e:
            logger.warning(f"WindowSensor error: {e}")
            return WindowData()
