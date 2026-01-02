import time
import sys
import os
import argparse
from typing import List, Dict

# Ensure we can import from core and utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.config_loader import ConfigLoader
from core.executor import WEExecutor
from core.sensors import WindowSensor
from core.policies import ActivityPolicy, Policy, TimePolicy
from core.context import ContextManager
from core.arbiter import Arbiter
from core.matcher import Matcher
from core.controller import DisturbanceController
from core.sensors import WindowSensor, IdleSensor

def main() -> None:
    print("Context Aware WE Scheduler starting...")
    
    parser = argparse.ArgumentParser(description="Context Aware Wallpaper Engine Scheduler")
    parser.add_argument("--config", default="scheduler_config.json", help="Path to the configuration file")
    args = parser.parse_args()

    # Resolve config path
    config_path = args.config
    if not os.path.isabs(config_path):
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), config_path)

    # 1. Load Config
    try:
        config_loader = ConfigLoader(config_path)
        config = config_loader.load()
        print(f"Loaded {len(config_loader.get_playlists())} playlists from config.")
    except Exception as e:
        print(f"Failed to load config from {config_path}: {e}")
        return

    # 2. Initialize Executor
    we_path = config_loader.get_we_path()
    if not we_path:
        print("Error: 'we_path' not found in config.")
        return

    try:
        executor = WEExecutor(we_path)
        print(f"WE Executor initialized with path: {we_path}")
    except Exception as e:
        print(f"Failed to initialize executor: {e}")
        return

    # 3. Initialize Context Manager & Sensors
    context_manager = ContextManager()
    try:
        window_sensor = WindowSensor()
        idle_sensor = IdleSensor()
        context_manager.register_sensor("window", window_sensor)
        context_manager.register_sensor("idle", idle_sensor)
        print("ContextManager initialized with WindowSensor and IdleSensor.")
    except Exception as e:
        print(f"Failed to initialize sensors: {e}")
        return

    # 4. Initialize Policies
    policies: List[Policy] = []
    try:
        policy_config = config_loader.get_policies()
        if "activity" in policy_config:
            policies.append(ActivityPolicy(policy_config["activity"]))
        if "time" in policy_config:
            policies.append(TimePolicy(policy_config["time"]))
        print(f"Initialized {len(policies)} policies.")
    except Exception as e:
        print(f"Failed to initialize policies: {e}")
        return

    # 5. Initialize Arbiter & Matcher
    smoothing_window = config_loader.get_smoothing_window()
    arbiter = Arbiter(policies, smoothing_window=smoothing_window)
    matcher = Matcher(config_loader.get_playlists())
    print(f"Arbiter initialized with smoothing_window: {smoothing_window}m")
    print("Matcher initialized.")
    
    # 6. Initialize Disturbance Controller
    disturbance_config = config_loader.get_disturbance_config()
    print(f"Disturbance Config: {disturbance_config}")
    controller = DisturbanceController(disturbance_config)
    print("DisturbanceController initialized.")
    
    current_playlist: str = ""

    print("Entering main loop... (Press Ctrl+C to stop)")
    try:
        while True:
            # Main Loop
            # 1. Sense & Aggregate Context
            context = context_manager.refresh()
            
            # 2. Think (Policy -> Arbiter -> Matcher)
            aggregated_tags = arbiter.arbitrate(context)
            best_playlist = matcher.match(aggregated_tags)
            
            # 3. Act (Executor)
            if best_playlist:
                # Check with Disturbance Controller
                if controller.can_switch(context):
                    if best_playlist != current_playlist:
                        print(f"\n[Action] Switching Playlist from '{current_playlist}' to '{best_playlist}'")
                        executor.open_playlist(best_playlist)
                        current_playlist = best_playlist
                        controller.notify_switch()
                    else:
                        # Same playlist, but maybe we want to cycle wallpaper?
                        # We can use the same disturbance rules for cycling wallpapers within a playlist
                        # This effectively keeps the playlist "fresh" even if the context hasn't changed
                        print(f"\n[Action] Cycling Wallpaper in '{current_playlist}'")
                        executor.next_wallpaper()
                        controller.notify_switch()
                else:
                    # Intent detected but blocked by controller
                    pass
            
            # Placeholder for testing: print sensor data and tags
            process_name = context.get("window", {}).get("process", "N/A")
            idle_time = context.get("idle", 0.0)
            print(f"\r[Sensor] {process_name} (Idle: {idle_time:.1f}s) -> [Tags] {aggregated_tags} -> [Decision] {best_playlist or 'None'}          ", end="", flush=True)
            
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping scheduler...")

if __name__ == "__main__":
    main()
