import time
import sys
import os
import argparse
from typing import List, Dict, Any

# Ensure we can import from core and utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.config_loader import ConfigLoader
from utils.logger import setup_logger
from core.executor import WEExecutor
from core.sensors import WindowSensor
from core.policies import ActivityPolicy, Policy, TimePolicy, SeasonPolicy, WeatherPolicy
from core.context import ContextManager
from core.arbiter import Arbiter
from core.matcher import Matcher
from core.controller import DisturbanceController
from core.actuator import Actuator
from core.sensors import WindowSensor, IdleSensor

def render_status_bar(context: Dict[str, Any], tags: Dict[str, float], decision: str) -> str:
    """
    Renders a cool status bar for the console.
    Format: [Decision] PLAYLIST | #tag1 0.9 ■■■■■ | #tag2 0.5 ■■
    """
    # 1. Process Info
    process_name = context.get("window", {}).get("process", "N/A")
    idle_time = context.get("idle", 0.0)
    
    # 2. Sort and format tags
    sorted_tags = sorted(tags.items(), key=lambda x: x[1], reverse=True)[:3] # Top 3
    
    tag_parts = []
    for tag, weight in sorted_tags:
        # Bar length: max 5 blocks for 1.0+
        bar_len = int(min(weight, 1.5) * 5) 
        bar = "■" * bar_len
        tag_parts.append(f"{tag} {weight:.1f} {bar}")
    
    tag_str = " | ".join(tag_parts)
    
    # 3. Assemble
    # Clear line with spaces at the end
    return f"\r[{decision or 'WAITING'}] {process_name}({idle_time:.0f}s) >> {tag_str:<50}"

def main() -> None:
    logger = setup_logger()
    logger.info("Context Aware WE Scheduler starting...")
    
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
        logger.info(f"Loaded {len(config_loader.get_playlists())} playlists from config.")
    except Exception as e:
        logger.error(f"Failed to load config from {config_path}: {e}")
        return

    # 2. Initialize Executor
    we_path = config_loader.get_we_path()
    if not we_path:
        logger.error("Error: 'we_path' not found in config.")
        return

    try:
        executor = WEExecutor(we_path)
        logger.info(f"WE Executor initialized with path: {we_path}")
    except Exception as e:
        logger.error(f"Failed to initialize executor: {e}")
        return

    # 3. Initialize Context Manager & Sensors
    context_manager = ContextManager()
    try:
        window_sensor = WindowSensor()
        idle_sensor = IdleSensor()
        context_manager.register_sensor("window", window_sensor)
        context_manager.register_sensor("idle", idle_sensor)
        logger.info("ContextManager initialized with WindowSensor and IdleSensor.")
    except Exception as e:
        logger.error(f"Failed to initialize sensors: {e}")
        return

    # 4. Initialize Policies
    policies: List[Policy] = []
    try:
        policy_config = config_loader.get_policies()
        if "activity" in policy_config:
            policies.append(ActivityPolicy(policy_config["activity"]))
        if "time" in policy_config:
            policies.append(TimePolicy(policy_config["time"]))
        if "season" in policy_config:
            policies.append(SeasonPolicy(policy_config["season"]))
        if "weather" in policy_config:
            policies.append(WeatherPolicy(policy_config["weather"]))
            
        logger.info(f"Initialized {len(policies)} policies.")
    except Exception as e:
        logger.error(f"Failed to initialize policies: {e}")
        return

    # 5. Initialize Arbiter & Matcher
    arbiter = Arbiter(policies)
    matcher = Matcher(config_loader.get_playlists())
    logger.info("Arbiter initialized.")
    logger.info("Matcher initialized.")
    
    # 6. Initialize Disturbance Controller & Actuator
    disturbance_config = config_loader.get_disturbance_config()
    logger.info(f"Disturbance Config: {disturbance_config}")
    controller = DisturbanceController(disturbance_config)
    actuator = Actuator(executor, controller)
    logger.info("DisturbanceController & Actuator initialized.")
    
    current_playlist: str = ""

    logger.info("Entering main loop... (Press Ctrl+C to stop)")
    try:
        while True:
            # Main Loop
            # 1. Sense & Aggregate Context
            context = context_manager.refresh()
            
            # 2. Think (Policy -> Arbiter -> Matcher)
            aggregated_tags = arbiter.arbitrate(context)
            best_playlist = matcher.match(aggregated_tags)
            
            # 3. Act (Actuator)
            current_playlist = actuator.act(context, aggregated_tags, best_playlist, current_playlist)
            
            # Dynamic Status Line
            status_line = render_status_bar(context, aggregated_tags, best_playlist)
            print(status_line, end="", flush=True)
            
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping scheduler...")

if __name__ == "__main__":
    main()
