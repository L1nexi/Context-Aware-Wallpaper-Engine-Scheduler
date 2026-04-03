import time
import threading
import logging
import os
import sys
from typing import List, Dict, Any, Optional

from utils.config_loader import ConfigLoader
from core.executor import WEExecutor
from core.sensors import WindowSensor, IdleSensor
from core.policies import ActivityPolicy, Policy, TimePolicy, SeasonPolicy, WeatherPolicy
from core.context import ContextManager
from core.arbiter import Arbiter
from core.matcher import Matcher
from core.controller import DisturbanceController
from core.actuator import Actuator

logger = logging.getLogger("WEScheduler.Core")

class WEScheduler:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.initialized = False
        self.running = False
        self.paused = False
        self.pause_until: float = 0
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # Components
        self.config_loader: Optional[ConfigLoader] = None
        self.executor: Optional[WEExecutor] = None
        self.context_manager: Optional[ContextManager] = None
        self.arbiter: Optional[Arbiter] = None
        self.matcher: Optional[Matcher] = None
        self.actuator: Optional[Actuator] = None
        
        self.current_playlist: str = ""
        self.last_status_line: str = ""

    def initialize(self) -> bool:
        """Initializes all components. Returns True if successful."""
        try:
            # 1. Load Config
            self.config_loader = ConfigLoader(self.config_path)
            config = self.config_loader.load()
            logger.info(f"Loaded {len(self.config_loader.get_playlists())} playlists.")

            # 2. Initialize Executor
            we_path = self.config_loader.get_we_path()
            if not we_path:
                logger.error("'we_path' not found in config.")
                return False
            self.executor = WEExecutor(we_path)

            # 3. Initialize Sensors
            self.context_manager = ContextManager()
            self.context_manager.register_sensor("window", WindowSensor())
            self.context_manager.register_sensor("idle", IdleSensor())

            # 4. Initialize Policies
            policies: List[Policy] = []
            policy_config = self.config_loader.get_policies()
            if "activity" in policy_config:
                policies.append(ActivityPolicy(policy_config["activity"]))
            if "time" in policy_config:
                policies.append(TimePolicy(policy_config["time"]))
            if "season" in policy_config:
                policies.append(SeasonPolicy(policy_config["season"]))
            if "weather" in policy_config:
                policies.append(WeatherPolicy(policy_config["weather"]))

            # 5. Initialize Logic
            self.arbiter = Arbiter(policies)
            self.matcher = Matcher(self.config_loader.get_playlists())
            
            # 6. Initialize Controller & Actuator
            disturbance_config = self.config_loader.get_disturbance_config()
            controller = DisturbanceController(disturbance_config)
            self.actuator = Actuator(self.executor, controller)
            
            logger.info("Scheduler initialized successfully.")
            self.initialized = True
            return True
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False

    def start(self):
        if self.running:
            logger.warning("Scheduler is already running.")
            return
        
        if not getattr(self, 'initialized', False):
            logger.error("Scheduler not initialized. Call initialize() first.")
            return

        self.running = True
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("Scheduler started.")

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
        logger.info("Scheduler stopped.")

    def pause(self):
        self.paused = True
        self.pause_until = 0
        logger.info("Scheduler paused (indefinitely).")

    def pause_for(self, seconds: int):
        """Pauses the scheduler for a specified duration in seconds."""
        self.pause_until = time.time() + seconds
        self.paused = True
        logger.info(f"Scheduler paused for {seconds}s (until {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.pause_until))}).")

    def resume(self):
        self.paused = False
        self.pause_until = 0
        logger.info("Scheduler resumed.")

    def get_pause_remaining(self) -> Optional[float]:
        """Returns remaining pause seconds, or None if not in a timed pause."""
        if not self.paused or self.pause_until == 0:
            return None
        remaining = self.pause_until - time.time()
        return max(0.0, remaining)

    def _run_loop(self):
        while not self.stop_event.is_set():
            if self.paused:
                # Check for timed pause expiry
                if self.pause_until > 0 and time.time() >= self.pause_until:
                    logger.info("Timed pause expired. Resuming scheduler.")
                    self.resume()
                else:
                    time.sleep(1)
                    continue

            try:
                # 1. Sense
                context = self.context_manager.refresh()
                
                # 2. Think
                aggregated_tags = self.arbiter.arbitrate(context)
                best_playlist = self.matcher.match(aggregated_tags)
                
                # 3. Act
                self.current_playlist = self.actuator.act(
                    context, aggregated_tags, best_playlist, self.current_playlist
                )
                
                # Status Update (for console/tray)
                self._update_status(context, aggregated_tags, best_playlist)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
            
            time.sleep(1)

    def _update_status(self, context: Dict[str, Any], tags: Dict[str, float], decision: str):
        process_name = context.get("window", {}).get("process", "N/A")
        idle_time = context.get("idle", 0.0)
        sorted_tags = sorted(tags.items(), key=lambda x: x[1], reverse=True)[:3]
        
        tag_parts = []
        for tag, weight in sorted_tags:
            bar_len = int(min(weight, 1.5) * 5) 
            bar = "■" * bar_len
            tag_parts.append(f"{tag} {weight:.1f} {bar}")
        
        tag_str = " | ".join(tag_parts)
        self.last_status_line = f"[{decision or 'WAITING'}] {process_name}({idle_time:.0f}s) >> {tag_str}"
        # Print to console if attached
        if sys.stdout and not getattr(sys, 'frozen', False):
             print(f"\r{self.last_status_line:<100}", end="", flush=True)
