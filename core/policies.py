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
            if d >= self._H:
                continue
            w = 0.5 * (1.0 + math.cos(math.pi * d / self._H))
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
            if d >= self._H:
                continue
            w = 0.5 * (1.0 + math.cos(math.pi * d / self._H))
            if w > 1e-4:
                tags[tag] = w

        return self._normalize_and_scale(tags)


class WeatherPolicy(Policy):
    """
    Maps OpenWeatherMap ``weather.id`` (condition code 200-804) to fine-
    grained, multi-tag vectors with intensity weights.

    Falls back to the coarse ``weather.main`` string when the ``id``
    field is missing or unrecognised.

    Recognised tags: ``#rain``, ``#snow``, ``#storm``, ``#fog``,
    ``#clear``, ``#cloudy``.
    """

    # ── Weather-ID → tag mapping (OpenWeatherMap condition codes) ──
    _ID_TAGS: Dict[int, Dict[str, float]] = {
        # 2xx Thunderstorm
        200: {"#storm": 0.7, "#rain": 0.4},   # thunderstorm + light rain
        201: {"#storm": 0.8, "#rain": 0.6},   # thunderstorm + rain
        202: {"#storm": 1.0, "#rain": 0.8},   # thunderstorm + heavy rain
        210: {"#storm": 0.6},                  # light thunderstorm
        211: {"#storm": 0.7},                  # thunderstorm
        212: {"#storm": 1.0},                  # heavy thunderstorm
        221: {"#storm": 0.9},                  # ragged thunderstorm
        230: {"#storm": 0.7, "#rain": 0.3},   # thunderstorm + light drizzle
        231: {"#storm": 0.8, "#rain": 0.4},   # thunderstorm + drizzle
        232: {"#storm": 0.9, "#rain": 0.6},   # thunderstorm + heavy drizzle
        # 3xx Drizzle
        300: {"#rain": 0.3},                   # light drizzle
        301: {"#rain": 0.4},                   # drizzle
        302: {"#rain": 0.6},                   # heavy drizzle
        310: {"#rain": 0.3},                   # light drizzle rain
        311: {"#rain": 0.4},                   # drizzle rain
        312: {"#rain": 0.6},                   # heavy drizzle rain
        313: {"#rain": 0.5},                   # shower rain + drizzle
        314: {"#rain": 0.7},                   # heavy shower rain + drizzle
        321: {"#rain": 0.5},                   # shower drizzle
        # 5xx Rain
        500: {"#rain": 0.4},                   # light rain
        501: {"#rain": 0.6},                   # moderate rain
        502: {"#rain": 0.9},                   # heavy intensity rain
        503: {"#rain": 1.0},                   # very heavy rain
        504: {"#rain": 1.0},                   # extreme rain
        511: {"#rain": 0.5, "#snow": 0.3},     # freezing rain
        520: {"#rain": 0.5},                   # light shower rain
        521: {"#rain": 0.7},                   # shower rain
        522: {"#rain": 1.0},                   # heavy shower rain
        531: {"#rain": 0.8},                   # ragged shower rain
        # 6xx Snow
        600: {"#snow": 0.5},                   # light snow
        601: {"#snow": 0.8},                   # snow
        602: {"#snow": 1.0},                   # heavy snow
        611: {"#snow": 0.4, "#rain": 0.3},     # sleet
        612: {"#snow": 0.5, "#rain": 0.3},     # light shower sleet
        613: {"#snow": 0.5, "#rain": 0.3},     # shower sleet
        615: {"#snow": 0.4, "#rain": 0.3},     # light rain and snow
        616: {"#snow": 0.5, "#rain": 0.4},     # rain and snow
        620: {"#snow": 0.4},                   # light shower snow
        621: {"#snow": 0.7},                   # shower snow
        622: {"#snow": 1.0},                   # heavy shower snow
        # 7xx Atmosphere
        701: {"#fog": 0.6},                    # mist
        711: {"#fog": 0.5},                    # smoke
        721: {"#fog": 0.4},                    # haze
        731: {"#fog": 0.3},                    # dust whirls
        741: {"#fog": 0.8},                    # fog
        751: {"#fog": 0.3},                    # sand
        761: {"#fog": 0.4},                    # dust
        762: {"#fog": 0.6},                    # volcanic ash
        771: {"#storm": 0.6},                  # squall
        781: {"#storm": 1.0},                  # tornado
        # 800 Clear
        800: {"#clear": 1.0},                  # clear sky
        # 80x Clouds
        801: {"#clear": 0.6, "#cloudy": 0.3},  # few clouds (11-25%)
        802: {"#cloudy": 0.5, "#clear": 0.3},  # scattered clouds (25-50%)
        803: {"#cloudy": 0.8},                 # broken clouds (51-84%)
        804: {"#cloudy": 1.0},                 # overcast (85-100%)
    }

    # Coarse fallback when id is missing / unrecognised
    _MAIN_FALLBACK: Dict[str, Dict[str, float]] = {
        "thunderstorm": {"#storm": 0.8, "#rain": 0.5},
        "drizzle":      {"#rain": 0.4},
        "rain":         {"#rain": 0.7},
        "snow":         {"#snow": 0.7},
        "mist":         {"#fog": 0.5},
        "smoke":        {"#fog": 0.4},
        "haze":         {"#fog": 0.3},
        "dust":         {"#fog": 0.3},
        "fog":          {"#fog": 0.7},
        "sand":         {"#fog": 0.3},
        "ash":          {"#fog": 0.5},
        "squall":       {"#storm": 0.6},
        "tornado":      {"#storm": 1.0},
        "clear":        {"#clear": 1.0},
        "clouds":       {"#cloudy": 0.7},
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.lat = config.get("lat", "")
        self.lon = config.get("lon", "")
        self.interval = config.get("interval", 600)  # seconds

        self.last_fetch_time = 0.0
        self.cached_tags: Dict[str, float] = {}

    def get_tags(self, context: Dict[str, Any]) -> Dict[str, float]:
        if not self.enabled or not self.api_key:
            return {}

        current_timestamp = time.time()

        if current_timestamp - self.last_fetch_time > self.interval:
            self._fetch_weather()
            self.last_fetch_time = current_timestamp

        return self._normalize_and_scale(self.cached_tags)

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
                url, params=params, timeout=10,
                proxies={"http": None, "https": None},
            )

            if response.status_code == 200:
                data = response.json()
                first = (data.get("weather") or [{}])[0]
                weather_id = first.get("id", 0)
                weather_main = first.get("main", "")

                self.cached_tags = self._resolve_tags(weather_id, weather_main)
                logger.info(
                    "Weather updated: id=%s main=%s -> %s",
                    weather_id, weather_main, self.cached_tags,
                )
            else:
                logger.warning("Weather API error: %s", response.status_code)
        except Exception as e:
            logger.warning("Weather fetch failed: %s", e)
