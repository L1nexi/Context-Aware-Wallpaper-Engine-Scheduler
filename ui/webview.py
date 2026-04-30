"""
Dashboard window process entry point.

Launched as a subprocess by the tray host.  Thin wrapper around pywebview
that creates a single window, blocks until the user closes it, then exits.
No show/hide tricks — window close = process exit.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import time

from utils.i18n import t

logger = logging.getLogger("WEScheduler.WebView")

WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1


def _resolve_icon_path() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, 'AppIcon.ico')
    from utils.app_context import get_app_root
    return os.path.join(get_app_root(), 'AppIcon.ico')


def _set_window_icon() -> None:
    """Poll for the native window handle and set its icon via Win32 API."""
    import webview

    icon_path = _resolve_icon_path()
    if not os.path.isfile(icon_path):
        logger.warning("Icon not found: %s", icon_path)
        return

    # Poll until the window is created and has a native handle
    for _ in range(50):  # up to 5 seconds
        time.sleep(0.1)
        try:
            if webview.windows:
                hwnd = webview.windows[0].native.Handle
                if hwnd:
                    hicon = ctypes.windll.user32.LoadImageW(
                        0, icon_path, 1, 0, 0, 0x00000010,
                    )
                    if hicon:
                        ctypes.windll.user32.SendMessageW(
                            hwnd, WM_SETICON, ICON_BIG, hicon,
                        )
                        ctypes.windll.user32.SendMessageW(
                            hwnd, WM_SETICON, ICON_SMALL, hicon,
                        )
                    return
        except Exception:
            pass
    logger.warning("Could not set window icon — timed out")


class _DashboardAPI:
    """JS-accessible API exposed via pywebview js_api bridge."""

    def close(self) -> None:
        """Called from JS via window.pywebview.api.close()"""
        import webview
        if webview.windows:
            webview.windows[0].destroy()


class DashboardWindow:
    """Creates a pywebview window loading the dashboard SPA from the
    in-process HTTP server, then blocks until the window is closed."""

    def __init__(self, api_port: int, locale: str):
        self._url = f"http://127.0.0.1:{api_port}?locale={locale}"

    def create_and_block(self) -> None:
        import webview

        webview.create_window(
            title=t("dashboard_title"),
            url=self._url,
            width=900,
            height=650,
            resizable=True,
            text_select=True,
            js_api=_DashboardAPI(),
        )

        threading.Thread(target=_set_window_icon, daemon=True).start()
        webview.start(gui="edgechromium")
        # Returns when window is closed — process exits
