from __future__ import annotations

import logging
import threading
import time

from configurations.runtime_models import SchedulerConfig, WeatherPolicyConfig
from core.models.context import WeatherData
from core.sensors.base import Sensor
from integrations.openweather import fetch_weather

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
            observation = fetch_weather(
                self.api_key,
                self.lat,
                self.lon,
                timeout=self.timeout,
            )
            self._cached = WeatherData(
                id=observation.id,
                main=observation.main,
                sunrise=observation.sunrise,
                sunset=observation.sunset,
            )
            logger.info(
                "Weather updated: id=%s main=%s sunrise=%s sunset=%s",
                observation.id,
                observation.main,
                observation.sunrise,
                observation.sunset,
            )
        except Exception as e:
            logger.warning("Weather fetch failed: %s", e)
        finally:
            self._fetching = False

    @classmethod
    def create(cls, config: SchedulerConfig) -> WeatherSensor | None:
        """Return a new instance only when an API key and coordinates are present."""
        weather_cfg = config.policies.weather
        if not weather_cfg.api_key or weather_cfg.lat is None or weather_cfg.lon is None:
            return None
        return cls(weather_cfg)
