from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from core.runtime.profile_manager import ProfileManager, ProfileNotFoundError


class SetupProcess(Protocol):
    def wait(self) -> int: ...


def ensure_initial_profile(
    profile_manager: ProfileManager,
    launch_setup: Callable[[], SetupProcess],
) -> bool:
    """Ensure an initial Profile exists, opening setup when necessary.

    Returns ``False`` when setup exits before creating a Profile.

    Raises:
        Exception: If Profile loading or setup launch fails.
    """

    try:
        profile_manager.load_initial_profile()
        return True
    except ProfileNotFoundError:
        setup_process = launch_setup()

    setup_process.wait()

    try:
        profile_manager.load_initial_profile()
    except ProfileNotFoundError:
        return False
    return True
