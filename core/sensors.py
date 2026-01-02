import win32gui
import win32process
import win32api
import psutil
from typing import Dict, Any
from abc import ABC, abstractmethod

class Sensor(ABC):
    @abstractmethod
    def collect(self) -> Any:
        """Collects data from the sensor."""
        pass

class WindowSensor(Sensor):
    def collect(self) -> Dict[str, str]:
        """
        Returns a dictionary containing the active window's title and process name.
        """
        return self.get_active_window_info()

    def get_active_window_info(self) -> Dict[str, str]:
        """
        Legacy method, kept for internal logic.
        Returns a dictionary containing the active window's title and process name.
        """
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return {"title": "", "process": ""}

            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            
            try:
                process = psutil.Process(pid)
                process_name = process.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                process_name = "Unknown"

            return {
                "title": title,
                "process": process_name
            }
        except Exception as e:
            # In case of any unexpected win32 API failure
            return {"title": "", "process": "", "error": str(e)}

class IdleSensor(Sensor):
    def collect(self) -> float:
        """
        Returns the number of seconds the user has been idle.
        """
        return self.get_idle_duration()

    def get_idle_duration(self) -> float:
        """
        Calculates idle time based on GetLastInputInfo.
        """
        try:
            last_input_info = win32api.GetLastInputInfo()
            tick_count = win32api.GetTickCount()
            idle_milliseconds = tick_count - last_input_info
            return idle_milliseconds / 1000.0
        except Exception:
            return 0.0

if __name__ == "__main__":
    import time
    sensor = WindowSensor()
    while True:
        info = sensor.get_active_window_info()
        print(f"Active: {info.get('process')} - {info.get('title')}")
        time.sleep(1)