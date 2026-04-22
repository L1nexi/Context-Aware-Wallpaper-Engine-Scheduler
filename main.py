import sys
import os
import argparse
import time

# ── DPI Awareness ───────────────────────────────────────────────
# Must be called before any window or UI object is created.
# PROCESS_PER_MONITOR_DPI_AWARE (2) gives the sharpest rendering on
# high-DPI displays.  Falls back silently on older Windows versions.
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

# Ensure we can import from core and utils
# When frozen, we don't need this as everything is bundled.
# But for script mode, we keep it.
if not getattr(sys, 'frozen', False):
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.app_context import get_app_root
from utils.logger import setup_logger
from core.scheduler import WEScheduler
from core.tray import TrayIcon

def main() -> None:
    logger = setup_logger()
    logger.info("Context Aware WE Scheduler starting...")
    
    parser = argparse.ArgumentParser(description="Context Aware Wallpaper Engine Scheduler")
    parser.add_argument("--config", default="scheduler_config.json", help="Path to the configuration file")
    parser.add_argument("--no-tray", action="store_true", help="Run without system tray icon (console mode)")
    args = parser.parse_args()

    # Resolve config path
    config_path = args.config
    if not os.path.isabs(config_path):
        config_path = os.path.join(get_app_root(), config_path)

    # Initialize Scheduler
    scheduler = WEScheduler(config_path)

    try:
        scheduler.initialize()
    except Exception as e:
        msg = str(e)
        logger.critical(f"Failed to initialize scheduler: {msg}")
        if not args.no_tray:
            TrayIcon.show_startup_error(msg)
        sys.exit(1)

    # Start Scheduler Loop (in background thread)
    scheduler.start()
    
    if args.no_tray:
        # Console Mode: Keep main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            scheduler.stop()
    else:
        # Tray Mode: Blocks main thread
        logger.info("Starting System Tray...")
        tray = TrayIcon(scheduler)
        tray.run()

if __name__ == "__main__":
    main()
