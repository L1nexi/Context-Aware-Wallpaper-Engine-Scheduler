import subprocess
import os
import logging
from typing import List

logger = logging.getLogger("WEScheduler.Executor")

class WEExecutor:
    def __init__(self, we_path: str):
        self.we_path = we_path
        if not os.path.exists(self.we_path):
            raise FileNotFoundError(f"Wallpaper Engine executable not found at: {self.we_path}")

    def _run_command(self, args: List[str]) -> None:
        """Runs a command silently."""
        cmd = [self.we_path, "-control"] + args
        try:
            # Use CREATE_NO_WINDOW to avoid popping up cmd windows
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            subprocess.run(cmd, check=True, startupinfo=startupinfo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.debug(f"Executed: {' '.join(cmd)}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error executing command: {e}")

    def open_playlist(self, playlist_name: str) -> None:
        self._run_command(["openPlaylist", "-playlist", playlist_name])

    def next_wallpaper(self) -> None:
        self._run_command(["nextWallpaper"])
