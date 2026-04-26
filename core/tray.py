import pystray
import os
import logging
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from core.scheduler import WEScheduler
from utils.icon_generator import IconGenerator
from utils.app_context import get_app_root
from utils.i18n import t

logger = logging.getLogger("WEScheduler.Tray")

# Preset pause durations: (i18n_key, seconds).
# Keys must exist in utils/i18n.py translation table.
PAUSE_PRESETS = [
    ("pause_30m",  30 * 60),
    ("pause_2h",   2 * 3600),
    ("pause_12h",  12 * 3600),
    ("pause_24h",  24 * 3600),
    ("pause_48h",  48 * 3600),
    ("pause_1w",   7 * 24 * 3600),
]


# ── Custom Pause Dialog ─────────────────────────────────────────

class CustomPauseDialog:
    """
    Modal tkinter dialog for specifying a custom pause duration.

    Provides Day / Hour / Minute spinboxes.  Calls ``on_confirm(seconds)``
    only when the user clicks OK **and** the total duration is > 0.

    Must be shown from a **non-main** thread when the main thread is
    occupied by pystray — tkinter creates its own event loop via
    ``mainloop()``.

    Keyboard shortcuts:
        Enter  — confirm
        Escape — cancel / close
    """

    def __init__(self, on_confirm):
        """
        :param on_confirm: callback(seconds: int) invoked on valid input.
        """
        self._on_confirm = on_confirm

    def show(self):
        """Creates the dialog window and blocks until it is closed."""

        root = tk.Tk()
        root.title(t("dialog_title"))
        root.resizable(False, False)
        root.attributes("-topmost", True)
        # Clicking the X button simply closes the dialog (same as Cancel).
        root.protocol("WM_DELETE_WINDOW", root.destroy)

        frame = ttk.Frame(root, padding=16)
        frame.grid(sticky="nsew")

        # ── Spinbox rows: (i18n_key, max_value) ──
        field_defs = [("days", 365), ("hours", 23), ("minutes", 59)]
        tk_vars = []
        for row, (label_key, max_val) in enumerate(field_defs):
            ttk.Label(frame, text=t(label_key)).grid(
                row=row, column=0, sticky="e", padx=(0, 8), pady=4,
            )
            var = tk.IntVar(value=0)
            spinbox = ttk.Spinbox(
                frame, from_=0, to=max_val, width=6,
                textvariable=var, wrap=False,
            )
            spinbox.grid(row=row, column=1, pady=4)
            tk_vars.append(var)
            # Auto-focus the first spinbox so the user can type immediately.
            if row == 0:
                spinbox.focus_set()

        days_var, hours_var, mins_var = tk_vars

        # ── Helpers ──
        def _total_seconds() -> int:
            try:
                return (days_var.get() * 86400
                        + hours_var.get() * 3600
                        + mins_var.get() * 60)
            except (tk.TclError, ValueError):
                return 0

        def _on_ok(_event=None):
            total = _total_seconds()
            root.destroy()
            if total > 0:
                self._on_confirm(total)

        def _on_cancel(_event=None):
            root.destroy()

        # ── Buttons ──
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(
            row=len(field_defs), column=0, columnspan=2, pady=(12, 0),
        )
        ttk.Button(btn_frame, text=t("ok"), command=_on_ok, width=8).pack(
            side="left", padx=4,
        )
        ttk.Button(btn_frame, text=t("cancel"), command=_on_cancel, width=8).pack(
            side="left", padx=4,
        )

        # ── Keyboard shortcuts ──
        root.bind("<Return>", _on_ok)
        root.bind("<Escape>", _on_cancel)

        # ── Centre on screen ──
        root.update_idletasks()
        w = root.winfo_reqwidth()
        h = root.winfo_reqheight()
        x = (root.winfo_screenwidth() - w) // 2
        y = (root.winfo_screenheight() - h) // 2
        root.geometry(f"+{x}+{y}")

        root.mainloop()


# ── System Tray Icon ─────────────────────────────────────────────

class TrayIcon:
    """
    System-tray interface backed by *pystray*.

    **Menu state** (text, visibility) uses pystray callable properties
    — re-evaluated lazily on every menu open.  No rebuild needed.

    **Icon image** is synced via ``_sync_icon()``:
    - Direct call from pystray-thread menu handlers.
    - Via ``scheduler.on_auto_resume`` hook when a timed pause expires.
    - Via a short Timer for cross-thread callers (custom-dialog confirm).
    """

    def __init__(self, scheduler: WEScheduler):
        self.scheduler = scheduler
        self.icon = None
        self._last_paused_state: Optional[bool] = None
        self.on_show_dashboard: Callable[[], None] | None = None
        # Let the scheduler notify us when a timed pause auto-expires.
        self.scheduler.on_auto_resume = self._sync_icon

    @staticmethod
    def show_startup_error(detail: str) -> None:
        """Show a native error dialog when tray-mode startup fails.

        Only called in tray mode (--no-tray lets the exception surface
        naturally in the console).
        """
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            from tkinter import messagebox
            messagebox.showerror(t("startup_error_title"), t("startup_error_body", detail=detail))
            root.destroy()
        except Exception:
            pass  # tkinter unavailable — error already in log

    # ── Helpers ──────────────────────────────────────────────────

    def _open_file(self, path: str):
        if os.path.exists(path):
            os.startfile(path)

    def _sync_icon(self):
        """
        Syncs the tray icon image **and** menu to the current scheduler
        state.

        pystray's Win32 backend caches the HMENU — callable menu
        properties (text, visible) are only evaluated when the menu is
        *built*, not on each right-click.  Therefore we must call
        ``update_menu()`` explicitly whenever state changes outside of
        a pystray menu-item callback.
        """
        if not self.icon:
            return
        current = self.scheduler.paused
        if current != self._last_paused_state:
            self.icon.icon = IconGenerator.generate(paused=current)
            self._last_paused_state = current
        # Always rebuild the Win32 HMENU so dynamic text / visibility
        # reflects the latest scheduler state (harmless if redundant).
        self.icon.update_menu()

    # ── Menu action handlers ─────────────────────────────────────

    def _on_pause_wrapper(self, seconds: Optional[int] = None):
        """
        Returns a pystray-compatible handler that pauses for *seconds*.
        ``None`` means indefinite pause.
        """
        def handler(icon, item):
            self.scheduler.pause(seconds)
            self._sync_icon()
        return handler

    def _on_resume(self, icon, item):
        self.scheduler.resume()
        self._sync_icon()

    def _on_custom_pause(self, icon, item):
        """Opens the custom-duration dialog in a dedicated thread."""
        def _show():
            def on_confirm(total_seconds: int):
                self.scheduler.pause(total_seconds)
                self._sync_icon()
            CustomPauseDialog(on_confirm).show()
        threading.Thread(target=_show, daemon=True).start()

    def _on_open_config(self, icon, item):
        self._open_file(self.scheduler.config_path)

    def _on_open_logs(self, icon, item):
        log_path = os.path.join(get_app_root(), "logs", "scheduler.log")
        self._open_file(log_path)

    def _on_show_dashboard(self, icon, item):
        self.on_show_dashboard()

    def _on_exit(self, icon, item):
        self.scheduler.stop()
        icon.stop()

    # ── Status formatting ────────────────────────────────────────

    def _get_status_text(self) -> str:
        if not self.scheduler.paused:
            return t("status_running")

        remaining = self.scheduler.get_pause_remaining()
        if remaining is None:
            return t("status_paused")

        # Format remaining time: e.g. "2d 3h 15m" or "45s"
        r = int(remaining)
        days, r = divmod(r, 86400)
        hours, r = divmod(r, 3600)
        minutes, seconds = divmod(r, 60)
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if days == 0 and hours == 0 and minutes == 0:
            parts.append(f"{seconds}s")
        else:
            parts.append(f"{minutes}m")
        return t("status_paused_remaining", remaining=" ".join(parts))

    # ── Menu construction ────────────────────────────────────────

    def _build_menu(self) -> pystray.Menu:
        """
        Builds the context menu **once**.  Dynamic parts (status text,
        Resume visibility) use callables so pystray re-evaluates them
        on every menu open — no rebuild needed.
        """
        # -- Pause submenu: Indefinitely + presets + custom --
        pause_items = [
            pystray.MenuItem(t("pause_indefinitely"), self._on_pause_wrapper(None)),
            pystray.Menu.SEPARATOR,
        ]
        for key, seconds in PAUSE_PRESETS:
            pause_items.append(
                pystray.MenuItem(t(key), self._on_pause_wrapper(seconds))
            )
        pause_items.append(pystray.Menu.SEPARATOR)
        pause_items.append(
            pystray.MenuItem(t("pause_custom"), self._on_custom_pause)
        )

        items = [
            # Status — callable text, re-evaluated on every menu open
            pystray.MenuItem(
                lambda item: self._get_status_text(),
                lambda icon, item: None,
                enabled=False,
            ),
            # Resume — visible only when paused (callable)
            pystray.MenuItem(
                t("resume"), self._on_resume,
                visible=lambda item: self.scheduler.paused,
            ),
            # Pause submenu
            pystray.MenuItem(t("pause"), pystray.Menu(*pause_items)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                t("dashboard_show"), self._on_show_dashboard,
                visible=lambda item: self.on_show_dashboard is not None,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(t("open_config"), self._on_open_config),
            pystray.MenuItem(t("open_logs"), self._on_open_logs),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(t("exit"), self._on_exit),
        ]

        return pystray.Menu(*items)

    # ── Entry point ──────────────────────────────────────────────

    def run(self):
        """Starts the tray icon. Blocks the calling thread."""
        self._last_paused_state = self.scheduler.paused

        self.icon = pystray.Icon(
            "WEScheduler",
            IconGenerator.generate(paused=self.scheduler.paused),
            "Context Aware WE Scheduler",
            menu=self._build_menu(),
        )
        self._patch_menu_refresh()
        self.icon.run()

    def _patch_menu_refresh(self):
        """
        Monkey-patches pystray's Win32 WM_NOTIFY handler so that
        ``_update_menu()`` is called right before every right-click
        popup.  This ensures dynamic menu text (e.g. remaining pause
        time) is always freshly evaluated.

        Implementation: replaces the WM_NOTIFY entry in
        ``icon._message_handlers`` — a plain dict keyed by Win32
        message numbers that the WndProc dispatcher reads at runtime
        (_win32.py line 412).  Wrapped in try/except so a future
        pystray upgrade that changes internals degrades gracefully.
        """
        try:
            from pystray._util import win32 as _w32
            _original = self.icon._message_handlers[_w32.WM_NOTIFY]

            def _notify_with_refresh(wparam, lparam):
                if self.icon._menu_handle and lparam == _w32.WM_RBUTTONUP:
                    self.icon._update_menu()
                _original(wparam, lparam)

            self.icon._message_handlers[_w32.WM_NOTIFY] = _notify_with_refresh
        except Exception:
            logger.debug("Menu-refresh patch not applied (pystray internals may have changed)")
