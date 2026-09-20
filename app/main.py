from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time

from app.context import get_app_root
from app.logging import setup_logger

# ── CLI ─────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Host-mode flags (user-facing):
        --config               Path to the config directory
        --no-tray              Run without system tray icon (console mode)
        --dashboard-api-port   Local dashboard HTTP server port (0 = dynamic)

    Dashboard subprocess flags (internal — suppressed from help):
        --dashboard   Launch the dashboard webview window
        --port        API port of the in-process HTTP server
        --locale      UI language for the dashboard client

    """
    parser = argparse.ArgumentParser(description="Context Aware Wallpaper Engine Scheduler")
    parser.add_argument(
        "--config",
        default="config",
        help="Path to the configuration directory",
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="Run without system tray icon (console mode)",
    )
    parser.add_argument(
        "--dashboard-api-port",
        type=int,
        default=0,
        help="Local dashboard HTTP server port (0 = dynamic)",
    )
    parser.add_argument("--dashboard", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--locale", default="en", help=argparse.SUPPRESS)
    return parser.parse_args()


def _resolve_config_path(config_arg: str) -> str:
    if os.path.isabs(config_arg):
        return config_arg
    return os.path.join(get_app_root(), config_arg)


# ── Mode runners ────────────────────────────────────────────────


def _spawn_dashboard_subprocess(port: int) -> None:
    """Spawn a detached dashboard subprocess loading the local host URL."""
    from ui.i18n import current_lang

    if getattr(sys, "frozen", False):
        exe = sys.executable
        cmd = [exe, "--dashboard", f"--port={port}", f"--locale={current_lang}"]
        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        exe = sys.executable
        script = os.path.join(get_app_root(), "main.py")
        cmd = [exe, script, "--dashboard", f"--port={port}", f"--locale={current_lang}"]
        subprocess.Popen(cmd, creationflags=0)


def _run_dashboard(port: int, locale: str) -> None:
    """Dashboard subprocess entry point."""
    from ui.webview import DashboardWindow

    DashboardWindow(port, locale).create_and_block()


def _run_console_mode(config_dir: str, logger: logging.Logger) -> None:
    """Create scheduler and run in console mode (--no-tray).

    No HTTP server, no tray — just the scheduler loop on a background
    thread with the main thread sleeping until KeyboardInterrupt.
    """
    from app.context import get_data_dir
    from app.event_logger import JsonlEventLogger
    from core.runtime.scheduler import WEScheduler
    from ui.cli_status import CliStatusReporter

    scheduler = WEScheduler(config_dir, JsonlEventLogger(get_data_dir()))
    try:
        scheduler.initialize()
    except Exception as e:
        logger.critical("Failed to initialize scheduler: %s", e)
        sys.exit(1)

    scheduler.add_tick_listener(CliStatusReporter().on_tick)
    scheduler.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        scheduler.stop()


def _run_tray_mode(config_dir: str, logger: logging.Logger, dashboard_api_port: int = 0) -> None:
    """Create scheduler, start the local dashboard API server, and block on
    the system tray icon.

    Error handling: log + native error dialog so the user sees it even
    though there's no console window.
    """
    from app.context import get_data_dir
    from app.event_logger import JsonlEventLogger
    from core.runtime.scheduler import WEScheduler
    from core.state.tick_history import TickHistoryStore
    from ui.dashboard import DashboardHTTPServer, build_dashboard_app
    from ui.tick_history_export import export_tick_history
    from ui.tray import TrayIcon

    scheduler = WEScheduler(config_dir, JsonlEventLogger(get_data_dir()))
    try:
        scheduler.initialize()
    except Exception as e:
        logger.critical("Failed to initialize scheduler: %s", e)
        TrayIcon.show_startup_error(str(e))
        sys.exit(1)
    tick_history = TickHistoryStore()

    scheduler.add_tick_listener(tick_history.update)
    scheduler.start()
    dashboard_app = build_dashboard_app(tick_history, scheduler.profile_manager)
    httpd = DashboardHTTPServer(
        dashboard_app,
        requested_port=dashboard_api_port,
    )
    try:
        httpd.start()
    except OSError as exc:
        scheduler.stop()
        detail = str(exc)
        logger.critical(detail)
        TrayIcon.show_startup_error(detail)
        sys.exit(1)

    tray = TrayIcon(scheduler)
    tray.on_show_dashboard = lambda: _spawn_dashboard_subprocess(httpd.port)
    tray.on_export_tick_history = lambda: export_tick_history(
        tick_history,
        os.path.join(get_data_dir(), "tick-history"),
    )
    tray.run()


# ── Entry point ─────────────────────────────────────────────────


def main() -> None:
    logger = setup_logger()
    logger.info("Context Aware WE Scheduler starting...")

    args = _parse_args()

    if args.dashboard:
        _run_dashboard(args.port, args.locale)
        return

    config_dir = _resolve_config_path(args.config)

    if args.no_tray:
        _run_console_mode(config_dir, logger)
    else:
        _run_tray_mode(config_dir, logger, args.dashboard_api_port)


if __name__ == "__main__":
    main()
