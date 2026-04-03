import pystray
import os
import time
import logging
import threading
import tkinter as tk
from tkinter import ttk
from typing import Optional

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
        self._enable_dpi_awareness()

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

    # ──────────────────────────────────────────────────────────────
    @staticmethod
    def _enable_dpi_awareness():
        """Best-effort HiDPI support on Windows."""
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


# ── System Tray Icon ─────────────────────────────────────────────

class TrayIcon:
    """
    System-tray interface backed by *pystray*.

    **Menu state** (text, visibility) uses pystray callable properties
    — re-evaluated lazily on every menu open.  No rebuild needed.

    **Icon image** is synced via ``_sync_icon()`` (direct call from
    pystray-thread handlers) or ``_schedule_icon_sync(delay)`` (Timer
    for deferred cross-thread scenarios like custom-dialog confirm and
    timed-pause auto-resume).
    """

    def __init__(self, scheduler: WEScheduler):
        self.scheduler = scheduler
        self.icon = None
        self._last_paused_state: Optional[bool] = None
        # Timer for deferred icon sync (auto-resume / cross-thread)
        self._sync_timer: Optional[threading.Timer] = None

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

    def _cancel_sync_timer(self):
        """Cancel any pending icon-sync timer."""
        if self._sync_timer is not None:
            self._sync_timer.cancel()
            self._sync_timer = None

    def _schedule_icon_sync(self, delay: float):
        """
        Schedule a deferred ``_sync_icon()`` call after *delay* seconds.
        Cancels any previously scheduled timer.  Used for:
          - timed pause auto-resume (delay = remaining seconds + buffer)
          - cross-thread callers like the custom-dialog callback (delay ≈ 0)
        """
        self._cancel_sync_timer()
        if delay < 0:
            delay = 0
        self._sync_timer = threading.Timer(delay, self._deferred_sync)
        self._sync_timer.daemon = True
        self._sync_timer.start()

    def _deferred_sync(self):
        """
        Timer callback: sync icon + menu, then retry once if the
        scheduler hasn't caught up with a timed-pause expiry yet.
        """
        self._sync_icon()
        # If a timed pause should have expired but the scheduler loop
        # hasn't called resume() yet (±1 s loop jitter), retry shortly.
        if (self.scheduler.paused
                and self.scheduler.pause_until > 0
                and time.time() >= self.scheduler.pause_until):
            self._schedule_icon_sync(1)

    # ── Menu action handlers ─────────────────────────────────────

    def _on_pause(self, seconds: Optional[int] = None):
        """
        Returns a pystray-compatible handler that pauses for *seconds*.
        ``None`` means indefinite pause.
        """
        def handler(icon, item):
            self.scheduler.pause(seconds)
            # Direct call — we're in pystray's own thread.
            # (pystray's _handler wrapper also calls update_menu()
            #  after us, which is redundant but harmless.)
            self._sync_icon()
            # Schedule icon sync for auto-resume with a 2 s buffer so
            # the Timer fires *after* the scheduler loop has detected
            # the timed-pause expiry and called resume().
            if seconds is not None:
                self._schedule_icon_sync(seconds + 2)
            else:
                self._cancel_sync_timer()
        return handler

    def _on_resume(self, icon, item):
        self.scheduler.resume()
        self._cancel_sync_timer()
        self._sync_icon()

    def _on_custom_pause(self, icon, item):
        """Opens the custom-duration dialog in a dedicated thread."""
        def _show():
            def on_confirm(total_seconds: int):
                self.scheduler.pause(total_seconds)
                # Immediate sync (tiny delay so scheduler state is stable),
                # then schedule a second sync for auto-resume.
                def _immediate_then_schedule():
                    self._sync_icon()
                    self._schedule_icon_sync(total_seconds + 2)
                t_now = threading.Timer(0.1, _immediate_then_schedule)
                t_now.daemon = True
                t_now.start()
            CustomPauseDialog(on_confirm).show()
        threading.Thread(target=_show, daemon=True).start()

    def _on_open_config(self, icon, item):
        self._open_file(self.scheduler.config_path)

    def _on_open_logs(self, icon, item):
        log_path = os.path.join(get_app_root(), "logs", "scheduler.log")
        self._open_file(log_path)

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

        # Format remaining time: e.g. "2d 3h 15m"
        r = int(remaining)
        days, r = divmod(r, 86400)
        hours, r = divmod(r, 3600)
        minutes, _ = divmod(r, 60)
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
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
            pystray.MenuItem(t("pause_indefinitely"), self._on_pause(None)),
            pystray.Menu.SEPARATOR,
        ]
        for key, seconds in PAUSE_PRESETS:
            pause_items.append(
                pystray.MenuItem(t(key), self._on_pause(seconds))
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
        self.icon.run()
