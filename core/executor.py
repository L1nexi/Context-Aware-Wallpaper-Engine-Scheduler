import subprocess
import os
import logging
import psutil
from typing import List

logger = logging.getLogger("WEScheduler.Executor")

class WEExecutor:
    def __init__(self, we_path: str):
        self.we_path = we_path
        if not os.path.exists(self.we_path):
            raise FileNotFoundError(f"Wallpaper Engine executable not found at: {self.we_path}")
        self.process_name = os.path.basename(self.we_path).lower()

    def is_we_running(self) -> bool:
        """Checks if the Wallpaper Engine process is currently running."""
        try:
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] and proc.info['name'].lower() == self.process_name:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
        return False

    def ensure_we_running(self) -> bool:
        """Ensures WE is running, attempts to start it if not."""
        if self.is_we_running():
            return True
        
        logger.warning(f"Wallpaper Engine ({self.process_name}) is not running. Attempting to start...")
        try:
            # Start WE without waiting for it to finish
            subprocess.Popen([self.we_path], 
                             stdout=subprocess.DEVNULL, 
                             stderr=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            logger.info("Wallpaper Engine start command issued.")
            return True
        except Exception as e:
            logger.error(f"Failed to start Wallpaper Engine: {e}")
            return False

    def _run_command(self, args: List[str]) -> None:
        """Runs a command silently, ensuring WE is running first."""
        if not self.ensure_we_running():
            logger.error("Cannot execute command: Wallpaper Engine is not running and failed to start.")
            return

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
            if e.returncode == 5:
                logger.info(f"Wallpaper Engine Error Code 5. This Error seems to affect nothing though."
                             f"Please check if the playlist/profile name exists in WE: {args}")
            else:
                logger.error(f"Error executing command: {e}")

    def open_playlist(self, playlist_name: str) -> None:
        self._run_command(["openPlaylist", "-playlist", playlist_name])

    def next_wallpaper(self) -> None:
        self._run_command(["nextWallpaper"])
