from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Protocol

from core.runtime.profile_manager import ProfileNotFoundError


class InitializableScheduler(Protocol):
    def initialize(self) -> bool: ...


class SetupProcess(Protocol):
    def poll(self) -> int | None: ...


class FirstRunCoordinator:
    """Coordinate Scheduler initialization with the first-run setup window."""

    def __init__(self, *, poll_interval: float = 0.1) -> None:
        self._poll_interval = poll_interval
        self._profile_created = threading.Event()

    def notify_profile_created(self) -> None:
        self._profile_created.set()

    def initialize_scheduler(
        self,
        scheduler: InitializableScheduler,
        launch_setup: Callable[[], SetupProcess],
    ) -> bool:
        """Initialize immediately or wait for first-run setup to create a Profile.

        Returns ``False`` when the user closes setup before creating a Profile.

        Raises:
            Exception: If Scheduler initialization or setup launch fails for a
                reason other than a missing initial Profile.
        """

        try:
            scheduler.initialize()
            return True
        except ProfileNotFoundError:
            setup_process = launch_setup()

        while not self._profile_created.wait(self._poll_interval):
            if setup_process.poll() is not None:
                return False

        scheduler.initialize()
        return True
