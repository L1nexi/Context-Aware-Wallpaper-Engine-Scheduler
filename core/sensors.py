from __future__ import annotations
import win32gui
import win32process
import win32api
import ctypes
import time
import threading
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

    @abstractmethod
    def create(cls, policy_cfg: Dict, disturbance_cfg: Dict) -> Optional[Sensor]:
        """
            Factory method to create a sensor instance based on configuration.
            Returns None if the sensor should not be registered (e.g., disabled / missing arguments).
        """
        pass

class WindowSensor(Sensor):
    @classmethod
    def create(cls, policy_cfg: Dict, disturbance_cfg: Dict) -> Optional[WindowSensor]:
        return cls()

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
    @classmethod
    def create(cls, policy_cfg: Dict, disturbance_cfg: Dict) -> Optional[IdleSensor]:
        return cls()

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

    @classmethod
    def create(cls, policy_cfg: Dict, disturbance_cfg: Dict) -> Optional[CpuSensor]:
        return cls(window=disturbance_cfg.get("cpu_window", 10))

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

    @classmethod
    def create(cls, policy_cfg: Dict, disturbance_cfg: Dict) -> Optional[FullscreenSensor]:
        """Return a new instance only when fullscreen-defer is enabled."""
        if not disturbance_cfg.get("fullscreen_defer", True):
            return None
        return cls()


class WeatherSensor(Sensor):
    """Periodically fetches weather data from OpenWeatherMap 2.5 /weather.

    Returns a dict with weather code, main category, and sunrise/sunset
    timestamps.  Cached for ``interval`` seconds between API calls.

    The HTTP request is executed in a background daemon thread so that
    ``collect()`` always returns immediately with the cached value, never
    blocking the 1-second scheduler tick.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.api_key: str = config.get("api_key", "")
        self.lat: str = str(config.get("lat", ""))
        self.lon: str = str(config.get("lon", ""))
        self.interval: float = config.get("interval", 600)
        self.timeout: float = config.get("request_timeout", 10)

        self._last_fetch: float = 0.0
        self._cached: Optional[Dict[str, Any]] = None
        self._fetching: bool = False  # guard: only one background thread at a time
        self._ready_event = threading.Event()  # set after first fetch attempt completes

        # Start the first fetch eagerly and block until it resolves or times out.
        # This happens inside __init__ so the scheduler tick loop is never blocked;
        # the brief wait is absorbed by the rest of initialize().
        warmup_timeout: float = config.get("warmup_timeout", 3.0)
        self._last_fetch = time.time()
        self._fetching = True
        threading.Thread(target=self._fetch_async, daemon=True).start()
        self._ready_event.wait(timeout=warmup_timeout)

    def collect(self) -> Optional[Dict[str, Any]]:
        now = time.time()
        # Rate-limit: once _last_fetch is set, wait at least interval before retry.
        # _last_fetch is set *before* the thread starts so rapid collect() calls
        # during a fetch don't spawn multiple concurrent threads.
        if self._last_fetch > 0 and (now - self._last_fetch) < self.interval:
            return self._cached

        if not self._fetching:
            self._last_fetch = now
            self._fetching = True
            threading.Thread(target=self._fetch_async, daemon=True).start()

        return self._cached

    def _fetch_async(self) -> None:
        """Background fetch — updates ``_cached`` on success, never blocks tick loop."""
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
                    f"Weather updated: id={self._cached['id']} main={self._cached['main']} "
                    f"sunrise={self._cached['sunrise']} sunset={self._cached['sunset']}"
                )
            else:
                logger.warning(f"Weather API error: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Weather fetch failed: {e}")
        finally:
            self._fetching = False
            self._ready_event.set()

    @classmethod
    def create(cls, policy_cfg: Dict, disturbance_cfg: Dict) -> Optional[WeatherSensor]:
        """Return a new instance only when the sensor is enabled and an API key is present."""
        weather_cfg = policy_cfg.get("weather", {})
        if not weather_cfg.get("enabled", True) or not weather_cfg.get("api_key"):
            return None
        return cls(weather_cfg)

class TimeSensor(Sensor):
    @classmethod
    def create(cls, policy_cfg: Dict, disturbance_cfg: Dict) -> Optional[TimeSensor]:
        return cls()

    def collect(self) -> time.struct_time:
        """Returns the current local time as a struct_time."""
        return time.localtime()