from __future__ import annotations

import math

from configurations.runtime_models import WeatherPolicyConfig
from core.models.context import Context
from core.models.trace import WeatherDetails, WeatherEvaluation
from core.policies.base import Policy


class WeatherPolicy(Policy):
    """Maps OWM condition codes to normalized weather tag contributions."""

    fixed_output_tags = ("clear", "cloudy", "rain", "storm", "snow", "fog")

    _ID_TAGS: dict[int, dict[str, float]] = {
        210: {"storm": 0.50, "rain": 0.25},
        211: {"storm": 0.75, "rain": 0.50},
        212: {"storm": 1.00, "rain": 0.60},
        221: {"storm": 0.90, "rain": 0.50},
        200: {"storm": 0.67, "rain": 0.34},
        201: {"storm": 0.80, "rain": 0.40},
        202: {"storm": 0.89, "rain": 0.45},
        230: {"storm": 0.62, "rain": 0.21},
        231: {"storm": 0.71, "rain": 0.24},
        232: {"storm": 0.80, "rain": 0.36},
        300: {"rain": 0.25},
        301: {"rain": 0.40},
        302: {"rain": 0.55},
        310: {"rain": 0.30},
        311: {"rain": 0.50},
        312: {"rain": 0.60},
        313: {"rain": 0.50},
        314: {"rain": 0.65},
        321: {"rain": 0.50},
        500: {"rain": 0.40},
        501: {"rain": 0.65},
        502: {"rain": 0.85},
        503: {"rain": 1.00},
        504: {"rain": 1.00},
        511: {"rain": 0.53, "snow": 0.27},
        520: {"rain": 0.45},
        521: {"rain": 0.65},
        522: {"rain": 0.90},
        531: {"rain": 0.70},
        600: {"snow": 0.40},
        601: {"snow": 0.70},
        602: {"snow": 1.00},
        611: {"snow": 0.39, "rain": 0.39},
        612: {"snow": 0.32, "rain": 0.32},
        613: {"snow": 0.35, "rain": 0.35},
        615: {"rain": 0.35, "snow": 0.35},
        616: {"rain": 0.42, "snow": 0.42},
        620: {"snow": 0.40},
        621: {"snow": 0.65},
        622: {"snow": 1.00},
        701: {"fog": 0.30},
        711: {"fog": 0.45},
        721: {"fog": 0.25},
        731: {"fog": 0.25},
        741: {"fog": 0.75},
        751: {"fog": 0.30},
        761: {"fog": 0.40},
        762: {"fog": 0.60},
        771: {"storm": 0.65},
        781: {"storm": 1.00},
        800: {"clear": 0.50},
        801: {"clear": 0.47, "cloudy": 0.16},
        802: {"clear": 0.35, "cloudy": 0.35},
        803: {"cloudy": 0.47, "clear": 0.16},
        804: {"cloudy": 0.50},
    }

    _MAIN_FALLBACK: dict[str, dict[str, float]] = {
        "thunderstorm": {"storm": 0.67, "rain": 0.34},
        "drizzle": {"rain": 0.40},
        "rain": {"rain": 0.65},
        "snow": {"snow": 0.65},
        "mist": {"fog": 0.30},
        "smoke": {"fog": 0.45},
        "haze": {"fog": 0.25},
        "dust": {"fog": 0.40},
        "fog": {"fog": 0.75},
        "sand": {"fog": 0.30},
        "ash": {"fog": 0.55},
        "squall": {"storm": 0.65},
        "tornado": {"storm": 1.00},
        "clear": {"clear": 0.50},
        "clouds": {"cloudy": 0.50},
    }

    config_key = "weather"
    evaluation_cls = WeatherEvaluation

    def __init__(self, config: WeatherPolicyConfig):
        super().__init__(config)

    def evaluate(self, context: Context) -> WeatherEvaluation:
        weather = context.weather
        details = WeatherDetails(
            weather_id=weather.id if weather is not None else None,
            weather_main=weather.main if weather is not None else None,
            available=weather is not None,
        )
        if not self.enabled:
            return self._make_evaluation(
                details=details,
                raw_direction=None,
                salience=0.0,
                intensity=0.0,
            )

        if weather is None:
            return self._make_evaluation(
                details=details,
                raw_direction=None,
                salience=0.0,
                intensity=0.0,
            )

        raw = self._resolve_tags(weather.id, weather.main)
        if not raw:
            return self._make_evaluation(
                details=details,
                raw_direction=None,
                salience=0.0,
                intensity=0.0,
            )

        details.mapped = True
        norm = math.sqrt(sum(weight * weight for weight in raw.values()))
        return self._make_evaluation(
            details=details,
            raw_direction=raw,
            salience=1.0,
            intensity=norm,
        )

    @classmethod
    def _resolve_tags(cls, weather_id: int, weather_main: str) -> dict[str, float] | None:
        entry = cls._ID_TAGS.get(weather_id)
        if entry is not None:
            return dict(entry)
        fallback = cls._MAIN_FALLBACK.get(weather_main.lower())
        return dict(fallback) if fallback is not None else None
