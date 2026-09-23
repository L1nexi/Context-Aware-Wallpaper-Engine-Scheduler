from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable

logger = logging.getLogger("WEScheduler.SettingsWindow")


class SettingsWindowController:
    """Own the settings window subprocess and its single-window policy."""

    def __init__(
        self,
        spawn: Callable[[], subprocess.Popen[bytes]],
        focus: Callable[[int], bool],
    ):
        self._spawn = spawn
        self._focus = focus
        self._process: subprocess.Popen[bytes] | None = None

    def show(self) -> None:
        if self._process is not None and self._process.poll() is None:
            if not self._focus(self._process.pid):
                logger.warning("Failed to focus settings window process %d", self._process.pid)
            return
        self._process = self._spawn()
