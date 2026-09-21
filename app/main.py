from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys

from app.context import get_app_root
from app.logging import setup_logger

# ── CLI ─────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Host-mode flags (user-facing):
        --config       Path to the config directory
        --api-port     Local API HTTP server port (0 = dynamic)

    Window subprocess flags (internal — suppressed from help):
        --window      Launch the webview window
        --port        API port of the in-process HTTP server
        --locale      UI language for the webview client

    """
    parser = argparse.ArgumentParser(description="Context Aware Wallpaper Engine Scheduler")
    parser.add_argument(
        "--config",
        default="config",
        help="Path to the configuration directory",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=0,
        help="Local API HTTP server port (0 = dynamic)",
    )
    parser.add_argument("--window", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--setup", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--locale", default="en", help=argparse.SUPPRESS)
    return parser.parse_args()


def _resolve_config_path(config_arg: str) -> str:
    if os.path.isabs(config_arg):
        return config_arg
    return os.path.join(get_app_root(), config_arg)


# ── Mode runners ────────────────────────────────────────────────


def _spawn_window_subprocess(port: int, *, setup: bool = False) -> subprocess.Popen[bytes]:
    """Spawn a detached webview subprocess loading the local host URL."""
    from ui.i18n import current_lang

    cmd = [sys.executable]
    creationflags = 0
    if getattr(sys, "frozen", False):
        creationflags = subprocess.CREATE_NO_WINDOW
    else:
        cmd.append(os.path.join(get_app_root(), "main.py"))
    cmd.extend(("--window", f"--port={port}", f"--locale={current_lang}"))
    if setup:
        cmd.append("--setup")
    return subprocess.Popen(cmd, creationflags=creationflags)


def _run_window(port: int, locale: str, *, setup: bool = False) -> None:
    """Webview subprocess entry point."""
    from ui.webview import AppWindow

    path = "/setup/" if setup else "/"
    AppWindow(port, locale, path=path).create_and_block()


def _run_tray_mode(config_dir: str, logger: logging.Logger, api_port: int = 0) -> None:
    """Create scheduler, start the local API server, and block on the system
    tray icon.

    Error handling: log + native error dialog so the user sees it even
    though there's no console window.
    """
    from app.context import get_data_dir
    from app.event_logger import JsonlEventLogger
    from app.startup import ensure_initial_profile
    from core.runtime.profile_manager import ProfileManager
    from core.runtime.scheduler import WEScheduler
    from core.state.tick_history import TickHistoryStore
    from ui.api_server import APIServer, build_api_app
    from ui.tick_history_export import export_tick_history
    from ui.tray import TrayIcon

    data_dir = get_data_dir()
    profile_manager = ProfileManager(config_dir)
    scheduler = WEScheduler(
        profile_manager=profile_manager,
        event_logger=JsonlEventLogger(data_dir),
    )
    tick_history = TickHistoryStore()
    api_server = APIServer(
        build_api_app(tick_history, profile_manager),
        requested_port=api_port,
    )

    try:
        api_server.start()
    except OSError as exc:
        detail = str(exc)
        logger.critical(detail)
        TrayIcon.show_startup_error(detail)
        sys.exit(1)

    def launch_setup() -> subprocess.Popen[bytes]:
        logger.info("No Profile found; opening first-run setup.")
        return _spawn_window_subprocess(api_server.port, setup=True)

    try:
        profile_ready = ensure_initial_profile(profile_manager, launch_setup)
        if not profile_ready:
            logger.info("First-run setup closed before completion.")
            return

        scheduler.initialize()
        scheduler.add_tick_listener(tick_history.update)
        scheduler.start()

        tray = TrayIcon(scheduler)
        tray.on_show_settings = lambda: _spawn_window_subprocess(api_server.port)
        tray.on_export_tick_history = lambda: export_tick_history(
            tick_history,
            os.path.join(data_dir, "tick-history"),
        )
        tray.run()
    except Exception as exc:
        logger.critical("Failed to start application: %s", exc)
        TrayIcon.show_startup_error(str(exc))
    finally:
        scheduler.stop()
        api_server.stop()


# ── Entry point ─────────────────────────────────────────────────


def main() -> None:
    logger = setup_logger()
    logger.info("Context Aware WE Scheduler starting...")

    args = _parse_args()

    if args.window:
        _run_window(args.port, args.locale, setup=args.setup)
        return

    config_dir = _resolve_config_path(args.config)
    _run_tray_mode(config_dir, logger, args.api_port)


if __name__ == "__main__":
    main()
