from __future__ import annotations

import json
from unittest import mock

import pytest

from configurations.profile import Profile
from configurations.profile_store import (
    PROFILE_FILE_NAME,
    ProfileStore,
    ProfileStoreError,
)


def _profile(*, playlist: str = "WORK") -> Profile:
    return Profile.model_validate(
        {
            "wallpaper_engine_path": r"C:\Wallpaper Engine\wallpaper64.exe",
            "weather": {
                "api_key": "test-key",
                "location": {
                    "name": "上海",
                    "latitude": 31.2304,
                    "longitude": 121.4737,
                },
            },
            "scenes": {"day_work": playlist},
        }
    )


def test_profile_store_missing_file_returns_none(tmp_path):
    store = ProfileStore(str(tmp_path))

    assert store.load() is None


def test_profile_store_commit_round_trips_without_revision(tmp_path):
    store = ProfileStore(str(tmp_path))

    committed = store.commit(_profile())

    assert store.load() == committed
    payload = json.loads((tmp_path / PROFILE_FILE_NAME).read_text(encoding="utf-8"))
    assert "revision" not in payload
    assert payload["scenes"] == {"day_work": "WORK"}


def test_profile_store_commit_replaces_previous_profile(tmp_path):
    store = ProfileStore(str(tmp_path))

    store.commit(_profile())
    committed = store.commit(_profile(playlist="NEW"))

    assert store.load() == committed
    assert committed.scenes == {"day_work": "NEW"}


def test_profile_store_invalid_json_is_an_explicit_read_error(tmp_path):
    (tmp_path / PROFILE_FILE_NAME).write_text("{invalid", encoding="utf-8")
    store = ProfileStore(str(tmp_path))

    with pytest.raises(ProfileStoreError, match="profile_invalid"):
        store.load()


def test_profile_store_failed_replace_preserves_previous_profile(tmp_path):
    store = ProfileStore(str(tmp_path))
    current = store.commit(_profile())

    with mock.patch("configurations.profile_store.os.replace", side_effect=OSError("busy")):
        with pytest.raises(ProfileStoreError, match="profile_write_failed"):
            store.commit(_profile(playlist="NEW"))

    assert store.load() == current
