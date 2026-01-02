import logging
from typing import List, Dict, Any
from core.policies import Policy

logger = logging.getLogger("WEScheduler.Arbiter")

class Arbiter:
    def __init__(self, policies: List[Policy], smoothing_window: int = 60):
        self.policies = policies
        # Calculate alpha for EMA: alpha = 2 / (N + 1)
        # If window is <= 1, we want instant reaction (alpha = 1.0)
        if smoothing_window <= 1:
            self.alpha = 1.0
        else:
            self.alpha = 2.0 / (smoothing_window + 1.0)
        
        self.smoothed_tags: Dict[str, float] = {}

    def arbitrate(self, context: Dict[str, Any]) -> Dict[str, float]:
        """
        Aggregates tags from all policies based on the given context.
        Returns a dictionary of tags and their summed weights.
        Applies Exponential Moving Average (EMA) for smoothing.
        """
        # 1. Calculate Instant Tags
        instant_tags: Dict[str, float] = {}
        for policy in self.policies:
            try:
                tags = policy.get_tags(context)
                for tag, weight in tags.items():
                    instant_tags[tag] = instant_tags.get(tag, 0.0) + weight
            except Exception as e:
                logger.error(f"Error in policy {type(policy).__name__}: {e}")
        
        # 2. Apply EMA Smoothing
        self.smoothed_tags = self._apply_ema(instant_tags)
                
        return self.smoothed_tags

    def _apply_ema(self, instant_tags: Dict[str, float]) -> Dict[str, float]:
        """
        Applies Exponential Moving Average to the tags.
        """
        if not self.smoothed_tags:
            return instant_tags.copy()

        # Union of all tags seen so far (in history or current)
        all_tags = set(self.smoothed_tags.keys()) | set(instant_tags.keys())
        new_smoothed_tags = {}
        
        for tag in all_tags:
            current_weight = instant_tags.get(tag, 0.0)
            previous_weight = self.smoothed_tags.get(tag, 0.0)
            
            new_weight = self.alpha * current_weight + (1.0 - self.alpha) * previous_weight
            
            # Cleanup threshold to prevent memory leak for very small weights
            if new_weight >= 0.001:
                new_smoothed_tags[tag] = new_weight
        
        return new_smoothed_tags
