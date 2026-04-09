import win32gui
import win32process
import win32api
import ctypes
import time
import requests
import psutil
import logging
from collections import deque
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger("WEScheduler.Sensor")

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


class CpuSensor(Sensor):
    """Returns a rolling-average CPU utilisation (0.0–100.0) over a sliding window.

    Uses psutil.cpu_percent(interval=None) — non-blocking, measures since the
    previous call.  The first call after import always returns 0.0 (psutil
    limitation); we prime it in __init__ so the actual first collect() value
    is meaningful.

    Window size guideline: at 1 s/tick a window of 10 gives a 10-second
    smoothed view — short spikes (page-faults, disk flush) don't trip the
    gate; sustained loads (gaming, compilation, training) do.
    """

    def __init__(self, window: int = 10) -> None:
        self._samples: deque[float] = deque(maxlen=window)
        # Prime psutil's internal baseline so the first collect() measurement
        # covers a real ~1 s interval rather than returning 0.0.
        psutil.cpu_percent()

    def collect(self) -> float:
        sample = psutil.cpu_percent()
        self._samples.append(sample)
        return sum(self._samples) / len(self._samples)


class FullscreenSensor(Sensor):
    """Detects fullscreen or presentation-mode applications via Win32 API.

    Uses SHQueryUserNotificationState (shell32.dll) which reliably detects:
    - D3D exclusive fullscreen (games)
    - Presentation mode (PowerPoint, etc.)
    - Generic full-screen applications
    """

    _FULLSCREEN_STATES = frozenset({
        2,  # QUNS_BUSY — full-screen app running or Presentation Settings applied
        3,  # QUNS_RUNNING_D3D_FULL_SCREEN — D3D exclusive fullscreen
        4,  # QUNS_PRESENTATION_MODE — presentation mode active
    })

    def collect(self) -> bool:
        try:
            state = ctypes.c_int(0)
            ctypes.windll.shell32.SHQueryUserNotificationState(
                ctypes.byref(state)
            )
            return state.value in self._FULLSCREEN_STATES
        except Exception:
            return False


class WeatherSensor(Sensor):
    """Periodically fetches weather data from OpenWeatherMap 2.5 /weather.

    Returns a dict with weather code, main category, and sunrise/sunset
    timestamps.  Cached for ``interval`` seconds between API calls.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.api_key: str = config.get("api_key", "")
        self.lat: str = str(config.get("lat", ""))
        self.lon: str = str(config.get("lon", ""))
        self.interval: float = config.get("interval", 600)
        self.timeout: float = config.get("request_timeout", 10)

        self._last_fetch: float = 0.0
        self._cached: Optional[Dict[str, Any]] = None

    def collect(self) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return self._cached

        now = time.time()
        # Rate-limit regardless of whether the previous fetch succeeded:
        # _last_fetch > 0 means at least one attempt has been made.
        if self._last_fetch > 0 and (now - self._last_fetch) < self.interval:
            return self._cached

        try:
            resp = requests.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={
                    "lat": self.lat,
                    "lon": self.lon,
                    "appid": self.api_key,
                    "units": "metric",
                },
                timeout=self.timeout,
                proxies={"http": None, "https": None},
            )
            if resp.ok:
                data = resp.json()
                first = (data.get("weather") or [{}])[0]
                sys_block = data.get("sys") or {}
                self._cached = {
                    "id": first.get("id", 0),
                    "main": first.get("main", ""),
                    "sunrise": sys_block.get("sunrise", 0),
                    "sunset": sys_block.get("sunset", 0),
                }
                logger.info(
                    "Weather updated: id=%d main=%s sunrise=%d sunset=%d",
                    self._cached["id"], self._cached["main"],
                    self._cached["sunrise"], self._cached["sunset"],
                )
            else:
                logger.warning("Weather API error: %d", resp.status_code)
        except Exception as e:
            logger.warning("Weather fetch failed: %s", e)

        self._last_fetch = now
        return self._cached
