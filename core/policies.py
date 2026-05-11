from __future__ import annotations

import logging
import math
import re
import time as _time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Dict, Optional, Type

from core.context import Context
from core.diagnostics import (
    ActivityPolicyDetails,
    ActivityPolicyEvaluation,
    BasePolicyEvaluation,
    SeasonPolicyDetails,
    SeasonPolicyEvaluation,
    TimePolicyDetails,
    TimePolicyEvaluation,
    WeatherPolicyDetails,
    WeatherPolicyEvaluation,
)
from utils.runtime_config import (
    _BasePolicyConfig,
    ActivityPolicyConfig,
    PoliciesConfig,
    SeasonPolicyConfig,
    TimePolicyConfig,
    WeatherPolicyConfig,
)

logger = logging.getLogger("WEScheduler.Policy")

_MATCH_SOURCE_PRIORITY = {
    "process": 0,
    "title": 1,
}

_MATCH_TYPE_PRIORITY = {
    "contains": 0,
    "regex": 1,
    "exact": 2,
}


@dataclass(frozen=True)
class CompiledActivityMatcher:
    source: str
    match: str
    pattern: str
    tag: str
    case_sensitive: bool
    declaration_order: int
    regex: re.Pattern[str] | None = None

    @property
    def literal_length(self) -> int:
        if self.match == "regex":
            return 0
        return len(self.pattern)

    @property
    def priority(self) -> tuple[int, int, int, int]:
        return (
            _MATCH_SOURCE_PRIORITY[self.source],
            _MATCH_TYPE_PRIORITY[self.match],
            self.literal_length,
            -self.declaration_order,
        )


def _circular_distance(a: float, b: float, period: float) -> float:
    """Shortest distance between two points on a circle of given *period*."""
    d = abs(a - b) % period
    return min(d, period - d)


def _hann(d: float, H: float) -> float:
    """Hann window: 0.5·(1 + cos(π·d/H)) for d < H, else 0."""
    if d >= H:
        return 0.0
    return 0.5 * (1.0 + math.cos(math.pi * d / H))


class Policy(ABC):
    # Config key matching the attribute name on PoliciesConfig.
    # Each concrete subclass must define this as a class-level string.
    config_key: ClassVar[str]
    evaluation_cls: ClassVar[type[BasePolicyEvaluation]]
    fixed_output_tags: ClassVar[tuple[str, ...] | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "config_key" not in cls.__dict__:
            return
        valid_keys = set(PoliciesConfig.model_fields.keys())
        if cls.config_key not in valid_keys:
            raise TypeError(
                f"{cls.__name__}.config_key={cls.config_key!r} is not a field "
                f"of PoliciesConfig (valid: {sorted(valid_keys)}). "
                "Update runtime_config.py or the policy class."
            )
        if "fixed_output_tags" in cls.__dict__ and cls.fixed_output_tags is not None:
            if not isinstance(cls.fixed_output_tags, tuple) or any(
                not isinstance(tag, str) or not tag for tag in cls.fixed_output_tags
            ):
                raise TypeError(
                    f"{cls.__name__}.fixed_output_tags must be a tuple[str, ...] when provided."
                )

    def __init__(self, config: _BasePolicyConfig):
        self.config = config
        self.enabled = config.enabled
        self.weight = config.weight

    def _make_evaluation(
        self,
        *,
        details: object,
        raw_direction: Optional[Dict[str, float]],
        salience: float,
        intensity: float,
    ) -> BasePolicyEvaluation:
        raw_direction = raw_direction or {}
        active = False
        direction: Dict[str, float] = {}
        raw_contribution: Dict[str, float] = {}
        effective_magnitude = 0.0
        dominant_tag = max(raw_direction, key=raw_direction.get) if raw_direction else None

        if self.enabled and raw_direction and salience > 0 and intensity > 0:
            norm = math.sqrt(sum(weight * weight for weight in raw_direction.values()))
            if norm >= 1e-6:
                active = True
                direction = {
                    tag: weight / norm
                    for tag, weight in raw_direction.items()
                }
                effective_magnitude = salience * intensity * self.weight
                raw_contribution = {
                    tag: weight * effective_magnitude
                    for tag, weight in direction.items()
                }

        return self.evaluation_cls(
            policy_id=self.config_key,
            enabled=self.enabled,
            active=active,
            weight=self.weight,
            salience=max(salience, 0.0) if self.enabled else 0.0,
            intensity=max(intensity, 0.0) if self.enabled else 0.0,
            effective_magnitude=effective_magnitude,
            direction=direction,
            raw_contribution=raw_contribution,
            dominant_tag=dominant_tag,
            details=details,
        )

    @abstractmethod
    def evaluate(self, context: Context) -> BasePolicyEvaluation:
        ...

    def export_state(self) -> Dict[str, Any]:
        return {}

    def import_state(self, state: Dict[str, Any]) -> None:
        pass


class ActivityPolicy(Policy):
    config_key = "activity"
    evaluation_cls = ActivityPolicyEvaluation

    def __init__(self, config: ActivityPolicyConfig):
        super().__init__(config)
        self.matchers: list[CompiledActivityMatcher] = []
        for declaration_order, matcher in enumerate(config.matchers):
            compiled_regex = None
            if matcher.match == "regex":
                flags = 0 if matcher.case_sensitive else re.IGNORECASE
                compiled_regex = re.compile(matcher.pattern, flags)
            self.matchers.append(
                CompiledActivityMatcher(
                    source=matcher.source,
                    match=matcher.match,
                    pattern=matcher.pattern,
                    tag=matcher.tag,
                    case_sensitive=matcher.case_sensitive,
                    declaration_order=declaration_order,
                    regex=compiled_regex,
                )
            )

        smoothing_window = config.smoothing_window
        if smoothing_window <= 1:
            self.alpha = 1.0
        else:
            self.alpha = 2.0 / (smoothing_window + 1.0)

        self._dir_ema: Dict[str, float] = {}
        self._mag_ema: float = 0.0

    def evaluate(self, context: Context) -> ActivityPolicyEvaluation:
        if not self.enabled:
            return self._make_evaluation(
                details=ActivityPolicyDetails(
                    window_title=context.window.title,
                    process=context.window.process,
                ),
                raw_direction=None,
                salience=0.0,
                intensity=0.0,
            )

        instant_dir, details = self._get_instant_signal(context)

        all_tags = set(self._dir_ema.keys()) | set(instant_dir.keys())
        new_dir_ema: Dict[str, float] = {}
        for tag in all_tags:
            cur = instant_dir.get(tag, 0.0)
            prev = self._dir_ema.get(tag, 0.0)
            value = self.alpha * cur + (1.0 - self.alpha) * prev
            if value >= 1e-6:
                new_dir_ema[tag] = value
        self._dir_ema = new_dir_ema

        instant_mag = 1.0 if instant_dir else 0.0
        self._mag_ema = self.alpha * instant_mag + (1.0 - self.alpha) * self._mag_ema

        if not instant_dir:
            details.ema_active = bool(self._dir_ema)

        return self._make_evaluation(
            details=details,
            raw_direction=dict(self._dir_ema),
            salience=1.0 if self._dir_ema else 0.0,
            intensity=self._mag_ema if self._dir_ema else 0.0,
        )

    def _get_instant_signal(
        self,
        context: Context,
    ) -> tuple[Dict[str, float], ActivityPolicyDetails]:
        details = ActivityPolicyDetails(
            window_title=context.window.title,
            process=context.window.process,
        )

        matched = self._select_matcher(context)
        if matched is not None:
            details.match_source = matched.source
            details.matched_rule = matched.pattern
            details.matched_tag = matched.tag
            return {matched.tag: 1.0}, details

        return {}, details

    def _select_matcher(self, context: Context) -> CompiledActivityMatcher | None:
        matched: CompiledActivityMatcher | None = None

        for matcher in self.matchers:
            if not self._matcher_matches(matcher, context):
                continue
            if matched is None or matcher.priority > matched.priority:
                matched = matcher

        return matched

    def _matcher_matches(
        self,
        matcher: CompiledActivityMatcher,
        context: Context,
    ) -> bool:
        observed = context.window.process if matcher.source == "process" else context.window.title
        if matcher.match == "exact":
            return self._matches_exact(matcher, observed)
        if matcher.match == "contains":
            return self._matches_contains(matcher, observed)
        if matcher.regex is None:
            return False
        return matcher.regex.search(observed) is not None

    @staticmethod
    def _matches_exact(
        matcher: CompiledActivityMatcher,
        observed: str,
    ) -> bool:
        pattern = matcher.pattern
        if matcher.source == "process":
            pattern = ActivityPolicy._strip_optional_exe_suffix(pattern, matcher.case_sensitive)
            observed = ActivityPolicy._strip_optional_exe_suffix(observed, matcher.case_sensitive)

        if matcher.case_sensitive:
            return observed == pattern
        return observed.lower() == pattern.lower()

    @staticmethod
    def _matches_contains(
        matcher: CompiledActivityMatcher,
        observed: str,
    ) -> bool:
        if matcher.case_sensitive:
            return matcher.pattern in observed
        return matcher.pattern.lower() in observed.lower()

    @staticmethod
    def _strip_optional_exe_suffix(value: str, case_sensitive: bool) -> str:
        suffix = ".exe"
        if case_sensitive:
            return value[:-len(suffix)] if value.endswith(suffix) else value
        return value[:-len(suffix)] if value.lower().endswith(suffix) else value

    def export_state(self) -> Dict[str, Any]:
        return {
            "dir_ema": self._dir_ema.copy(),
            "mag_ema": self._mag_ema,
        }

    def import_state(self, state: Dict[str, Any]) -> None:
        allowed_tags = {matcher.tag for matcher in self.matchers}
        self._dir_ema = {
            tag: float(value)
            for tag, value in state.get("dir_ema", {}).items()
            if tag in allowed_tags
        }
        self._mag_ema = float(state.get("mag_ema", 0.0))



class TimePolicy(Policy):
    """Maps time-of-day to dawn/day/sunset/night via Hann windows."""

    config_key = "time"
    evaluation_cls = TimePolicyEvaluation
    fixed_output_tags = ("dawn", "day", "sunset", "night")

    def __init__(self, config: TimePolicyConfig):
        super().__init__(config)
        self._day_start: float = config.day_start_hour
        self._night_start: float = config.night_start_hour
        self.auto: bool = config.auto

        self._peaks: Dict[str, float] = {}
        self._H: float = 6.0
        self._recompute_peaks(self._day_start, self._night_start)

    @staticmethod
    def _compute_peaks(ds: float, ns: float) -> Dict[str, float]:
        day_span = (ns - ds) % 24
        night_span = 24 - day_span
        return {
            "dawn": ds,
            "day": (ds + day_span / 2) % 24,
            "sunset": ns % 24,
            "night": (ns + night_span / 2) % 24,
        }

    _TAG_ORDER = fixed_output_tags
    _VIRTUAL_PEAKS = [0.0, 6.0, 12.0, 18.0]

    @staticmethod
    def _warp_time(hour: float, peaks: Dict[str, float]) -> float:
        real = [peaks[tag] for tag in TimePolicy._TAG_ORDER]
        n = len(real)
        for i in range(n):
            r_a = real[i]
            r_b = real[(i + 1) % n]
            seg = (r_b - r_a) % 24
            pos = (hour - r_a) % 24
            if pos < seg:
                v_a = TimePolicy._VIRTUAL_PEAKS[i]
                return (v_a + pos / seg * 6.0) % 24
        return 0.0

    def _recompute_peaks(self, ds: float, ns: float) -> None:
        self._day_start = ds
        self._night_start = ns
        self._peaks = self._compute_peaks(ds, ns)

    def _update_from_context(self, context: Context) -> None:
        weather = context.weather
        if weather is None or not weather.sunrise or not weather.sunset:
            return
        sunrise = _time.localtime(weather.sunrise)
        sunset = _time.localtime(weather.sunset)
        ds = sunrise.tm_hour + sunrise.tm_min / 60.0
        ns = sunset.tm_hour + sunset.tm_min / 60.0
        if abs(ds - self._day_start) > 1 / 60 or abs(ns - self._night_start) > 1 / 60:
            self._recompute_peaks(ds, ns)
            logger.debug("TimePolicy peaks updated: day_start=%.2f night_start=%.2f", ds, ns)

    def evaluate(self, context: Context) -> TimePolicyEvaluation:
        current_time = context.time
        if self.auto:
            self._update_from_context(context)
        hour = current_time.tm_hour + current_time.tm_min / 60.0
        t_virtual = self._warp_time(hour, self._peaks)
        details = TimePolicyDetails(
            auto=self.auto,
            hour=round(hour, 4),
            virtual_hour=round(t_virtual, 4),
            day_start_hour=round(self._day_start, 4),
            night_start_hour=round(self._night_start, 4),
            peaks={tag: round(value, 4) for tag, value in self._peaks.items()},
        )
        if not self.enabled:
            return self._make_evaluation(
                details=details,
                raw_direction=None,
                salience=0.0,
                intensity=0.0,
            )

        best_weight = 0.0
        raw: Dict[str, float] = {}
        for tag, v_peak in zip(self._TAG_ORDER, self._VIRTUAL_PEAKS):
            distance = _circular_distance(t_virtual, v_peak, 24)
            weight = _hann(distance, self._H)
            if weight > 1e-4:
                raw[tag] = weight
                best_weight = max(best_weight, weight)
        return self._make_evaluation(
            details=details,
            raw_direction=raw,
            salience=best_weight,
            intensity=1.0 if raw else 0.0,
        )


class SeasonPolicy(Policy):
    """Maps day-of-year to spring/summer/autumn/winter via Hann windows."""

    config_key = "season"
    evaluation_cls = SeasonPolicyEvaluation
    fixed_output_tags = ("spring", "summer", "autumn", "winter")

    def __init__(self, config: SeasonPolicyConfig):
        super().__init__(config)
        self._peaks = {
            "spring": config.spring_peak,
            "summer": config.summer_peak,
            "autumn": config.autumn_peak,
            "winter": config.winter_peak,
        }
        self._H = 365 / len(self._peaks)

    def evaluate(self, context: Context) -> SeasonPolicyEvaluation:
        day_of_year = context.time.tm_yday
        details = SeasonPolicyDetails(
            day_of_year=day_of_year,
            peaks=self._peaks.copy(),
        )
        if not self.enabled:
            return self._make_evaluation(
                details=details,
                raw_direction=None,
                salience=0.0,
                intensity=0.0,
            )

        raw: Dict[str, float] = {}
        best_weight = 0.0
        for tag, peak in self._peaks.items():
            distance = _circular_distance(day_of_year, peak, 365)
            weight = _hann(distance, self._H)
            if weight > 1e-4:
                raw[tag] = weight
                best_weight = max(best_weight, weight)
        return self._make_evaluation(
            details=details,
            raw_direction=raw,
            salience=best_weight,
            intensity=1.0 if raw else 0.0,
        )


class WeatherPolicy(Policy):
    """Maps OWM condition codes to normalized weather tag contributions."""

    fixed_output_tags = ("clear", "cloudy", "rain", "storm", "snow", "fog")

    _ID_TAGS: Dict[int, Dict[str, float]] = {
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

    _MAIN_FALLBACK: Dict[str, Dict[str, float]] = {
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
    evaluation_cls = WeatherPolicyEvaluation

    def __init__(self, config: WeatherPolicyConfig):
        super().__init__(config)

    def evaluate(self, context: Context) -> WeatherPolicyEvaluation:
        weather = context.weather
        details = WeatherPolicyDetails(
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
    def _resolve_tags(cls, weather_id: int, weather_main: str) -> Optional[Dict[str, float]]:
        entry = cls._ID_TAGS.get(weather_id)
        if entry is not None:
            return dict(entry)
        fallback = cls._MAIN_FALLBACK.get(weather_main.lower())
        return dict(fallback) if fallback is not None else None


POLICY_REGISTRY: list[Type[Policy]] = [
    ActivityPolicy,
    TimePolicy,
    SeasonPolicy,
    WeatherPolicy,
]


def get_policy_fixed_output_tags() -> dict[str, tuple[str, ...]]:
    return {
        policy_cls.config_key: policy_cls.fixed_output_tags
        for policy_cls in POLICY_REGISTRY
        if policy_cls.fixed_output_tags is not None
    }


KNOWN_TAGS: list[str] = sorted({
    "focus", "chill",
    *(tag for tags in get_policy_fixed_output_tags().values() for tag in tags),
})
