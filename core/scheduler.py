import time
import threading
import logging
import json
import os
import sys
from typing import List, Dict, Any, Optional

from utils.config_loader import ConfigLoader
from utils.app_context import get_app_root
from core.executor import WEExecutor
from core.sensors import WindowSensor, IdleSensor, CpuSensor
from core.policies import ActivityPolicy, Policy, TimePolicy, SeasonPolicy, WeatherPolicy
from core.context import ContextManager
from core.arbiter import Arbiter
from core.matcher import Matcher
from core.controller import DisturbanceController
from core.actuator import Actuator

logger = logging.getLogger("WEScheduler.Core")

_STATE_FILE = os.path.join(get_app_root(), "state.json")


def _load_state() -> Dict[str, Any]:
    """Load persisted state from state.json. Returns {} on any error."""
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    """Persist state to state.json. Silently ignores write errors."""
    try:
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        logger.warning("Failed to write state.json", exc_info=True)

class WEScheduler:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.initialized = False
        self.running = False
        self.paused = False
        self.pause_until: float = 0
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()

        # Hook: called (from the scheduler thread) after an automatic
        # timed-pause resume.  Allows the tray to sync icon / menu
        # without polling or guessing timing.
        self.on_auto_resume = None
        
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
            cpu_window = disturbance_config.get("cpu_window", 10)
            self.context_manager.register_sensor("cpu", CpuSensor(cpu_window))
            controller = DisturbanceController(disturbance_config)
            self.actuator = Actuator(self.executor, controller)

            # 7. Restore persisted state
            state = _load_state()
            self.current_playlist = state.get("current_playlist", "")
            saved_until = float(state.get("pause_until", 0))
            if saved_until > time.time():
                # Timed pause is still active — restore it
                self.paused = True
                self.pause_until = saved_until
                logger.info(
                    f"Restored timed pause (until "
                    f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(saved_until))})."
                )
            elif state.get("paused") and saved_until == 0:
                # Indefinite pause was active, restore it
                self.paused = True
                self.pause_until = 0
                logger.info("Restored indefinite pause.")

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
        _save_state(self._build_state())
        logger.info("Scheduler stopped.")

    def pause(self, seconds: Optional[int] = None):
        """
        Pauses the scheduler.
        :param seconds: Duration in seconds. None means indefinite.
        """
        self.paused = True
        if seconds is not None:
            self.pause_until = time.time() + seconds
            logger.info(f"Scheduler paused for {seconds}s (until {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.pause_until))}).")
        else:
            self.pause_until = 0
            logger.info("Scheduler paused (indefinitely).")
        _save_state(self._build_state())

    def resume(self):
        self.paused = False
        self.pause_until = 0
        logger.info("Scheduler resumed.")
        _save_state(self._build_state())

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
                    if self.on_auto_resume:
                        try:
                            self.on_auto_resume()
                        except Exception:
                            logger.exception("on_auto_resume hook failed")
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
                new_playlist = self.actuator.act(
                    context, aggregated_tags, best_playlist, self.current_playlist
                )
                if new_playlist != self.current_playlist:
                    self.current_playlist = new_playlist
                    _save_state(self._build_state())
                
                # Status Update (for console/tray)
                self._update_status(context, aggregated_tags, best_playlist)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
            
            time.sleep(1)

    def _build_state(self) -> Dict[str, Any]:
        """Returns a snapshot of the scheduler state suitable for persistence."""
        return {
            "paused": self.paused,
            "pause_until": self.pause_until,
            "current_playlist": self.current_playlist,
        }

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
        # Print to console if not frozen (PyInstaller)
        if not getattr(sys, 'frozen', False):
            print(f"\r{self.last_status_line:<100}", end="", flush=True)
