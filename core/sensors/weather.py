from __future__ import annotations

import logging
import threading
import time

import requests

from configurations.runtime_models import SchedulerConfig, WeatherPolicyConfig
from core.models.context import WeatherData
from core.sensors.base import Sensor

logger = logging.getLogger("WEScheduler.Sensor")


class WeatherSensor(Sensor):
    key = "weather"

    def __init__(self, config: WeatherPolicyConfig) -> None:
        self.api_key: str = config.api_key
        self.lat: float = float(config.lat)
        self.lon: float = float(config.lon)
        self.interval: float = config.fetch_interval
        self.timeout: float = config.request_timeout

        self._last_fetch: float = 0.0
        self._cached: WeatherData | None = None
        self._fetching: bool = False  # guard: only one background thread at a time

    def collect(self) -> WeatherData | None:
        now = time.time()

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
            )
            if resp.ok:
                data = resp.json()
                first = (data.get("weather") or [{}])[0]
                sys_block = data.get("sys") or {}
                self._cached = WeatherData(
                    id=first.get("id", 0),
                    main=first.get("main", ""),
                    sunrise=sys_block.get("sunrise", 0),
                    sunset=sys_block.get("sunset", 0),
                )
                logger.info(
                    f"Weather updated: id={self._cached.id} main={self._cached.main} sunrise={self._cached.sunrise} sunset={self._cached.sunset}"
                )
            else:
                logger.warning(f"Weather API error: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Weather fetch failed: {e}")
        finally:
            self._fetching = False

    @classmethod
    def create(cls, config: SchedulerConfig) -> WeatherSensor | None:
        """Return a new instance only when the sensor is enabled and an API key is present."""
        weather_cfg = config.policies.weather
        if not weather_cfg.enabled or not weather_cfg.api_key or weather_cfg.lat is None or weather_cfg.lon is None:
            return None
        return cls(weather_cfg)
