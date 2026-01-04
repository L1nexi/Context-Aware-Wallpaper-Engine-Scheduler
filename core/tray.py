import pystray
from PIL import Image, ImageDraw
import os
from core.scheduler import WEScheduler

class TrayIcon:
    def __init__(self, scheduler: WEScheduler):
        self.scheduler = scheduler
        self.icon = None

    def create_image(self, width=64, height=64, color1="blue", color2="white"):
        # Generate a simple icon
        image = Image.new('RGB', (width, height), color1)
        dc = ImageDraw.Draw(image)
        dc.rectangle(
            (width // 4, height // 4, width * 3 // 4, height * 3 // 4),
            fill=color2
        )
        return image

    def _open_file(self, path):
        if os.path.exists(path):
            os.startfile(path)

    def _on_toggle_pause(self, icon, item):
        if self.scheduler.paused:
            self.scheduler.resume()
        else:
            self.scheduler.pause()
        # Refresh menu to update label
        icon.menu = self._build_menu()

    def _on_open_config(self, icon, item):
        self._open_file(self.scheduler.config_path)

    def _on_open_logs(self, icon, item):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
        image = self.create_image()

        self.icon = pystray.Icon(
            "WEScheduler", 
            image, 
            "Context Aware WE Scheduler", 
            menu=self._build_menu() 
        )
        
        self.icon.run()
