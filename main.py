from __future__ import annotations

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.diagnostics import SchedulerTickTrace

import sys
import os
import argparse
import subprocess
import time
import logging

# ── DPI Awareness ───────────────────────────────────────────────
# Must be called before any window or UI object is created.
# PROCESS_PER_MONITOR_DPI_AWARE (2) gives the sharpest rendering on
# high-DPI displays.  Falls back silently on older Windows versions.
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

# Ensure we can import from core and utils in source mode.
# When frozen, everything is bundled by PyInstaller.
if not getattr(sys, 'frozen', False):
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.app_context import get_app_root
from utils.logger import setup_logger


# ── CLI ─────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Host-mode flags (user-facing):
        --config      Path to scheduler_config.json
        --no-tray     Run without system tray icon (console mode)

    Dashboard subprocess flags (internal — suppressed from help):
        --dashboard   Launch the dashboard webview window
        --port        API port of the in-process HTTP server
        --locale      UI language for the dashboard client

    """
    parser = argparse.ArgumentParser(
        description="Context Aware Wallpaper Engine Scheduler"
    )
    parser.add_argument(
        "--config", default="scheduler_config.json",
        help="Path to the configuration file",
    )
    parser.add_argument(
        "--no-tray", action="store_true",
        help="Run without system tray icon (console mode)",
    )
    parser.add_argument("--dashboard", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--locale", default="en", help=argparse.SUPPRESS)
    return parser.parse_args()


# ── Config helpers ──────────────────────────────────────────────

def _resolve_config_path(config_arg: str) -> str:
    """Resolve a config path to an absolute path.

    Relative paths are resolved against the application root.
    """
    if os.path.isabs(config_arg):
        return config_arg
    return os.path.join(get_app_root(), config_arg)


# ── Mode runners ────────────────────────────────────────────────

def _spawn_dashboard_subprocess(port: int) -> None:
    """Spawn a detached dashboard subprocess loading the local host URL."""
    from utils.i18n import _current_lang

    if getattr(sys, "frozen", False):
        exe = sys.executable
        cmd = [exe, "--dashboard", f"--port={port}", f"--locale={_current_lang}"]
        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        exe = sys.executable
        script = os.path.join(get_app_root(), "main.py")
        cmd = [exe, script, "--dashboard", f"--port={port}", f"--locale={_current_lang}"]
        subprocess.Popen(cmd, creationflags=0)


def _run_dashboard(port: int, locale: str) -> None:
    """Dashboard subprocess entry point."""
    from ui.webview import DashboardWindow

    DashboardWindow(port, locale).create_and_block()


def _run_console_mode(config_path: str, logger: logging.Logger) -> None:
    """Create scheduler and run in console mode (--no-tray).

    No HTTP server, no tray — just the scheduler loop on a background
    thread with the main thread sleeping until KeyboardInterrupt.
    """
    from core.scheduler import WEScheduler
    from utils.history_logger import HistoryLogger
    from utils.app_context import get_data_dir

    scheduler = WEScheduler(config_path, HistoryLogger(get_data_dir()))
    try:
        scheduler.initialize()
    except Exception as e:
        logger.critical("Failed to initialize scheduler: %s", e)
        sys.exit(1)

    scheduler.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        scheduler.stop()


def _run_tray_mode(config_path: str, logger: logging.Logger) -> None:
    """Create scheduler, start the local dashboard API server, and block on
    the system tray icon.

    Error handling: log + native error dialog so the user sees it even
    though there's no console window.
    """
    from core.scheduler import WEScheduler
    from ui.dashboard import AnalysisStore, DashboardHTTPServer, build_tick_snapshot
    from ui.tray import TrayIcon
    from utils.history_logger import HistoryLogger
    from utils.app_context import get_data_dir

    scheduler = WEScheduler(config_path, HistoryLogger(get_data_dir()))
    try:
        scheduler.initialize()
    except Exception as e:
        logger.critical("Failed to initialize scheduler: %s", e)
        TrayIcon.show_startup_error(str(e))

    scheduler.start()

    analysis_store = AnalysisStore()

    def _handle_tick(trace: SchedulerTickTrace) -> None:
        analysis_store.update(build_tick_snapshot(scheduler, trace))

    scheduler.on_tick = _handle_tick
    httpd = DashboardHTTPServer(analysis_store, scheduler.history_logger, config_path)
    httpd.start()

    tray = TrayIcon(scheduler)
    tray.on_show_dashboard = lambda: _spawn_dashboard_subprocess(httpd.port)
    tray.run()


# ── Entry point ─────────────────────────────────────────────────

def main() -> None:
    logger = setup_logger()
    logger.info("Context Aware WE Scheduler starting...")

    args = _parse_args()

    if args.dashboard:
        _run_dashboard(args.port, args.locale)
        return

    config_path = _resolve_config_path(args.config)

    if args.no_tray:
        _run_console_mode(config_path, logger)
    else:
        _run_tray_mode(config_path, logger)


if __name__ == "__main__":
    main()
