from __future__ import annotations

import logging
import os
import subprocess

logger = logging.getLogger("WEScheduler.Executor")

WE_CONTROL_TIMEOUT_SECONDS = 3.0
KEEP_ALIVE_INTERVAL = 5


class WEExecutor:
    def __init__(self, we_path: str):
        """Create an executor for the given Wallpaper Engine executable.

        Raises:
            ValueError: If *we_path* is empty or does not point to an existing file.
        """
        if not we_path or not os.path.isfile(we_path):
            raise ValueError("WEExecutor requires a resolved Wallpaper Engine executable path")
        self.we_path = we_path
        self._keep_alive_tick = 0

    def keep_alive(self) -> None:
        self._keep_alive_tick += 1
        if self._keep_alive_tick % KEEP_ALIVE_INTERVAL != 0:
            return
        self._run_command(["getWallpaper"])

    def _run_command(self, args: list[str]) -> bool:
        """-control 参数默认会先拉起 WE，随后执行命令。
        拉起时间小于 0.5s，这使得我们在除了在 WE 安全恢复后弹窗以外的场景无需做复杂的 WE 保活
        """
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
            logger.warning(
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
