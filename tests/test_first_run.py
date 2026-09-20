from __future__ import annotations

from app.first_run import FirstRunCoordinator
from core.runtime.profile_manager import ProfileNotFoundError


class SchedulerWithoutProfile:
    def __init__(self) -> None:
        self.initialize_calls = 0

    def initialize(self) -> bool:
        self.initialize_calls += 1
        if self.initialize_calls == 1:
            raise ProfileNotFoundError("profile not found")
        return True


def test_first_run_starts_scheduler_after_setup_creates_profile():
    coordinator = FirstRunCoordinator(poll_interval=0)
    scheduler = SchedulerWithoutProfile()

    class SetupProcess:
        @staticmethod
        def poll() -> int | None:
            coordinator.notify_profile_created()
            return None

    initialized = coordinator.initialize_scheduler(scheduler, SetupProcess)

    assert initialized is True
    assert scheduler.initialize_calls == 2


def test_first_run_exits_when_setup_closes_before_creating_profile():
    coordinator = FirstRunCoordinator(poll_interval=0)
    scheduler = SchedulerWithoutProfile()

    class SetupProcess:
        @staticmethod
        def poll() -> int | None:
            return 0

    initialized = coordinator.initialize_scheduler(scheduler, SetupProcess)

    assert initialized is False
    assert scheduler.initialize_calls == 1
