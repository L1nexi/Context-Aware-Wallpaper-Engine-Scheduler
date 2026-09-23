from __future__ import annotations

import logging
import queue
import threading
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Literal

from configurations.profile import Profile
from configurations.profile_compiler import ProfileCompiler
from configurations.profile_store import ProfileStore
from configurations.runtime_models import SchedulerConfig
from core.runtime.engine import Engine
from core.runtime.we_config import WEConfigProber

logger = logging.getLogger("WEScheduler.Profile")


class ProfileNotFoundError(RuntimeError):
    """Raised when no committed Profile exists at startup."""


class ProfileAlreadyExists(RuntimeError):
    """Raised when first-run creation targets an existing Profile."""


class ProfileApplyUnavailable(RuntimeError):
    """Raised when Profile updates are not being accepted."""


class ProfileApplyTimeout(TimeoutError):
    """Raised when a queued Profile update does not finish in time."""


class ProfileApplyFailed(RuntimeError):
    """Raised when a named Profile application stage fails."""

    def __init__(
        self,
        stage: Literal["compile", "prepare", "persist"],
        cause: Exception,
    ):
        self.stage = stage
        self.cause = cause
        super().__init__(str(cause))


@dataclass(frozen=True)
class _ApplyProfileCommand:
    profile: Profile
    future: Future[Profile]


class ProfileManager:
    """Own Profile persistence, compilation, and serialized application."""

    def __init__(self, config_dir: str):
        self._store = ProfileStore(config_dir)
        self._profile: Profile | None = None
        self._commands: queue.Queue[_ApplyProfileCommand] = queue.Queue()
        self._accepting_lock = threading.Lock()
        self._accepting_updates = False
        self._profile_lock = threading.Lock()
        self._creation_lock = threading.Lock()

    def load_initial_profile(self) -> None:
        """Load and publish the committed Profile before application startup.

        Raises:
            ProfileNotFoundError: If no committed Profile exists.
            ProfileStoreError: If the committed Profile cannot be read.
        """

        profile = self._store.load()
        if profile is None:
            raise ProfileNotFoundError(f"Profile not found at: {self._store.path}")

        with self._profile_lock:
            self._profile = profile

    def compile_initial_config(self) -> SchedulerConfig:
        """Compile the published Profile into the initial runtime config.

        Raises:
            ProfileNotFoundError: If no Profile has been published.
            Exception: If compilation fails.
        """

        profile = self.get_profile()
        if profile is None:
            raise ProfileNotFoundError("profile is not loaded")
        return self._compile(profile)

    def accept_updates(self) -> None:
        """Allow Profile updates after scheduler initialization.

        Raises:
            ProfileApplyUnavailable: If the Profile was not initialized.
        """

        with self._profile_lock:
            if self._profile is None:
                raise ProfileApplyUnavailable("profile is not initialized")
        with self._accepting_lock:
            self._accepting_updates = True

    def reject_updates(self) -> None:
        """Reject new Profile updates and fail commands not yet processed."""

        with self._accepting_lock:
            self._accepting_updates = False
            while True:
                try:
                    command = self._commands.get_nowait()
                except queue.Empty:
                    break
                if command.future.set_running_or_notify_cancel():
                    command.future.set_exception(ProfileApplyUnavailable("profile manager is stopping"))

    def get_profile(self) -> Profile | None:
        with self._profile_lock:
            if self._profile is None:
                return None
            return self._profile.model_copy(deep=True)

    def has_committed_profile(self) -> bool:
        """Check loaded and persisted initial Profile state.

        Raises:
            ProfileStoreError: If the persisted Profile cannot be read.
        """
        with self._creation_lock:
            return self._has_committed_profile()

    def _has_committed_profile(self) -> bool:
        with self._profile_lock:
            if self._profile is not None:
                return True
        return self._store.load() is not None

    def create_initial_profile(self, profile: Profile) -> Profile:
        """Validate and persist the first Profile before Scheduler startup.

        Raises:
            ProfileAlreadyExists: If a committed or loaded Profile already
                exists.
            ProfileApplyFailed: If compilation, runtime preparation, or
                persistence fails.
            ProfileStoreError: If an existing Profile cannot be read.
        """

        with self._creation_lock:
            if self._has_committed_profile():
                raise ProfileAlreadyExists("profile is already committed")

            try:
                config = self._compile(profile)
            except Exception as exc:
                raise ProfileApplyFailed("compile", exc) from exc

            try:
                Engine.validate_config(config)
            except Exception as exc:
                raise ProfileApplyFailed("prepare", exc) from exc

            try:
                committed = self._store.commit(profile)
            except Exception as exc:
                raise ProfileApplyFailed("persist", exc) from exc

            with self._profile_lock:
                self._profile = committed
            logger.info("Created initial Profile.")
            return committed.model_copy(deep=True)

    def apply_profile(self, profile: Profile, *, timeout: float) -> Profile:
        """Queue a Profile update and wait briefly for its result.

        Raises:
            ProfileApplyUnavailable: If Profile updates are not being accepted.
            ProfileApplyTimeout: If the command does not finish within
                ``timeout``.
            ProfileApplyFailed: If compilation, preparation, or persistence
                fails.
        """

        future: Future[Profile] = Future()
        with self._accepting_lock:
            if not self._accepting_updates:
                raise ProfileApplyUnavailable("profile updates are not being accepted")
            self._commands.put(_ApplyProfileCommand(profile=profile, future=future))

        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            raise ProfileApplyTimeout("profile apply timed out") from exc

    def process_pending(self, engine: Engine) -> None:
        """Apply queued Profile updates to an Engine at a scheduler safe point."""

        while True:
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                return

            if not command.future.set_running_or_notify_cancel():
                continue

            try:
                committed = self._apply(command.profile, engine)
            except Exception as exc:
                command.future.set_exception(exc)
            else:
                command.future.set_result(committed)

    def _compile(self, profile: Profile) -> SchedulerConfig:
        """Compile a Profile with current Wallpaper Engine playlist counts."""

        item_counts = WEConfigProber(profile.wallpaper_engine_path).probe_item_counts()
        return ProfileCompiler.compile(profile, playlist_item_counts=item_counts)

    def _apply(self, profile: Profile, engine: Engine) -> Profile:
        """Prepare, persist, and install one Profile update.

        Raises:
            ProfileApplyFailed: If compilation, preparation, or persistence
                fails.
        """

        try:
            config = self._compile(profile)
        except Exception as exc:
            raise ProfileApplyFailed("compile", exc) from exc

        try:
            replacement = engine.prepare_replacement(config)
        except Exception as exc:
            raise ProfileApplyFailed("prepare", exc) from exc

        try:
            committed = self._store.commit(profile)
        except Exception as exc:
            raise ProfileApplyFailed("persist", exc) from exc

        engine.install_replacement(replacement)
        with self._profile_lock:
            self._profile = committed
        logger.info("Applied Profile update.")
        return committed.model_copy(deep=True)
