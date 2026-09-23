from __future__ import annotations

from dataclasses import dataclass

import requests

CURRENT_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
VALIDATION_TIMEOUT_SECONDS = 8.0


class WeatherRejected(RuntimeError):
    """OpenWeatherMap rejected submitted weather settings."""

    code: str
    path: tuple[str, ...]


class InvalidApiKey(WeatherRejected):
    code = "weather_api_key_invalid"
    path = ("weather", "api_key")


class InvalidLocation(WeatherRejected):
    code = "weather_location_invalid"
    path = ("weather", "location")


class QuotaExceeded(WeatherRejected):
    code = "weather_api_quota_exceeded"
    path = ("weather", "api_key")


class WeatherUnavailable(RuntimeError):
    """OpenWeatherMap could not complete a weather request."""


@dataclass(frozen=True)
class WeatherObservation:
    id: int
    main: str
    sunrise: int
    sunset: int


def fetch_weather(
    api_key: str,
    latitude: float,
    longitude: float,
    *,
    timeout: float = VALIDATION_TIMEOUT_SECONDS,
) -> WeatherObservation:
    """Fetch and parse the current weather.

    Raises:
        WeatherRejected: If the service rejects the settings or quota.
        WeatherUnavailable: If the request fails or its response is unusable.
    """
    try:
        response = requests.get(
            CURRENT_WEATHER_URL,
            params={"lat": latitude, "lon": longitude, "appid": api_key, "units": "metric"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise WeatherUnavailable("weather service is unavailable") from exc

    if response.status_code == 200:
        try:
            payload = response.json()
        except ValueError as exc:
            raise WeatherUnavailable("weather service returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise WeatherUnavailable("weather service returned invalid data")
        conditions = payload.get("weather")
        if not isinstance(conditions, list) or not conditions or not isinstance(conditions[0], dict):
            raise WeatherUnavailable("weather service returned incomplete data")
        condition = conditions[0]
        weather_id = condition.get("id")
        main = condition.get("main")
        if isinstance(weather_id, bool) or not isinstance(weather_id, int) or not isinstance(main, str) or not main:
            raise WeatherUnavailable("weather service returned incomplete data")
        sun_times = payload.get("sys") or {}
        if not isinstance(sun_times, dict):
            raise WeatherUnavailable("weather service returned invalid data")
        sunrise = sun_times.get("sunrise", 0)
        sunset = sun_times.get("sunset", 0)
        if not isinstance(sunrise, int) or not isinstance(sunset, int):
            raise WeatherUnavailable("weather service returned invalid data")
        return WeatherObservation(id=weather_id, main=main, sunrise=sunrise, sunset=sunset)
    if response.status_code == 401:
        raise InvalidApiKey("weather API key is invalid")
    if response.status_code in {400, 404}:
        raise InvalidLocation("weather location is invalid")
    if response.status_code == 429:
        raise QuotaExceeded("weather API quota exceeded")
    raise WeatherUnavailable(f"weather service returned HTTP {response.status_code}")


def validate_weather_connection(api_key: str, latitude: float, longitude: float) -> None:
    """Verify weather settings with a parsed observation.

    Raises:
        WeatherRejected: If the service rejects the settings or quota.
        WeatherUnavailable: If the request fails or its response is unusable.
    """
    fetch_weather(api_key, latitude, longitude)
