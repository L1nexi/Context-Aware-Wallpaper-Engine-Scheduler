import time
import requests
import logging
import math
from abc import ABC, abstractmethod
from typing import Dict, Any

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
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get("enabled", True)
        self.weight_scale = config.get("weight_scale", 1.0)

    @abstractmethod
    def get_tags(self, context: Dict[str, Any]) -> Dict[str, float]:
        """
        Returns a dictionary of tags and their weights based on the context.
        Example: {"#work": 0.8, "#night": 0.5}
        """
        pass
    
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

class ActivityPolicy(Policy):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        # Convert rules to lowercase for case-insensitive matching
        self.rules = {k.lower(): v for k, v in config.get("rules", {}).items()}
        self.title_rules = config.get("title_rules", {})
        
        # EMA Configuration
        smoothing_window = config.get("smoothing_window", 60)
        # Calculate alpha for EMA: alpha = 2 / (N + 1)
        if smoothing_window <= 1:
            self.alpha = 1.0
        else:
            self.alpha = 2.0 / (smoothing_window + 1.0)
            
        self.smoothed_tags: Dict[str, float] = {}

    def get_tags(self, context: Dict[str, Any]) -> Dict[str, float]:
        if not self.enabled:
            return {}

        instant_tags = self._get_instant_tags(context)
        
        # Apply EMA
        self.smoothed_tags = self._apply_ema(instant_tags)
        
        # For ActivityPolicy, we do NOT use L2 normalization.
        # Because we want the vector magnitude to decay when no rule is matched.
        return {tag: w * self.weight_scale for tag, w in self.smoothed_tags.items()}

    def _get_instant_tags(self, context: Dict[str, Any]) -> Dict[str, float]:
        window_info = context.get("window", {})
        process_name = window_info.get("process", "")
        window_title = window_info.get("title", "")
        
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

    where *d* is the shortest circular distance (in hours) to the tag's
    peak and *H* is the full inter-peak distance (= 24 / n_tags = 6 h
    for 4 tags).  Properties:
    * w(0) = 1 at peak, w(H) = 0 at the adjacent peak
    * First derivative w'(H) = 0  →  smooth, kink-free transitions
    * Adjacent windows sum to a near-constant, so the L2-normalised
      direction vector changes smoothly with time.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.day_start = config.get("day_start", 8)
        self.night_start = config.get("night_start", 20)

        # Pre-compute four equidistant anchor peaks on the 24 h circle
        ds = self.day_start
        ns = self.night_start
        day_span = (ns - ds) % 24          # hours from dawn → sunset
        night_span = 24 - day_span         # hours from sunset → next dawn

        self._peaks = {
            "#dawn":   ds,
            "#day":    (ds + day_span / 2) % 24,
            "#sunset": ns % 24,
            "#night":  (ns + night_span / 2) % 24,
        }
        # H = full inter-peak distance (not half of it)
        self._H = 24 / len(self._peaks)  # = 6.0 h for 4 tags

    def get_tags(self, context: Dict[str, Any]) -> Dict[str, float]:
        if not self.enabled:
            return {}

        current_time = context.get("time")
        if not current_time:
            return {}

        hour = current_time.tm_hour + current_time.tm_min / 60.0

        tags: Dict[str, float] = {}
        for tag, peak in self._peaks.items():
            d = _circular_distance(hour, peak, 24)
            w = _hann(d, self._H)
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

    # Default peaks: roughly the middle of each meteorological season
    _DEFAULT_PEAKS = {
        "#spring": 80,   # ~Mar 21
        "#summer": 172,  # ~Jun 21
        "#autumn": 265,  # ~Sep 22
        "#winter": 355,  # ~Dec 21
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._peaks = {
            tag: config.get(f"{tag[1:]}_peak", default)
            for tag, default in self._DEFAULT_PEAKS.items()
        }
        # H = full inter-peak distance ≈ 91.25 days for 4 seasons
        self._H = 365 / len(self._peaks)

    def get_tags(self, context: Dict[str, Any]) -> Dict[str, float]:
        if not self.enabled:
            return {}

        current_time = context.get("time")
        if not current_time:
            return {}

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

         T1 ≈ 0.25  negligible   mist, haze, dust whirls, few clouds
         T2 ≈ 0.50  light        drizzle, light rain/snow, scattered clouds
         T3 ≈ 0.75  heavy        moderate rain, dense fog, broken clouds
         T4 = 1.00  extreme      very heavy rain, heavy snow, tornado

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
    _ID_TAGS: Dict[int, Dict[str, float]] = {
        # 2xx Thunderstorm ────────────────────────────────────────────────
        # Pure storm: T2→T4 by severity
        210: {"#storm": 0.50},                   # s=T2   light thunderstorm
        211: {"#storm": 0.75},                   # s=T3   thunderstorm
        212: {"#storm": 1.00},                   # s=T4   heavy thunderstorm
        221: {"#storm": 0.90},                   # s=T3.6 ragged thunderstorm
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
        800: {"#clear": 1.00},                   # s=T4   clear sky
        # 80x Clouds (gradual clear→cloudy) ──────────────────────────────
        # 801-802 centred at T2=0.50; 803-804 at T3-T4.
        # Direction shifts from clear-primary to cloudy-primary.
        801: {"#clear": 0.47, "#cloudy": 0.16},  # s=0.50, 3:1 clear:cloudy
        802: {"#clear": 0.35, "#cloudy": 0.35},  # s=0.50, 1:1 equal
        803: {"#cloudy": 0.71, "#clear": 0.24},  # s=0.75, 3:1 cloudy:clear
        804: {"#cloudy": 1.00},                  # s=T4   overcast
    }

    # Coarse fallback when id is missing / unrecognised ───────────────────
    _MAIN_FALLBACK: Dict[str, Dict[str, float]] = {
        "thunderstorm": {"#storm": 0.67, "#rain": 0.34},  # T3 × 2:1
        "drizzle":      {"#rain": 0.40},                   # T2
        "rain":         {"#rain": 0.65},                   # T2+
        "snow":         {"#snow": 0.65},                   # T2+
        "mist":         {"#fog": 0.30},                    # T1+
        "smoke":        {"#fog": 0.45},                    # T2
        "haze":         {"#fog": 0.25},                    # T1
        "dust":         {"#fog": 0.40},                    # T2
        "fog":          {"#fog": 0.75},                    # T3
        "sand":         {"#fog": 0.30},                    # T1+
        "ash":          {"#fog": 0.55},                    # T2+
        "squall":       {"#storm": 0.65},                  # T2+
        "tornado":      {"#storm": 1.00},                  # T4
        "clear":        {"#clear": 1.00},                  # T4
        "clouds":       {"#cloudy": 0.65},                 # T2+
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.lat = config.get("lat", "")
        self.lon = config.get("lon", "")
        self.interval = config.get("interval", 600)          # seconds
        self.timeout  = config.get("request_timeout", 10)    # HTTP timeout (seconds)

        self.last_fetch_time = 0.0
        self.cached_tags: Dict[str, float] = {}

    def get_tags(self, context: Dict[str, Any]) -> Dict[str, float]:
        if not self.enabled or not self.api_key:
            return {}

        if time.time() - self.last_fetch_time > self.interval:
            self._fetch_weather()
            self.last_fetch_time = time.time()

        # Preserve intensity: do NOT normalise.
        # effective norm = s × weight_scale  (ceiling at s=1.00).
        return {tag: w * self.weight_scale for tag, w in self.cached_tags.items()}

    # ── ID → tags resolution ──

    @classmethod
    def _resolve_tags(cls, weather_id: int, weather_main: str) -> Dict[str, float]:
        """Return tag dict for a given weather condition, preferring *id*."""
        tags = cls._ID_TAGS.get(weather_id)
        if tags is not None:
            return dict(tags)
        return dict(cls._MAIN_FALLBACK.get(weather_main.lower(), {}))

    # ── API call ──

    def _fetch_weather(self):
        if not self.api_key:
            return

        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "lat": self.lat,
            "lon": self.lon,
            "appid": self.api_key,
            "units": "metric",
        }

        try:
            response = requests.get(
                url, params=params, timeout=self.timeout,
                proxies={"http": None, "https": None},
            )

            if response.ok:
                data = response.json()
                first = (data.get("weather") or [{}])[0]
                weather_id = first.get("id", 0)
                weather_main = first.get("main", "")

                self.cached_tags = self._resolve_tags(weather_id, weather_main)
                logger.info(f"Weather updated: id={weather_id} main={weather_main} -> {self.cached_tags}")
            else:
                logger.warning(f"Weather API error: {response.status_code}")
        except Exception as e:
            logger.warning(f"Weather fetch failed: {e}")
