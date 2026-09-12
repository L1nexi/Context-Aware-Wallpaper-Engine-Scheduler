from __future__ import annotations

import json
import os
import tempfile

from pydantic import ValidationError

from configurations.profile import Profile

PROFILE_FILE_NAME = "profile.json"


class ProfileStoreError(RuntimeError):
    """Raised when the persisted profile cannot be read or replaced."""


class ProfileStore:
    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.path = os.path.join(config_dir, PROFILE_FILE_NAME)

    def load(self) -> Profile | None:
        """Load the committed profile, returning ``None`` when it does not exist.

        Raises:
            ProfileStoreError: If the file cannot be read or does not contain a
                valid Profile.
        """

        try:
            with open(self.path, encoding="utf-8") as profile_file:
                payload = profile_file.read()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ProfileStoreError(f"profile_read_failed: {exc}") from exc

        try:
            return Profile.model_validate_json(payload)
        except ValidationError as exc:
            raise ProfileStoreError(f"profile_invalid: {exc}") from exc

    def commit(self, profile: Profile) -> Profile:
        """Atomically persist a complete Profile snapshot.

        Raises:
            ProfileStoreError: If the replacement cannot be written atomically.
        """

        committed = profile.model_copy(deep=True)
        self._replace(committed)
        return committed

    def _replace(self, profile: Profile) -> None:
        """Atomically replace the profile file.

        Raises:
            ProfileStoreError: If the temporary file or atomic replacement
                cannot be written.
        """

        temporary_path: str | None = None
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            descriptor, temporary_path = tempfile.mkstemp(
                dir=self.config_dir,
                prefix=".profile-",
                suffix=".tmp",
                text=True,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as temporary_file:
                json.dump(
                    profile.model_dump(mode="json"),
                    temporary_file,
                    ensure_ascii=False,
                    indent=2,
                )
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self.path)
        except OSError as exc:
            raise ProfileStoreError(f"profile_write_failed: {exc}") from exc
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
