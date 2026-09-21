from __future__ import annotations

import threading

from configurations.runtime_models import WeatherPolicyConfig
from core.sensors.weather import WeatherSensor


class _Response:
    ok = True

    @staticmethod
    def json():
        return {
            "weather": [{"id": 800, "main": "Clear"}],
            "sys": {"sunrise": 1, "sunset": 2},
        }


def _config() -> WeatherPolicyConfig:
    return WeatherPolicyConfig(api_key="key", lat=31.0, lon=121.0)


def test_weather_sensor_construction_makes_no_request(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr("core.sensors.weather.requests.get", lambda *_args, **_kwargs: calls.append(1))

    WeatherSensor(_config())

    assert calls == []


def test_weather_sensor_starts_first_fetch_on_collect(monkeypatch):
    fetched = threading.Event()

    def fake_get(*_args, **_kwargs):
        fetched.set()
        return _Response()

    monkeypatch.setattr("core.sensors.weather.requests.get", fake_get)
    sensor = WeatherSensor(_config())

    sensor.collect()

    assert fetched.wait(timeout=1)
