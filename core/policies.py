from abc import ABC, abstractmethod
from typing import Dict, Any

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

    def get_tags(self, context: Dict[str, Any]) -> Dict[str, float]:
        if not self.enabled:
            return {}

        window_info = context.get("window", {})
        process_name = window_info.get("process", "")
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
