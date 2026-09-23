from __future__ import annotations

import ctypes
import logging
import os
import sys
import webbrowser
from urllib.parse import urlsplit

import psutil

from ui.i18n import t

logger = logging.getLogger("WEScheduler.WebView")

WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1


def _resolve_icon_path() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "AppIcon.ico")
    from app.context import get_app_root

    return os.path.join(get_app_root(), "AppIcon.ico")


def _set_window_icon() -> None:
    import webview

    icon_path = _resolve_icon_path()
    if not os.path.isfile(icon_path):
        logger.warning("Icon not found: %s", icon_path)
        return

    try:
        title = webview.windows[0].title
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if not hwnd:
            logger.warning("FindWindowW returned NULL for title: %r", title)
            return

        hicon = ctypes.windll.user32.LoadImageW(
            0,
            icon_path,
            1,
            0,
            0,
            0x00000010 | 0x00000040,
        )
        if hicon:
            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon)
            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon)
    except Exception:
        logger.exception("Failed to set window icon")


class _WindowAPI:
    def choose_wallpaper_engine(self) -> str | None:
        """Open a native file picker and return the selected executable path."""
        import webview

        if not webview.windows:
            return None
        selected = webview.windows[0].create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            file_types=("Wallpaper Engine executable (*.exe)",),
        )
        return selected[0] if selected else None

    def open_external(self, url: str) -> None:
        """Open one safe HTTP(S) URL in the user's default browser.

        Raises:
            ValueError: If ``url`` is not an absolute HTTP(S) URL.
        """

        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("external URL must be an absolute HTTP(S) URL")
        webbrowser.open_new_tab(url)

    def close(self) -> None:
        import webview

        if webview.windows:
            webview.windows[0].destroy()


class AppWindow:
    def __init__(self, api_port: int, locale: str, *, path: str = "/", title_key: str = "setup_title"):
        self._url = f"http://127.0.0.1:{api_port}{path}?locale={locale}"
        self._title = t(title_key)

    def create_and_block(self) -> None:
        import webview

        webview.create_window(
            title=self._title,
            url=self._url,
            width=1200,
            height=780,
            resizable=True,
            text_select=True,
            js_api=_WindowAPI(),
        )

        webview.start(gui="edgechromium", func=_set_window_icon)


def focus_process_window(process_id: int) -> bool:
    """Restore and focus a visible window owned by a process or its children."""

    if sys.platform != "win32":
        return False

    process_ids = {process_id}
    try:
        process_ids.update(child.pid for child in psutil.Process(process_id).children(recursive=True))
    except psutil.Error:
        pass

    user32 = ctypes.windll.user32
    target: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    @callback_type
    def enum_window(hwnd: int, _lparam: int) -> bool:
        owner_process_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_process_id))
        if owner_process_id.value in process_ids and user32.IsWindowVisible(hwnd):
            target.append(hwnd)
            return False
        return True

    user32.EnumWindows(enum_window, 0)
    if not target:
        return False

    user32.ShowWindow(target[0], 9)  # SW_RESTORE
    return bool(user32.SetForegroundWindow(target[0]))
