import logging
import math
import time as _time
from abc import ABC, abstractmethod
from typing import ClassVar, Dict, Any, List, Union

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


def _circular_distance(a: float, b: float, period: float) -> float:
    """Shortest distance between two points on a circle of given *period*."""
    d = abs(a - b) % period
    return min(d, period - d)


def _hann(d: float, H: float) -> float:
    """Hann window: 0.5·(1 + cos(π·d/H)) for d < H, else 0.

    Properties:
    * w(0) = 1,  w(H) = 0
    * w'(H) = 0  →  C¹-smooth at the boundary (no kink)
    """
    if d >= H:
        return 0.0
    return 0.5 * (1.0 + math.cos(math.pi * d / H))


class Policy(ABC):
    # Config key matching the attribute name on PoliciesConfig.
    # Each concrete subclass must define this as a class-level string.
    config_key: ClassVar[str]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Skip abstract intermediates that don't (yet) declare config_key.
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
    def _compute_tags(self, context: Context) -> Union[Dict[str, float], List[Dict[str, float]]]:
        """Compute raw tags for the current context.

        Simple policies return a single ``Dict``.
        Policies that need semantic sub-vectors return a ``List[Dict]``
        """
        pass

    def get_tags(self, context: Context) -> List[Dict[str, float]]:
        """Public interface: always returns List[Dict[str, float]].

        Wraps ``_compute_tags`` output so callers (Matcher) always receive
        a uniform list of sub-vectors regardless of what the subclass returns.
        """
        result = self._compute_tags(context)
        if isinstance(result, dict):
            return [result]
        return result
    
    def _normalize_and_scale(self, tags: Dict[str, float]) -> Dict[str, float]:
        """
        Normalizes the tag vector to unit length, then scales by weight_scale.
        """
        if not tags:
            return {}
            
        # Calculate L2 norm
        norm = math.sqrt(sum(w * w for w in tags.values()))
        
        if norm < 1e-6:
            return {}
            
        # Normalize and scale
        return {tag: (w / norm) * self.weight_scale for tag, w in tags.items()}

    def export_state(self) -> Dict[str, Any]:
        """Export transient runtime state for hot-reload preservation.
        Default: no state. Override in stateful subclasses.
        """
        return {}

    def import_state(self, state: Dict[str, Any]) -> None:
        """Restore transient runtime state after a hot reload.
        Default: no-op. Override in stateful subclasses.
        """

class ActivityPolicy(Policy):
    config_key = "activity"

    def __init__(self, config: ActivityPolicyConfig):
        super().__init__(config)
        # Convert rules to lowercase for case-insensitive matching
        self.rules = {k.lower(): v for k, v in config.process_rules.items()}
        self.title_rules = config.title_rules

        # EMA Configuration
        smoothing_window = config.smoothing_window
        # Calculate alpha for EMA: alpha = 2 / (N + 1)
        if smoothing_window <= 1:
            self.alpha = 1.0
        else:
            self.alpha = 2.0 / (smoothing_window + 1.0)

        self.smoothed_tags: Dict[str, float] = {}

    def _compute_tags(self, context: Context) -> Dict[str, float]:
        if not self.enabled:
            return {}

        instant_tags = self._get_instant_tags(context)
        
        # Apply EMA
        self.smoothed_tags = self._apply_ema(instant_tags)
        
        # For ActivityPolicy, we do NOT use L2 normalization.
        # Because we want the vector magnitude to decay when no rule is matched.
        return {tag: w * self.weight_scale for tag, w in self.smoothed_tags.items()}

    def _get_instant_tags(self, context: Context) -> Dict[str, float]:
        process_name = context.window.process
        window_title = context.window.title
        
        # 1. Check Title Rules (Higher Priority)
        for keyword, tag in self.title_rules.items():
            if keyword.lower() in window_title.lower():
                return {tag: 1.0}

        # 2. Check Process Rules (Fallback)
        tag = self.rules.get(process_name.lower())
        if tag:
            return {tag: 1.0}
        
        return {}

    def _apply_ema(self, instant_tags: Dict[str, float]) -> Dict[str, float]:
        all_tags = set(self.smoothed_tags.keys()) | set(instant_tags.keys())
        new_smoothed_tags = {}
        
        for tag in all_tags:
            current_weight = instant_tags.get(tag, 0.0)
            previous_weight = self.smoothed_tags.get(tag, 0.0)
            
            new_weight = self.alpha * current_weight + (1.0 - self.alpha) * previous_weight
            
            if new_weight >= 0.001:
                new_smoothed_tags[tag] = new_weight
        
        return new_smoothed_tags

    def export_state(self) -> Dict[str, Any]:
        return {"smoothed_tags": self.smoothed_tags.copy()}

    def import_state(self, state: Dict[str, Any]) -> None:
        self.smoothed_tags = dict(state.get("smoothed_tags", {}))

class TimePolicy(Policy):
    """
    Maps the current time-of-day to ``#dawn``, ``#day``, ``#sunset``,
    ``#night`` tags using **raised-cosine** interpolation on a circular
    24-hour axis.

    Four anchor points (peaks) are placed evenly:
        dawn_peak   = day_start
        day_peak    = midpoint(day_start → night_start)
        sunset_peak = night_start
        night_peak  = midpoint(night_start → next day_start)  (wraps at 24)

    Each tag uses a **Hann window**:

        w(d) = 0.5 * (1 + cos(π · d / H))  for d ≤ H
               0                             for d > H

    where *d* is computed in **virtual time** after a piecewise-linear
    warp that maps the four real peaks to 0 / 6 / 12 / 18 h, and *H* = 6 h
    is fixed in that virtual domain.  The warp stretches or compresses each
    real inter-peak arc to exactly 6 virtual hours, giving asymmetric windows
    in real time that always reach exactly the adjacent peak — regardless of
    how unequal the actual sunrise/sunset split makes them.  Properties in
    virtual time (invariant under the warp):
    * w(0) = 1 at peak, w(6) = 0 at the adjacent peak
    * First derivative w'(6) = 0  →  smooth, kink-free transitions
    * Adjacent windows sum to a near-constant, so the L2-normalised
      direction vector changes smoothly with time.
    """

    config_key = "time"

    def __init__(self, config: TimePolicyConfig):
        super().__init__(config)
        self._day_start: float = config.day_start
        self._night_start: float = config.night_start
        self.auto: bool = config.auto

        self._peaks: Dict[str, float] = {}
        self._H: float = 6.0  # constant in virtual time; warp handles real-time distortion
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

    # Canonical tag order (matches _compute_peaks insertion order)
    _TAG_ORDER = ["#dawn", "#day", "#sunset", "#night"]
    # Corresponding peak positions in virtual (uniformly-spaced) time
    _VIRTUAL_PEAKS = [0.0, 6.0, 12.0, 18.0]

    @staticmethod
    def _warp_time(hour: float, peaks: Dict[str, float]) -> float:
        """Piecewise-linear map: real hour → virtual hour in [0, 24).

        The 24-hour circle is divided into four arcs by the actual peak
        positions.  Each arc is linearly stretched/compressed to fill exactly
        6 virtual hours, mapping real peaks → virtual 0 / 6 / 12 / 18.
        After this warp the Hann kernel with H = 6 spans exactly one arc in
        virtual time, equivalently producing an asymmetric window in real time
        whose half-width equals the actual inter-peak arc length on each side.
        """
        real = [peaks[t] for t in TimePolicy._TAG_ORDER]
        n = len(real)
        for i in range(n):
            r_a = real[i]
            r_b = real[(i + 1) % n]
            seg = (r_b - r_a) % 24   # arc length of this real segment
            pos = (hour - r_a) % 24  # forward distance from r_a to hour
            if pos < seg:
                v_a = TimePolicy._VIRTUAL_PEAKS[i]
                return (v_a + pos / seg * 6.0) % 24
        # hour is exactly on the last peak boundary → start of next virtual arc
        return 0.0

    def _recompute_peaks(self, ds: float, ns: float) -> None:
        self._day_start = ds
        self._night_start = ns
        self._peaks = self._compute_peaks(ds, ns)

    def _update_from_context(self, context: Context) -> None:
        """Dynamically adjust peaks from OWM sunrise/sunset if available."""
        weather = context.weather
        if weather is None or not weather.sunrise or not weather.sunset:
            return

        sunrise_ts = weather.sunrise
        sunset_ts = weather.sunset

        # Convert UTC timestamps to local hours
        sr = _time.localtime(sunrise_ts)
        ss = _time.localtime(sunset_ts)
        ds = sr.tm_hour + sr.tm_min / 60.0
        ns = ss.tm_hour + ss.tm_min / 60.0

        # Only recompute if values actually changed (±1 min tolerance)
        if (abs(ds - self._day_start) > 1 / 60
                or abs(ns - self._night_start) > 1 / 60):
            self._recompute_peaks(ds, ns)
            logger.debug(
                "TimePolicy peaks updated: day_start=%.2f night_start=%.2f",
                ds, ns,
            )

    def _compute_tags(self, context: Context) -> Dict[str, float]:
        if not self.enabled:
            return {}

        if self.auto:
            self._update_from_context(context)

        current_time = context.time
        hour = current_time.tm_hour + current_time.tm_min / 60.0

        t_virtual = self._warp_time(hour, self._peaks)
        tags: Dict[str, float] = {}
        for tag, v_peak in zip(self._TAG_ORDER, self._VIRTUAL_PEAKS):
            d = _circular_distance(t_virtual, v_peak, 24)
            w = _hann(d, self._H)   # H = 6.0 always in virtual time
            if w > 1e-4:
                tags[tag] = w

        return self._normalize_and_scale(tags)


class SeasonPolicy(Policy):
    """
    Maps the current day-of-year to ``#spring``, ``#summer``, ``#autumn``,
    ``#winter`` tags using **raised-cosine** interpolation on a circular
    365-day axis.

    Peak days default to the meteorological mid-season points (Northern
    Hemisphere) and can be overridden via config:
        spring_peak, summer_peak, autumn_peak, winter_peak  (day-of-year)

    Same Hann-window interpolation as TimePolicy, on a 365-day circle.
    """

    config_key = "season"

    def __init__(self, config: SeasonPolicyConfig):
        super().__init__(config)
        self._peaks = {
            "#spring": config.spring_peak,
            "#summer": config.summer_peak,
            "#autumn": config.autumn_peak,
            "#winter": config.winter_peak,
        }
        # H = full inter-peak distance ≈ 91.25 days for 4 seasons
        self._H = 365 / len(self._peaks)

    def _compute_tags(self, context: Context) -> Dict[str, float]:
        if not self.enabled:
            return {}

        current_time = context.time
        doy = current_time.tm_yday

        tags: Dict[str, float] = {}
        for tag, peak in self._peaks.items():
            d = _circular_distance(doy, peak, 365)
            w = _hann(d, self._H)
            if w > 1e-4:
                tags[tag] = w

        return self._normalize_and_scale(tags)


class WeatherPolicy(Policy):
    """
    Maps OpenWeatherMap condition codes to intensity-weighted tag vectors.

    ── Design principle: output = intensity × unit_direction ──────────────

    Each entry in ``_ID_TAGS`` encodes two orthogonal quantities:

    1. **intensity** ``s`` = L2 norm of the output vector ∈ (0, 1].
       Represents "how much this weather overrides other signals":

         T1 ≈ 0.25  negligible   mist, haze, dust whirls
         T2 ≈ 0.50  light        drizzle, light rain/snow, sky conditions
         T3 ≈ 0.75  heavy        moderate rain, dense fog
         T4 = 1.00  extreme      very heavy rain, heavy snow, tornado

       Sky conditions (clear / cloudy) are capped at **T2** because they
       represent a stable ambient state, not an event.  Precipitation and
       storms use the full T1–T4 range.

    2. **unit_direction** = tag composition (Σ component² = 1).
       Encodes "what kind of weather" without changing voting power.

       Two-tag directions use fixed angle presets:
         2:1 ratio  → (cos 27° ≈ 0.89, sin 27° ≈ 0.45)   primary dominates
         3:1 ratio  → (cos 18° ≈ 0.95, sin 18° ≈ 0.32)   strongly primary
         1:1 ratio  → (cos 45° ≈ 0.71, sin 45° ≈ 0.71)   equal mix

    ── Normalisation policy ──────────────────────────────────────────────

    Unlike Time/Season, this policy does **NOT** L2-normalise its output.
    The raw tag vector (scaled by ``weight_scale``) is passed directly to
    the Arbiter sum.  Consequences:

    * Mild weather (T1-T2) contributes a small norm → yields to Activity
      and Time signals.
    * Extreme weather (T4) contributes a large norm → dominates direction.
    * ``weight_scale`` in config is the influence *ceiling* (at s = 1.00).
      With the default weight_scale = 1.5, extreme weather contributes
      norm 1.5, comparable to a fully-matched ActivityPolicy (ws = 1.2).
    """

    # ── Weather-ID → tag mapping ─────────────────────────────────────────
    # Values follow:  component = s × direction_component
    # Single-tag:  value = s
    # Two-tag 2:1: primary = s × 0.89,  secondary = s × 0.45
    # Two-tag 3:1: primary = s × 0.95,  secondary = s × 0.32
    # Two-tag 1:1: each   = s × 0.71
    _ID_TAGS: Dict[int, Dict[str, float] | List[Dict[str, float]]] = {
        # 2xx Thunderstorm ────────────────────────────────────────────────
        # Pure storm: T2→T4 by severity; #rain added as fallback (dry lightning
        # is meteorologically rare; real thunderstorms almost always have rain)
        210: {"#storm": 0.50, "#rain": 0.25},   # s≈0.56 light thunderstorm
        211: {"#storm": 0.75, "#rain": 0.50},   # s≈0.90 thunderstorm
        212: {"#storm": 1.00, "#rain": 0.60},   # s≈1.17 heavy thunderstorm
        221: {"#storm": 0.90, "#rain": 0.50},   # s≈1.03 ragged thunderstorm
        # Storm + rain: s = T3 → T4, direction 2:1 (storm primary)
        200: {"#storm": 0.67, "#rain": 0.34},    # s=0.75 ts+light rain
        201: {"#storm": 0.80, "#rain": 0.40},    # s=0.89 ts+rain
        202: {"#storm": 0.89, "#rain": 0.45},    # s=1.00 ts+heavy rain
        # Storm + drizzle: direction 3:1 (storm primary)
        230: {"#storm": 0.62, "#rain": 0.21},    # s=0.65 ts+light drizzle
        231: {"#storm": 0.71, "#rain": 0.24},    # s=0.75 ts+drizzle
        232: {"#storm": 0.80, "#rain": 0.36},    # s=0.89 ts+heavy drizzle
        # 3xx Drizzle ─────────────────────────────────────────────────────
        300: {"#rain": 0.25},                    # s=T1   light drizzle
        301: {"#rain": 0.40},                    # s=T2   drizzle
        302: {"#rain": 0.55},                    # s=T2+  heavy drizzle
        310: {"#rain": 0.30},                    # s=T1+  light drizzle rain
        311: {"#rain": 0.50},                    # s=T2   drizzle rain
        312: {"#rain": 0.60},                    # s=T2+  heavy drizzle rain
        313: {"#rain": 0.50},                    # s=T2   shower rain+drizzle
        314: {"#rain": 0.65},                    # s=T2+  heavy shower+drizzle
        321: {"#rain": 0.50},                    # s=T2   shower drizzle
        # 5xx Rain ────────────────────────────────────────────────────────
        500: {"#rain": 0.40},                    # s=T2   light rain
        501: {"#rain": 0.65},                    # s=T2+  moderate rain
        502: {"#rain": 0.85},                    # s=T3+  heavy intensity rain
        503: {"#rain": 1.00},                    # s=T4   very heavy rain
        504: {"#rain": 1.00},                    # s=T4   extreme rain
        511: {"#rain": 0.53, "#snow": 0.27},     # s=0.59 freezing rain, 2:1
        520: {"#rain": 0.45},                    # s=T2   light shower rain
        521: {"#rain": 0.65},                    # s=T2+  shower rain
        522: {"#rain": 0.90},                    # s=T3+  heavy shower rain
        531: {"#rain": 0.70},                    # s=T3   ragged shower rain
        # 6xx Snow ────────────────────────────────────────────────────────
        600: {"#snow": 0.40},                    # s=T2   light snow
        601: {"#snow": 0.70},                    # s=T3   snow
        602: {"#snow": 1.00},                    # s=T4   heavy snow
        611: {"#snow": 0.39, "#rain": 0.39},     # s=0.55 sleet, 1:1
        612: {"#snow": 0.32, "#rain": 0.32},     # s=0.45 light shower sleet, 1:1
        613: {"#snow": 0.35, "#rain": 0.35},     # s=0.50 shower sleet, 1:1
        615: {"#rain": 0.35, "#snow": 0.35},     # s=0.50 light rain and snow, 1:1
        616: {"#rain": 0.42, "#snow": 0.42},     # s=0.60 rain and snow, 1:1
        620: {"#snow": 0.40},                    # s=T2   light shower snow
        621: {"#snow": 0.65},                    # s=T2+  shower snow
        622: {"#snow": 1.00},                    # s=T4   heavy shower snow
        # 7xx Atmosphere ──────────────────────────────────────────────────
        701: {"#fog": 0.30},                     # s=T1+  mist
        711: {"#fog": 0.45},                     # s=T2   smoke
        721: {"#fog": 0.25},                     # s=T1   haze
        731: {"#fog": 0.25},                     # s=T1   dust whirls
        741: {"#fog": 0.75},                     # s=T3   fog
        751: {"#fog": 0.30},                     # s=T1+  sand
        761: {"#fog": 0.40},                     # s=T2   dust
        762: {"#fog": 0.60},                     # s=T2+  volcanic ash
        771: {"#storm": 0.65},                   # s=T2+  squall
        781: {"#storm": 1.00},                   # s=T4   tornado
        # 800 Clear ───────────────────────────────────────────────────────
        # Sky conditions are ambient states, capped at T2 to avoid
        # overwhelming Activity / Time signals.
        800: {"#clear": 0.50},                   # s=T2   clear sky
        # 80x Clouds (gradual clear→cloudy) ──────────────────────────────
        # 801-802 centred at T2=0.50; 803 at T2; 804 at T2.
        # Direction shifts from clear-primary to cloudy-primary.
        801: [{"#clear": 0.47}, {"#cloudy": 0.16}],  # s=0.50, independent: clear and cloudy are semantic opposites
        802: [{"#clear": 0.35}, {"#cloudy": 0.35}],  # s=0.50, independent: equal mix, no cross-fallback
        803: [{"#cloudy": 0.47}, {"#clear": 0.16}],  # s=0.50, independent: cloudy primary
        804: {"#cloudy": 0.50},                      # s=T2   overcast
    }
    # Normalize to uniform List[Dict] at class load time so runtime methods
    # never need to branch on the entry type.
    _ID_TAGS = {k: (v if isinstance(v, list) else [v]) for k, v in _ID_TAGS.items()}
    _ID_TAGS: Dict[int, List[Dict[str, float]]]

    # Coarse fallback when id is missing / unrecognised ───────────────────
    _MAIN_FALLBACK: Dict[str, List[Dict[str, float]]] = {
        "thunderstorm": [{"#storm": 0.67, "#rain": 0.34}],  # T3 × 2:1
        "drizzle":      [{"#rain": 0.40}],                   # T2
        "rain":         [{"#rain": 0.65}],                   # T2+
        "snow":         [{"#snow": 0.65}],                   # T2+
        "mist":         [{"#fog": 0.30}],                    # T1+
        "smoke":        [{"#fog": 0.45}],                    # T2
        "haze":         [{"#fog": 0.25}],                    # T1
        "dust":         [{"#fog": 0.40}],                    # T2
        "fog":          [{"#fog": 0.75}],                    # T3
        "sand":         [{"#fog": 0.30}],                    # T1+
        "ash":          [{"#fog": 0.55}],                    # T2+
        "squall":       [{"#storm": 0.65}],                  # T2+
        "tornado":      [{"#storm": 1.00}],                  # T4
        "clear":        [{"#clear": 0.50}],                  # T2
        "clouds":       [{"#cloudy": 0.50}],                 # T2
    }

    config_key = "weather"

    def __init__(self, config: WeatherPolicyConfig):
        super().__init__(config)

    def _compute_tags(self, context: Context) -> List[Dict[str, float]]:
        if not self.enabled:
            return []

        weather = context.weather
        if weather is None:
            return []

        weather_id = weather.id
        weather_main = weather.main
        resolved = self._resolve_tags(weather_id, weather_main)

        # Apply weight_scale to each sub-vector independently.
        # Preserve intensity: do NOT normalise.
        return [{tag: w * self.weight_scale for tag, w in sub.items()} for sub in resolved]

    @classmethod
    def _resolve_tags(cls, weather_id: int, weather_main: str) -> List[Dict[str, float]]:
        """Return sub-vectors for a given weather condition, preferring *id*.

        Always returns ``List[Dict]``; entries are independent energy sources
        that Matcher projects and compensates separately.
        """
        entry = cls._ID_TAGS.get(weather_id)
        if entry is not None:
            return [dict(sub) for sub in entry]
        fallback = cls._MAIN_FALLBACK.get(weather_main.lower())
        return [dict(sub) for sub in fallback] if fallback else []
