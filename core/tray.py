import pystray
import os
import threading
import tkinter as tk
from tkinter import ttk
from core.scheduler import WEScheduler
from utils.icon_generator import IconGenerator

from utils.app_context import get_app_root

# Preset pause durations: (label, seconds)
PAUSE_PRESETS = [
    ("30 Minutes", 30 * 60),
    ("2 Hours", 2 * 3600),
    ("12 Hours", 12 * 3600),
    ("24 Hours", 24 * 3600),
    ("48 Hours", 48 * 3600),
    ("1 Week", 7 * 24 * 3600),
]


class CustomPauseDialog:
    """A simple tkinter dialog for entering a custom pause duration."""

    def __init__(self, on_confirm):
        self._on_confirm = on_confirm
        self.result_seconds = 0

    def show(self):
        root = tk.Tk()
        root.title("Custom Pause Duration")
        root.resizable(False, False)
        root.attributes("-topmost", True)

        frame = ttk.Frame(root, padding=16)
        frame.grid()

        ttk.Label(frame, text="Days:").grid(row=0, column=0, sticky="e", padx=(0, 4))
        days_var = tk.IntVar(value=0)
        days_spin = ttk.Spinbox(frame, from_=0, to=365, width=6, textvariable=days_var)
        days_spin.grid(row=0, column=1, pady=4)

        ttk.Label(frame, text="Hours:").grid(row=1, column=0, sticky="e", padx=(0, 4))
        hours_var = tk.IntVar(value=0)
        hours_spin = ttk.Spinbox(frame, from_=0, to=23, width=6, textvariable=hours_var)
        hours_spin.grid(row=1, column=1, pady=4)

        ttk.Label(frame, text="Minutes:").grid(row=2, column=0, sticky="e", padx=(0, 4))
        mins_var = tk.IntVar(value=0)
        mins_spin = ttk.Spinbox(frame, from_=0, to=59, width=6, textvariable=mins_var)
        mins_spin.grid(row=2, column=1, pady=4)

        def on_ok():
            try:
                total = days_var.get() * 86400 + hours_var.get() * 3600 + mins_var.get() * 60
            except (tk.TclError, ValueError):
                total = 0
            root.destroy()
            if total > 0:
                self._on_confirm(total)

        def on_cancel():
            root.destroy()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btn_frame, text="OK", command=on_ok, width=8).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Cancel", command=on_cancel, width=8).pack(side="left", padx=4)

        # Center on screen
        root.update_idletasks()
        w, h = root.winfo_width(), root.winfo_height()
        x = (root.winfo_screenwidth() - w) // 2
        y = (root.winfo_screenheight() - h) // 2
        root.geometry(f"+{x}+{y}")

        root.mainloop()


class TrayIcon:
    def __init__(self, scheduler: WEScheduler):
        self.scheduler = scheduler
        self.icon = None

    def _open_file(self, path):
        if os.path.exists(path):
            os.startfile(path)

    def _refresh_icon(self):
        """Refreshes icon image and menu to reflect current state."""
        if self.icon:
            self.icon.icon = IconGenerator.generate(paused=self.scheduler.paused)
            self.icon.menu = self._build_menu()

    def _on_toggle_pause(self, icon, item):
        if self.scheduler.paused:
            self.scheduler.resume()
        else:
            self.scheduler.pause()
        self._refresh_icon()

    def _on_pause_for(self, seconds):
        """Pauses the scheduler for the given number of seconds."""
        def handler(icon, item):
            self.scheduler.pause_for(seconds)
            self._refresh_icon()
        return handler

    def _on_custom_pause(self, icon, item):
        """Opens a dialog on a separate thread so the tray stays responsive."""
        def _show_dialog():
            def on_confirm(total_seconds):
                self.scheduler.pause_for(total_seconds)
                self._refresh_icon()
            dialog = CustomPauseDialog(on_confirm)
            dialog.show()
        threading.Thread(target=_show_dialog, daemon=True).start()

    def _on_open_config(self, icon, item):
        self._open_file(self.scheduler.config_path)

    def _on_open_logs(self, icon, item):
        project_root = get_app_root()
        log_path = os.path.join(project_root, "logs", "scheduler.log")
        self._open_file(log_path)

    def _on_exit(self, icon, item):
        self.scheduler.stop()
        icon.stop()

    def _get_status_text(self) -> str:
        if not self.scheduler.paused:
            return "Status: Running"
        remaining = self.scheduler.get_pause_remaining()
        if remaining is None:
            return "Status: Paused"
        # Format remaining time
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
        return f"Status: Paused ({' '.join(parts)} left)"

    def _build_menu(self):
        # Build "Pause For..." submenu with presets and custom option
        pause_for_items = [
            pystray.MenuItem(label, self._on_pause_for(seconds))
            for label, seconds in PAUSE_PRESETS
        ]
        pause_for_items.append(pystray.Menu.SEPARATOR)
        pause_for_items.append(pystray.MenuItem("Custom...", self._on_custom_pause))
        pause_for_submenu = pystray.Menu(*pause_for_items)

        return pystray.Menu(
            pystray.MenuItem(
                self._get_status_text(),
                lambda i, it: None,
                enabled=False
            ),
            pystray.MenuItem(
                "Resume" if self.scheduler.paused else "Pause",
                self._on_toggle_pause
            ),
            pystray.MenuItem("Pause For...", pause_for_submenu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Config", self._on_open_config),
            pystray.MenuItem("Open Logs", self._on_open_logs),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._on_exit)
        )

    def run(self):
        image = IconGenerator.generate(paused=self.scheduler.paused)

        self.icon = pystray.Icon(
            "WEScheduler", 
            image, 
            "Context Aware WE Scheduler", 
            menu=self._build_menu() 
        )
        
        self.icon.run()
