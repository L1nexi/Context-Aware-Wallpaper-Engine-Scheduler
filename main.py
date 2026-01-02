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
from core.policies import ActivityPolicy, Policy
from core.context import ContextManager

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
        context_manager.register_sensor("window", window_sensor)
        print("ContextManager initialized with WindowSensor.")
    except Exception as e:
        print(f"Failed to initialize sensors: {e}")
        return

    # 4. Initialize Policies
    policies: List[Policy] = []
    try:
        policy_config = config_loader.get_policies()
        if "activity" in policy_config:
            policies.append(ActivityPolicy(policy_config["activity"]))
        print(f"Initialized {len(policies)} policies.")
    except Exception as e:
        print(f"Failed to initialize policies: {e}")
        return

    # TODO: Initialize Arbiter
    # TODO: Initialize Matcher
    
    print("Entering main loop... (Press Ctrl+C to stop)")
    try:
        while True:
            # Main Loop
            # 1. Sense & Aggregate Context
            context = context_manager.refresh()
            
            # 2. Think (Policy -> Arbiter -> Matcher)
            aggregated_tags: Dict[str, float] = {}
            for policy in policies:
                tags = policy.get_tags(context)
                for tag, weight in tags.items():
                    aggregated_tags[tag] = aggregated_tags.get(tag, 0.0) + weight
            
            # 3. Act (Executor)
            
            # Placeholder for testing: print sensor data and tags
            process_name = context.get("window", {}).get("process", "N/A")
            print(f"\r[Sensor] {process_name} -> [Tags] {aggregated_tags}          ", end="", flush=True)
            
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping scheduler...")

if __name__ == "__main__":
    main()
