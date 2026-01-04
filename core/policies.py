import time
import requests
import logging
import math
from abc import ABC, abstractmethod
from typing import Dict, Any

logger = logging.getLogger("WEScheduler.Policy")

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
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.night_start = config.get("night_start", 20)
        self.day_start = config.get("day_start", 8)

    def get_tags(self, context: Dict[str, Any]) -> Dict[str, float]:
        if not self.enabled:
            return {}

        current_time = context.get("time")
        if not current_time:
            return {}

        hour = current_time.tm_hour + current_time.tm_min / 60.0
        tags = {}

        # Define anchors (peaks)
        # Day peak: Noon (12:00) or midpoint of day
        # Night peak: Midnight (0:00) or midpoint of night
        # We use a simple distance-based interpolation
        
        # Calculate distance to "Day Center" (approx (day_start + night_start) / 2)
        day_center = (self.day_start + self.night_start) / 2
        
        # Calculate distance to "Night Center" (approx (night_start + 24 + day_start) / 2 % 24)
        # Simplified: Just use linear interpolation between day_start and night_start
        
        # Transition periods (e.g., 1 hour duration)
        transition_duration = 2.0 
        
        # Calculate weights
        day_weight = 0.0
        night_weight = 0.0
        sunset_weight = 0.0
        dawn_weight = 0.0
        
        # Dawn: around day_start
        if abs(hour - self.day_start) < transition_duration:
            dawn_weight = 1.0 - abs(hour - self.day_start) / transition_duration
            
        # Sunset: around night_start
        if abs(hour - self.night_start) < transition_duration:
            sunset_weight = 1.0 - abs(hour - self.night_start) / transition_duration
            
        # Day: between day_start and night_start
        if self.day_start <= hour < self.night_start:
            # Peak at center, fade at edges
            dist_to_edge = min(hour - self.day_start, self.night_start - hour)
            day_weight = min(1.0, dist_to_edge / transition_duration)
            
        # Night: before day_start or after night_start
        else:
            if hour < self.day_start:
                dist_to_edge = self.day_start - hour
            else:
                dist_to_edge = hour - self.night_start
            night_weight = min(1.0, dist_to_edge / transition_duration)

        if day_weight > 0: tags["#day"] = day_weight
        if night_weight > 0: tags["#night"] = night_weight
        if dawn_weight > 0: tags["#dawn"] = dawn_weight
        if sunset_weight > 0: tags["#sunset"] = sunset_weight
        
        return self._normalize_and_scale(tags)

class SeasonPolicy(Policy):
    def get_tags(self, context: Dict[str, Any]) -> Dict[str, float]:
        if not self.enabled:
            return {}

        current_time = context.get("time")
        if not current_time:
            return {}

        month = current_time.tm_mon
        
        # Simple season mapping (Northern Hemisphere)
        if month in [12, 1, 2]:
            tag = "#winter"
        elif month in [3, 4, 5]:
            tag = "#spring"
        elif month in [6, 7, 8]:
            tag = "#summer"
        else:
            tag = "#autumn"
            
        return self._normalize_and_scale({tag: 1.0})

class WeatherPolicy(Policy):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.lat = config.get("lat", "")
        self.lon = config.get("lon", "")
        self.interval = config.get("interval", 600) # Default 10 minutes
        
        self.last_fetch_time = 0
        self.cached_tags = {}

    def get_tags(self, context: Dict[str, Any]) -> Dict[str, float]:
        if not self.enabled or not self.api_key:
            return {}

        current_timestamp = time.time()
        
        # Check if we need to refresh data
        if current_timestamp - self.last_fetch_time > self.interval:
            self._fetch_weather()
            self.last_fetch_time = current_timestamp
            
        return self._normalize_and_scale(self.cached_tags)

    def _fetch_weather(self):
        if not self.api_key:
            return
            
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "lat": self.lat,
            "lon": self.lon,
            "appid": self.api_key,
            "units": "metric"
        }
        
        try:
            response = requests.get(url, params=params, timeout=10, proxies={"http": None, "https": None})
            
            if response.status_code == 200:
                data = response.json()
                weather_main = data.get("weather", [{}])[0].get("main", "").lower()
                
                # Map weather to tags
                tags = {}
                if weather_main in ["thunderstorm", "drizzle", "rain"]:
                    tags["#rain"] = 1.0
                elif weather_main == "snow":
                    tags["#snow"] = 1.0
                elif weather_main == "clear":
                    tags["#clear"] = 1.0
                elif weather_main == "clouds":
                    tags["#cloudy"] = 1.0
                
                self.cached_tags = tags
                logger.info(f"Weather updated: {weather_main} -> {tags}")
            else:
                logger.error(f"Weather API Error: {response.status_code}")
        except Exception as e:
            logger.error(f"Weather fetch failed: {e}")
