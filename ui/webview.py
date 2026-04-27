"""
Dashboard window process entry point.

Launched as a subprocess by the tray host.  Thin wrapper around pywebview
that creates a single window, blocks until the user closes it, then exits.
No show/hide tricks — window close = process exit.
"""

from __future__ import annotations

import logging
from utils.i18n import t

logger = logging.getLogger("WEScheduler.WebView")


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
        )
        webview.start(gui="edgechromium")
        # Returns when window is closed — process exits
