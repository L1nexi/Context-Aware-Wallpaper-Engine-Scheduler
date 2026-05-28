import logging
import os
import subprocess

import psutil

logger = logging.getLogger("WEScheduler.Executor")

WE_CONTROL_TIMEOUT_SECONDS = 3.0


class WEExecutor:
    def __init__(self, we_path: str):
        if not we_path or not os.path.isfile(we_path):
            raise ValueError("WEExecutor requires a resolved Wallpaper Engine executable path")
        self.we_path = we_path
        self.process_name = os.path.basename(self.we_path).lower()

    def is_we_running(self) -> bool:
        try:
            for proc in psutil.process_iter(["name"]):
                if proc.info["name"] and proc.info["name"].lower() == self.process_name:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
        return False

    def request_we_start(self) -> bool:
        try:
            subprocess.Popen(
                [self.we_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            logger.info("Wallpaper Engine start command issued.")
            return True
        except Exception as e:
            logger.error(f"Failed to start Wallpaper Engine: {e}")
            return False

    def _run_command(self, args: list[str]) -> bool:
        """Runs a command silently when WE is already ready for control."""
        if not self.is_we_running():
            logger.warning(
                "Command %s skipped as Wallpaper Engine is not running. Requesting restart command.",
                args,
            )
            self.request_we_start()
            return False

        cmd = [self.we_path, "-control"] + args
        try:
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            subprocess.run(
                cmd,
                check=True,
                timeout=WE_CONTROL_TIMEOUT_SECONDS,
                startupinfo=startupinfo,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.debug(f"Executed: {' '.join(cmd)}")
            return True
        except subprocess.TimeoutExpired:
            logger.error(
                "WE control command timed out after %.1fs: %s",
                WE_CONTROL_TIMEOUT_SECONDS,
                args,
            )
        except subprocess.CalledProcessError as e:
            if e.returncode == 5:
                logger.warning(f"WE Error 5 (Likely Encoding Issue). Try renaming playlist '{args[-1]}' to English. Command: {args}")
            else:
                logger.error(f"Error executing command: {e}")
        except Exception as e:
            logger.error(f"Unexpected error executing command: {e}")
        return False

    def open_playlist(self, playlist_name: str) -> bool:
        return self._run_command(["openPlaylist", "-playlist", playlist_name])

    def next_wallpaper(self) -> bool:
        return self._run_command(["nextWallpaper"])
