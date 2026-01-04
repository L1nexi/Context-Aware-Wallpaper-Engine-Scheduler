import pystray
import os
from core.scheduler import WEScheduler
from utils.icon_generator import IconGenerator

from utils.app_context import get_app_root

class TrayIcon:
    def __init__(self, scheduler: WEScheduler):
        self.scheduler = scheduler
        self.icon = None

    def _open_file(self, path):
        if os.path.exists(path):
            os.startfile(path)

    def _on_toggle_pause(self, icon, item):
        if self.scheduler.paused:
            self.scheduler.resume()
        else:
            self.scheduler.pause()
        
        # Update Icon Image
        icon.icon = IconGenerator.generate(paused=self.scheduler.paused)
        # Refresh menu to update label
        icon.menu = self._build_menu()

    def _on_open_config(self, icon, item):
        self._open_file(self.scheduler.config_path)

    def _on_open_logs(self, icon, item):
        project_root = get_app_root()
        log_path = os.path.join(project_root, "logs", "scheduler.log")
        self._open_file(log_path)

    def _on_exit(self, icon, item):
        self.scheduler.stop()
        icon.stop()

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(
                f"Status: {'Paused' if self.scheduler.paused else 'Running'}",
                lambda i, it: None,
                enabled=False
            ),
            pystray.MenuItem(
                "Resume" if self.scheduler.paused else "Pause",
                self._on_toggle_pause
            ),
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
