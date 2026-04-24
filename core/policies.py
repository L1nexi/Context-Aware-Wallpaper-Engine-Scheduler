import logging
import math
import time as _time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, Dict, Any, List, Optional, Union

from core.context import Context
from utils.config_loader import (
    _BasePolicyConfig,
    ActivityPolicyConfig,
    TimePolicyConfig,
    SeasonPolicyConfig,
    WeatherPolicyConfig,
    PoliciesConfig,
)

logger = logging.getLogger("WEScheduler.Policy")


@dataclass
class PolicyOutput:
    """Decomposed policy signal with orthogonal semantic dimensions.

    direction: unit L2-normalized tag vector (what kind of signal)
    salience:  clarity of category membership [0,1]; default 1.0
    intensity: physical/behavioral magnitude [0,1]; default 1.0

    Effective contribution to the env vector:
        direction * salience * intensity * weight_scale
    """
    direction: Dict[str, float]
    salience: float = 1.0
    intensity: float = 1.0


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

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "config_key" not in cls.__dict__:
            return
        valid_keys = set(PoliciesConfig.model_fields.keys())
        if cls.config_key not in valid_keys:
            raise TypeError(
                f"{cls.__name__}.config_key={cls.config_key!r} is not a field "
                f"of PoliciesConfig (valid: {sorted(valid_keys)}). "
                "Update config_loader.py or the policy class."
            )

    def __init__(self, config: _BasePolicyConfig):
        self.config = config
        self.enabled = config.enabled
        self.weight_scale = config.weight_scale

    @abstractmethod
    def _compute_output(self, context: Context) -> Optional[PolicyOutput]:
        """Compute raw PolicyOutput; direction need not be normalized."""
        ...

    def get_output(self, context: Context) -> Optional[PolicyOutput]:
        """Public interface. Normalizes direction to unit L2; returns None if zero."""
        output = self._compute_output(context)
        if output is None:
            return None
        norm = math.sqrt(sum(w * w for w in output.direction.values()))
        if norm < 1e-6:
            return None
        output.direction = {t: w / norm for t, w in output.direction.items()}
        return output

    def export_state(self) -> Dict[str, Any]:
        return {}

    def import_state(self, state: Dict[str, Any]) -> None:
        pass


class ActivityPolicy(Policy):
    config_key = "activity"

    def __init__(self, config: ActivityPolicyConfig):
        super().__init__(config)
        # Convert rules to lowercase for case-insensitive matching
        self.rules = {k.lower(): v for k, v in config.process_rules.items()}
        self.title_rules = config.title_rules

        smoothing_window = config.smoothing_window
        # Calculate alpha for EMA: alpha = 2 / (N + 1)
        if smoothing_window <= 1:
            self.alpha = 1.0
        else:
            self.alpha = 2.0 / (smoothing_window + 1.0)

        # Dual EMA tracks per spec
        self._dir_ema: Dict[str, float] = {}   # raw (un-normalized) direction EMA
        self._mag_ema: float = 0.0              # scalar magnitude EMA

    def _compute_output(self, context: Context) -> Optional[PolicyOutput]:
        if not self.enabled:
            return None

        instant_dir = self._get_instant_tags(context)

        # Direction EMA: blend raw vectors, base class normalizes on output
        all_tags = set(self._dir_ema.keys()) | set(instant_dir.keys())
        new_dir_ema: Dict[str, float] = {}
        for tag in all_tags:
            cur = instant_dir.get(tag, 0.0)
            prev = self._dir_ema.get(tag, 0.0)
            v = self.alpha * cur + (1.0 - self.alpha) * prev
            if v >= 1e-6:
                new_dir_ema[tag] = v
        self._dir_ema = new_dir_ema

        # Magnitude EMA: 1.0 when matched, 0.0 when not
        instant_mag = 1.0 if instant_dir else 0.0
        self._mag_ema = self.alpha * instant_mag + (1.0 - self.alpha) * self._mag_ema

        if not self._dir_ema:
            return None

        return PolicyOutput(
            direction=dict(self._dir_ema),  # base class normalizes
            salience=1.0,
            intensity=self._mag_ema,
        )

    def _get_instant_tags(self, context: Context) -> Dict[str, float]:
        window_title = context.window.title
        for keyword, tag in self.title_rules.items():
            if keyword.lower() in window_title.lower():
                return {tag: 1.0}
        tag = self.rules.get(context.window.process.lower())
        if tag:
            return {tag: 1.0}
        return {}

    def export_state(self) -> Dict[str, Any]:
        return {
            "dir_ema": self._dir_ema.copy(),
            "mag_ema": self._mag_ema,
        }

    def import_state(self, state: Dict[str, Any]) -> None:
        self._dir_ema = dict(state.get("dir_ema", {}))
        self._mag_ema = float(state.get("mag_ema", 0.0))


class TimePolicy(Policy):
    """Maps time-of-day to #dawn/#day/#sunset/#night via Hann windows.

    salience = Hann window value (peak clarity); intensity = 1.0 always.
    """

    config_key = "time"

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
            "#dawn":   ds,
            "#day":    (ds + day_span / 2) % 24,
            "#sunset": ns % 24,
            "#night":  (ns + night_span / 2) % 24,
        }

    _TAG_ORDER = ["#dawn", "#day", "#sunset", "#night"]
    _VIRTUAL_PEAKS = [0.0, 6.0, 12.0, 18.0]

    @staticmethod
    def _warp_time(hour: float, peaks: Dict[str, float]) -> float:
        """Piecewise-linear map: real hour → virtual hour in [0, 24).

        """
        real = [peaks[t] for t in TimePolicy._TAG_ORDER]
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
        sr = _time.localtime(weather.sunrise)
        ss = _time.localtime(weather.sunset)
        ds = sr.tm_hour + sr.tm_min / 60.0
        ns = ss.tm_hour + ss.tm_min / 60.0
        if abs(ds - self._day_start) > 1 / 60 or abs(ns - self._night_start) > 1 / 60:
            self._recompute_peaks(ds, ns)
            logger.debug("TimePolicy peaks updated: day_start=%.2f night_start=%.2f", ds, ns)

    def _compute_output(self, context: Context) -> Optional[PolicyOutput]:
        if not self.enabled:
            return None

        if self.auto:
            self._update_from_context(context)

        current_time = context.time
        hour = current_time.tm_hour + current_time.tm_min / 60.0
        t_virtual = self._warp_time(hour, self._peaks)

        # Dominant tag determines direction; salience = its Hann value
        best_tag = None
        best_w = 0.0
        raw: Dict[str, float] = {}
        for tag, v_peak in zip(self._TAG_ORDER, self._VIRTUAL_PEAKS):
            d = _circular_distance(t_virtual, v_peak, 24)
            w = _hann(d, self._H)
            if w > 1e-4:
                raw[tag] = w
                if w > best_w:
                    best_w = w
                    best_tag = tag

        if not raw:
            return None

        # direction = all Hann weights (base class normalizes); salience = peak Hann
        return PolicyOutput(direction=raw, salience=best_w, intensity=1.0)


class SeasonPolicy(Policy):
    """Maps day-of-year to #spring/#summer/#autumn/#winter via Hann windows."""

    config_key = "season"

    def __init__(self, config: SeasonPolicyConfig):
        super().__init__(config)
        self._peaks = {
            "#spring": config.spring_peak,
            "#summer": config.summer_peak,
            "#autumn": config.autumn_peak,
            "#winter": config.winter_peak,
        }
        self._H = 365 / len(self._peaks)

    def _compute_output(self, context: Context) -> Optional[PolicyOutput]:
        if not self.enabled:
            return None

        doy = context.time.tm_yday
        raw: Dict[str, float] = {}
        best_w = 0.0
        for tag, peak in self._peaks.items():
            d = _circular_distance(doy, peak, 365)
            w = _hann(d, self._H)
            if w > 1e-4:
                raw[tag] = w
                if w > best_w:
                    best_w = w

        if not raw:
            return None

        return PolicyOutput(direction=raw, salience=best_w, intensity=1.0)


class WeatherPolicy(Policy):
    """Maps OWM condition codes to (direction, intensity) PolicyOutput.

    direction = unit tag vector encoding weather type (#rain, #storm, etc.)
    intensity = T1-T4 severity level extracted from the raw vector norm
    salience  = 1.0 (weather IDs are unambiguous)
        1. **intensity** ``s`` = L2 norm of the output vector ∈ (0, 1].
       Represents "how much this weather overrides other signals":

         T1 ≈ 0.25  negligible   mist, haze, dust whirls
         T2 ≈ 0.50  light        drizzle, light rain/snow, sky conditions
         T3 ≈ 0.75  heavy        moderate rain, dense fog
         T4 = 1.00  extreme      very heavy rain, heavy snow, tornado

    2. **unit_direction** = tag composition (Σ component² = 1).
       Encodes "what kind of weather" without changing voting power.

       Two-tag directions use fixed angle presets:
         2:1 ratio  → (cos 27° ≈ 0.89, sin 27° ≈ 0.45)   primary dominates
         3:1 ratio  → (cos 18° ≈ 0.95, sin 18° ≈ 0.32)   strongly primary
         1:1 ratio  → (cos 45° ≈ 0.71, sin 45° ≈ 0.71)   equal mix
    """

    # Raw tag vectors: component = intensity * direction_component (pre-merged)
    _ID_TAGS: Dict[int, Dict[str, float]] = {
        # 2xx Thunderstorm
        210: {"#storm": 0.50, "#rain": 0.25},
        211: {"#storm": 0.75, "#rain": 0.50},
        212: {"#storm": 1.00, "#rain": 0.60},
        221: {"#storm": 0.90, "#rain": 0.50},
        200: {"#storm": 0.67, "#rain": 0.34},
        201: {"#storm": 0.80, "#rain": 0.40},
        202: {"#storm": 0.89, "#rain": 0.45},
        230: {"#storm": 0.62, "#rain": 0.21},
        231: {"#storm": 0.71, "#rain": 0.24},
        232: {"#storm": 0.80, "#rain": 0.36},
        # 3xx Drizzle
        300: {"#rain": 0.25},
        301: {"#rain": 0.40},
        302: {"#rain": 0.55},
        310: {"#rain": 0.30},
        311: {"#rain": 0.50},
        312: {"#rain": 0.60},
        313: {"#rain": 0.50},
        314: {"#rain": 0.65},
        321: {"#rain": 0.50},
        # 5xx Rain
        500: {"#rain": 0.40},
        501: {"#rain": 0.65},
        502: {"#rain": 0.85},
        503: {"#rain": 1.00},
        504: {"#rain": 1.00},
        511: {"#rain": 0.53, "#snow": 0.27},
        520: {"#rain": 0.45},
        521: {"#rain": 0.65},
        522: {"#rain": 0.90},
        531: {"#rain": 0.70},
        # 6xx Snow
        600: {"#snow": 0.40},
        601: {"#snow": 0.70},
        602: {"#snow": 1.00},
        611: {"#snow": 0.39, "#rain": 0.39},
        612: {"#snow": 0.32, "#rain": 0.32},
        613: {"#snow": 0.35, "#rain": 0.35},
        615: {"#rain": 0.35, "#snow": 0.35},
        616: {"#rain": 0.42, "#snow": 0.42},
        620: {"#snow": 0.40},
        621: {"#snow": 0.65},
        622: {"#snow": 1.00},
        # 7xx Atmosphere
        701: {"#fog": 0.30},
        711: {"#fog": 0.45},
        721: {"#fog": 0.25},
        731: {"#fog": 0.25},
        741: {"#fog": 0.75},
        751: {"#fog": 0.30},
        761: {"#fog": 0.40},
        762: {"#fog": 0.60},
        771: {"#storm": 0.65},
        781: {"#storm": 1.00},
        # 800 Clear / 80x Clouds
        800: {"#clear": 0.50},
        801: {"#clear": 0.47, "#cloudy": 0.16},
        802: {"#clear": 0.35, "#cloudy": 0.35},
        803: {"#cloudy": 0.47, "#clear": 0.16},
        804: {"#cloudy": 0.50},
    }

    _MAIN_FALLBACK: Dict[str, Dict[str, float]] = {
        "thunderstorm": {"#storm": 0.67, "#rain": 0.34},
        "drizzle":      {"#rain": 0.40},
        "rain":         {"#rain": 0.65},
        "snow":         {"#snow": 0.65},
        "mist":         {"#fog": 0.30},
        "smoke":        {"#fog": 0.45},
        "haze":         {"#fog": 0.25},
        "dust":         {"#fog": 0.40},
        "fog":          {"#fog": 0.75},
        "sand":         {"#fog": 0.30},
        "ash":          {"#fog": 0.55},
        "squall":       {"#storm": 0.65},
        "tornado":      {"#storm": 1.00},
        "clear":        {"#clear": 0.50},
        "clouds":       {"#cloudy": 0.50},
    }

    config_key = "weather"

    def __init__(self, config: WeatherPolicyConfig):
        super().__init__(config)

    def _compute_output(self, context: Context) -> Optional[PolicyOutput]:
        if not self.enabled:
            return None
        weather = context.weather
        if weather is None:
            return None

        raw = self._resolve_tags(weather.id, weather.main)
        if not raw:
            return None

        # Extract intensity as L2 norm of raw vector, then normalize direction
        norm = math.sqrt(sum(w * w for w in raw.values()))
        if norm < 1e-6:
            return None

        intensity = norm
        direction = {t: w / norm for t, w in raw.items()}

        return PolicyOutput(direction=direction, salience=1.0, intensity=intensity)

    @classmethod
    def _resolve_tags(cls, weather_id: int, weather_main: str) -> Optional[Dict[str, float]]:
        entry = cls._ID_TAGS.get(weather_id)
        if entry is not None:
            return dict(entry)
        return cls._MAIN_FALLBACK.get(weather_main.lower())
