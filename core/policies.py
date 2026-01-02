import time
import requests
import logging
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

class ActivityPolicy(Policy):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.rules = config.get("rules", {})
        self.title_rules = config.get("title_rules", {})

    def get_tags(self, context: Dict[str, Any]) -> Dict[str, float]:
        if not self.enabled:
            return {}

        window_info = context.get("window", {})
        process_name = window_info.get("process", "")
        window_title = window_info.get("title", "")
        
        # 1. Check Title Rules (Higher Priority)
        # Iterate through all title keywords. If a keyword is found in the title, use that tag.
        # This allows overriding the process-based rule.
        for keyword, tag in self.title_rules.items():
            if keyword.lower() in window_title.lower():
                return {tag: 1.0 * self.weight_scale}

        # 2. Check Process Rules (Fallback)
        # Simple exact match for now, could be regex later
        tag = self.rules.get(process_name)
        
        if tag:
            return {tag: 1.0 * self.weight_scale}
        
        return {}

class TimePolicy(Policy):
    def get_tags(self, context: Dict[str, Any]) -> Dict[str, float]:
        if not self.enabled:
            return {}

        # context["time"] is a struct_time
        current_time = context.get("time")
        if not current_time:
            return {}

        hour = current_time.tm_hour
        tags = {}

        # Simple logic: Night is 22:00 - 06:00
        if hour >= 22 or hour < 6:
            tags["#night"] = 1.0 * self.weight_scale
        
        # Can add more: #morning, #afternoon, etc.
        
        return tags

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
            
        return {tag: 1.0 * self.weight_scale}

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
            
        return self.cached_tags

    def _fetch_weather(self):
        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?lat={self.lat}&lon={self.lon}&appid={self.api_key}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                weather_main = data.get("weather", [{}])[0].get("main", "").lower()
                
                # Map weather to tags
                tags = {}
                if weather_main in ["thunderstorm", "drizzle", "rain"]:
                    tags["#rain"] = 1.0 * self.weight_scale
                elif weather_main == "snow":
                    tags["#snow"] = 1.0 * self.weight_scale
                elif weather_main == "clear":
                    tags["#clear"] = 1.0 * self.weight_scale
                elif weather_main == "clouds":
                    tags["#cloudy"] = 1.0 * self.weight_scale
                
                self.cached_tags = tags
                logger.info(f"Weather updated: {weather_main} -> {tags}")
            else:
                logger.error(f"Weather API Error: {response.status_code}")
        except Exception as e:
            logger.error(f"Weather fetch failed: {e}")
