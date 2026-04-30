from __future__ import annotations

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.scheduler import WEScheduler, Context, MatchResult

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
        --locale      UI language for the dashboard SPA
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


# ── Dashboard subprocess spawning ───────────────────────────────

def _spawn_dashboard_subprocess(port: int) -> None:
    """Spawn a detached dashboard subprocess loading the in-process HTTP server.

    Called by the tray menu handler.  The subprocess runs independently —
    closing the tray host does not kill the dashboard window.
    """
    from utils.i18n import _current_lang

    if getattr(sys, 'frozen', False):
        exe = sys.executable
        cmd = [exe, '--dashboard', f'--port={port}', f'--locale={_current_lang}']
        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        exe = sys.executable
        script = os.path.join(get_app_root(), 'main.py')
        cmd = [exe, script, '--dashboard', f'--port={port}', f'--locale={_current_lang}']
        subprocess.Popen(cmd, creationflags=0)


# ── Mode runners ────────────────────────────────────────────────

def _run_dashboard(port: int, locale: str) -> None:
    """Dashboard subprocess entry point.

    Opens a pywebview window loading the SPA from the host's HTTP server,
    then blocks until the window is closed.
    """
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
    """Create scheduler, start HTTP server, and block on the system tray icon.

    Error handling: log + native error dialog so the user sees it even
    though there's no console window.
    """
    from core.scheduler import WEScheduler
    from ui.dashboard import DashboardHTTPServer, StateStore, build_tick_state
    from ui.tray import TrayIcon
    from utils.history_logger import HistoryLogger
    from utils.app_context import get_data_dir

    scheduler = WEScheduler(config_path, HistoryLogger(get_data_dir()))
    try:
        scheduler.initialize()
    except Exception as e:
        msg = str(e)
        logger.critical("Failed to initialize scheduler: %s", msg)
        TrayIcon.show_startup_error(msg)
        sys.exit(1)

    scheduler.start()

    state_store = StateStore()
    def _handle_tick(scheduler: WEScheduler, context: Context, result: MatchResult) -> None:
        state_store.update(build_tick_state(scheduler, context, result))
    scheduler.on_tick = _handle_tick
    httpd = DashboardHTTPServer(state_store, scheduler.history_logger, config_path)
    httpd.start()

    tray = TrayIcon(scheduler)

    def _on_show_dashboard():
        _spawn_dashboard_subprocess(httpd.port)
    tray.on_show_dashboard = _on_show_dashboard
    tray.run()


# ── Entry point ─────────────────────────────────────────────────

def main() -> None:
    logger = setup_logger()
    logger.info("Context Aware WE Scheduler starting...")

    args = _parse_args()

    # Dashboard subprocess — tray host spawns this to display the SPA.
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
