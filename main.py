import time
import sys
import os

# Ensure we can import from core and utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.config_loader import ConfigLoader
from core.executor import WEExecutor

# Constants
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduler_config.json")
WE_PATH = r"E:\SteamLibrary\steamapps\common\wallpaper_engine\wallpaper64.exe"

def main():
    print("Context Aware WE Scheduler starting...")
    
    # 1. Load Config
    try:
        config_loader = ConfigLoader(CONFIG_PATH)
        config = config_loader.load()
        print(f"Loaded {len(config_loader.get_playlists())} playlists from config.")
    except Exception as e:
        print(f"Failed to load config: {e}")
        return

    # 2. Initialize Executor
    try:
        executor = WEExecutor(WE_PATH)
        print("WE Executor initialized.")
    except Exception as e:
        print(f"Failed to initialize executor: {e}")
        return

    # TODO: Initialize Sensors
    # TODO: Initialize Policies
    # TODO: Initialize Arbiter
    # TODO: Initialize Matcher
    
    print("Entering main loop... (Press Ctrl+C to stop)")
    try:
        while True:
            # Main Loop
            # 1. Sense
            # 2. Think (Policy -> Arbiter -> Matcher)
            # 3. Act (Executor)
            
            # Placeholder for testing: just print a heartbeat
            # print(".", end="", flush=True)
            
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nStopping scheduler...")

if __name__ == "__main__":
    main()
