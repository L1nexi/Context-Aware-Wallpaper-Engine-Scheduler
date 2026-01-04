import unittest
import sys
import os
import time
from typing import Dict, Any

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.controller import DisturbanceController

class TestDisturbanceController(unittest.TestCase):
    def setUp(self):
        self.config = {
            "idle_threshold": 10,
            "min_interval": 60,         # Playlist switch interval
            "wallpaper_interval": 300,  # Wallpaper cycle interval (5 mins)
            "force_interval": 3600
        }
        self.controller = DisturbanceController(self.config)
        # Reset timers to 0 for predictable testing
        self.controller.last_playlist_switch_time = 0
        self.controller.last_wallpaper_switch_time = 0

    def test_playlist_switch_cooldown(self):
        """Test that playlist switching respects min_interval"""
        # 1. Initial state: should allow switch (time=0, last=0 is tricky, let's simulate time passing)
        # Actually, if last_switch is 0, and current time is huge, it should allow.
        # Let's set last_switch to NOW
        now = time.time()
        self.controller.last_playlist_switch_time = now
        
        context = {"idle": 0}
        
        # 2. Try immediately -> Should fail (cooling down)
        self.assertFalse(self.controller.can_switch_playlist(context))
        
        # 3. Try after min_interval + 1s, but NOT idle -> Should fail (need idle)
        # Mock time is hard without mocking time.time(). 
        # Instead, we can manipulate last_switch_time.
        
        # Set last switch to (min_interval + 10) seconds ago
        self.controller.last_playlist_switch_time = now - (self.config["min_interval"] + 10)
        
        # Not idle -> False
        context["idle"] = 0
        self.assertFalse(self.controller.can_switch_playlist(context))
        
        # Idle -> True
        context["idle"] = 15
        self.assertTrue(self.controller.can_switch_playlist(context))

    def test_wallpaper_cycle_independent(self):
        """Test that wallpaper cycling has its own timer"""
        now = time.time()
        
        # Case: Playlist switched recently, but wallpaper hasn't cycled in a long time?
        # Wait, notify_playlist_switch updates BOTH timers.
        # So if we switched playlist, we also reset wallpaper timer.
        
        self.controller.notify_playlist_switch()
        # Both timers are now NOW.
        
        context = {"idle": 15}
        
        # 1. Immediate check -> Both False
        self.assertFalse(self.controller.can_switch_playlist(context))
        self.assertFalse(self.controller.can_cycle_wallpaper(context))
        
        # 2. Fast forward 2 mins ( > min_interval=60, < wallpaper_interval=300)
        # Playlist switch allowed? Yes (if idle)
        # Wallpaper cycle allowed? No (needs 300s)
        
        self.controller.last_playlist_switch_time = now - 120
        self.controller.last_wallpaper_switch_time = now - 120
        
        self.assertTrue(self.controller.can_switch_playlist(context))
        self.assertFalse(self.controller.can_cycle_wallpaper(context))
        
        # 3. Fast forward 6 mins ( > 300)
        self.controller.last_playlist_switch_time = now - 360
        self.controller.last_wallpaper_switch_time = now - 360
        
        self.assertTrue(self.controller.can_switch_playlist(context))
        self.assertTrue(self.controller.can_cycle_wallpaper(context))

    def test_wallpaper_cycle_reset(self):
        """Test that cycling wallpaper only resets its own timer"""
        now = time.time()
        # Set both to old
        self.controller.last_playlist_switch_time = now - 1000
        self.controller.last_wallpaper_switch_time = now - 1000
        
        self.controller.notify_wallpaper_cycle()
        
        # Playlist timer should still be old
        self.assertAlmostEqual(self.controller.last_playlist_switch_time, now - 1000, delta=1)
        # Wallpaper timer should be new
        self.assertAlmostEqual(self.controller.last_wallpaper_switch_time, time.time(), delta=1)

if __name__ == '__main__':
    unittest.main()
