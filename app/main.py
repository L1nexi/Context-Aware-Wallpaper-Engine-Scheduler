from __future__ import annotations

import argparse
import ctypes
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
        --server-port   Local frontend HTTP server port (0 = dynamic)

    GUI subprocess flags (internal — suppressed from help):
        --gui         Launch the GUI webview window
        --port        API port of the in-process HTTP server
        --locale      UI language for the GUI client

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
        "--server-port",
        type=int,
        default=0,
        help="Local frontend HTTP server port (0 = dynamic)",
    )
    parser.add_argument("--gui", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--locale", default="en", help=argparse.SUPPRESS)
    return parser.parse_args()


def _resolve_config_path(config_arg: str) -> str:
    if os.path.isabs(config_arg):
        return config_arg
    return os.path.join(get_app_root(), config_arg)


def _ensure_console_for_config_mode() -> None:
    if sys.platform != "win32":
        return
    if not getattr(sys, "frozen", False):
        return

    ATTACH_PARENT_PROCESS = -1
    if not ctypes.windll.kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
        ctypes.windll.kernel32.AllocConsole()

    sys.stdin = open("CONIN$", encoding="utf-8", errors="replace")
    sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
    sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")


# ── Mode runners ────────────────────────────────────────────────


def _spawn_gui_subprocess(port: int) -> None:
    """Spawn a detached GUI subprocess loading the local host URL."""
    from ui.i18n import current_lang

    if getattr(sys, "frozen", False):
        exe = sys.executable
        cmd = [exe, "--gui", f"--port={port}", f"--locale={current_lang}"]
        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        exe = sys.executable
        script = os.path.join(get_app_root(), "main.py")
        cmd = [exe, script, "--gui", f"--port={port}", f"--locale={current_lang}"]
        subprocess.Popen(cmd, creationflags=0)


def _run_gui(port: int, locale: str) -> None:
    """GUI subprocess entry point."""
    from ui.webview import GuiWindow

    GuiWindow(port, locale).create_and_block()


def _run_console_mode(config_dir: str, logger: logging.Logger) -> None:
    """Create scheduler and run in console mode (--no-tray).

    No HTTP server, no tray — just the scheduler loop on a background
    thread with the main thread sleeping until KeyboardInterrupt.
    """
    from app.context import get_data_dir
    from app.history_logger import HistoryLogger
    from core.runtime.scheduler import WEScheduler
    from ui.cli_status import CliStatusReporter

    scheduler = WEScheduler(config_dir, HistoryLogger(get_data_dir()))
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


def _run_tray_mode(config_dir: str, logger: logging.Logger, server_port: int = 0) -> None:
    """Create scheduler, start the local frontend API server, and block on
    the system tray icon.

    Error handling: log + native error dialog so the user sees it even
    though there's no console window.
    """
    from app.context import get_data_dir
    from app.history_logger import HistoryLogger
    from core.runtime.scheduler import WEScheduler
    from ui.frontend import FrontendHTTPServer
    from ui.tick_trace_store import TickTraceStore
    from ui.tray import TrayIcon

    scheduler = WEScheduler(config_dir, HistoryLogger(get_data_dir()))
    try:
        scheduler.initialize()
    except Exception as e:
        logger.critical("Failed to initialize scheduler: %s", e)
        TrayIcon.show_startup_error(str(e))
        sys.exit(1)
    scheduler.on_reload_error = lambda exc: TrayIcon.show_reload_error(str(exc))

    tick_store = TickTraceStore()

    scheduler.add_tick_listener(tick_store.update)
    scheduler.start()
    httpd = FrontendHTTPServer(
        tick_store,
        requested_port=server_port,
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
    tray.on_show_gui = lambda: _spawn_gui_subprocess(httpd.port)
    tray.run()


# ── Entry point ─────────────────────────────────────────────────


def main() -> None:
    config_mode = len(sys.argv) > 1 and sys.argv[1] == "config"
    if config_mode:
        _ensure_console_for_config_mode()

    logger = setup_logger()
    logger.info("Context Aware WE Scheduler starting...")

    if config_mode:
        from ui.config_cli import run_config_tools_tui

        config_parser = argparse.ArgumentParser(description="WEScheduler Config Tools")
        config_parser.add_argument(
            "--config",
            default="config",
            help="Path to the configuration directory",
        )
        config_args = config_parser.parse_args(sys.argv[2:])
        config_dir = _resolve_config_path(config_args.config)
        raise SystemExit(run_config_tools_tui(config_dir))

    args = _parse_args()

    if args.gui:
        _run_gui(args.port, args.locale)
        return

    config_dir = _resolve_config_path(args.config)

    if args.no_tray:
        _run_console_mode(config_dir, logger)
    else:
        _run_tray_mode(config_dir, logger, args.server_port)


if __name__ == "__main__":
    main()
