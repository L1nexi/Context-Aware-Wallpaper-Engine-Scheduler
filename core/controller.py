import time
from typing import Dict, Any

class DisturbanceController:
    def __init__(self, config: Dict[str, Any]):
        self.idle_threshold = config.get("idle_threshold", 60)
        self.min_interval = config.get("min_interval", 1800)
        self.force_interval = config.get("force_interval", 14400)
        
        # Initialize last_switch_time to current time to prevent immediate switch on startup
        # Or set to 0 if we WANT an immediate switch on startup (usually preferred to sync state)
        # Let's set it to 0 so the first valid decision is executed immediately.
        self.last_switch_time = 0.0

    def can_switch(self, context: Dict[str, Any]) -> bool:
        """
        Determines if a switch is allowed based on disturbance control rules.
        """
        current_time = time.time()
        time_since_last_switch = current_time - self.last_switch_time
        
        # 1. Cooling Down Check
        if time_since_last_switch < self.min_interval:
            return False

        # 2. Idle Check
        # Assuming context has an "idle" key from IdleSensor
        idle_time = context.get("idle", 0.0)
        
        if idle_time >= self.idle_threshold:
            return True
        
        # 3. Force Switch Check (Fallback)
        if time_since_last_switch >= self.force_interval:
            return True
            
        return False

    def notify_switch(self):
        """
        Call this method AFTER a successful switch to update the timer.
        """
        self.last_switch_time = time.time()
