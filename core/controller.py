import time
import logging
from typing import Dict, Any

logger = logging.getLogger("WEScheduler.Controller")

class DisturbanceController:
    def __init__(self, config: Dict[str, Any]):
        self.idle_threshold = config.get("idle_threshold", 60)
        
        # Playlist Switching Config
        self.playlist_min_interval = config.get("min_interval", 1800)
        self.playlist_force_interval = config.get("force_interval", 14400)
        
        # Wallpaper Cycling Config (New)
        # Default: Cycle wallpaper every 10 mins if playlist hasn't changed
        self.wallpaper_min_interval = config.get("wallpaper_interval", 600) 
        
        self.last_playlist_switch_time = 0
        self.last_wallpaper_switch_time = 0

    def can_switch_playlist(self, context: Dict[str, Any]) -> bool:
        """
        Determines if switching to a NEW playlist is allowed.
        """
        current_time = time.time()
        time_since_last = current_time - self.last_playlist_switch_time
        
        # 1. Cooling Down Check
        if time_since_last < self.playlist_min_interval:
            return False

        # 2. Idle Check
        idle_time = context.get("idle", 0.0)
        if idle_time >= self.idle_threshold:
            return True
        
        # 3. Force Switch Check
        if time_since_last >= self.playlist_force_interval:
            return True
            
        return False

    def can_cycle_wallpaper(self, context: Dict[str, Any]) -> bool:
        """
        Determines if cycling to the NEXT wallpaper within the SAME playlist is allowed.
        """
        current_time = time.time()
        time_since_last = current_time - self.last_wallpaper_switch_time
        
        # 1. Cooling Down Check (Strict)
        if time_since_last < self.wallpaper_min_interval:
            return False
            
        # 2. Idle Check (Strict)
        # We only cycle wallpaper when user is idle to avoid distraction
        idle_time = context.get("idle", 0.0)
        if idle_time >= self.idle_threshold:
            return True
            
        return False

    def notify_playlist_switch(self):
        self.last_playlist_switch_time = time.time()
        # Switching playlist also counts as switching wallpaper
        self.last_wallpaper_switch_time = time.time()

    def notify_wallpaper_cycle(self):
        self.last_wallpaper_switch_time = time.time()
