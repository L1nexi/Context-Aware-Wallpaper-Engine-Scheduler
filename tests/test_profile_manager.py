from __future__ import annotations

import getpass
import json
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import pytest

from configurations.profile import Profile
from configurations.profile_store import ProfileStore
from core.models.scene import SceneId
from core.runtime.engine import Engine
from core.runtime.profile_manager import (
    ProfileAlreadyExists,
    ProfileApplyFailed,
    ProfileApplyTimeout,
    ProfileApplyUnavailable,
    ProfileManager,
    ProfileNotFoundError,
)


@pytest.fixture(autouse=True)
def weather_api(monkeypatch):
    class Response:
        ok = True

        @staticmethod
        def json():
            return {
                "weather": [{"id": 800, "main": "Clear"}],
                "sys": {"sunrise": 1, "sunset": 2},
            }

    monkeypatch.setattr("core.sensors.weather.requests.get", lambda *_args, **_kwargs: Response())


def _wallpaper_engine_path(tmp_path: Path, *playlists: tuple[str, int]) -> str:
    executable = tmp_path / "wallpaper64.exe"
    executable.write_text("fake", encoding="utf-8")
    config = {
        getpass.getuser(): {
            "general": {"playlists": [{"name": name, "items": [f"item-{index}" for index in range(count)]} for name, count in playlists]}
        }
    }
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return str(executable)


def _profile(wallpaper_engine_path: str, *, playlist: str = "WORK") -> Profile:
    return Profile.model_validate(
        {
            "wallpaper_engine_path": wallpaper_engine_path,
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


def _initialized_manager(tmp_path: Path) -> tuple[ProfileManager, Engine, Profile]:
    executable = _wallpaper_engine_path(tmp_path, ("WORK", 7), ("NEW", 3))
    current = _profile(executable)
    ProfileStore(str(tmp_path)).commit(current)
    manager = ProfileManager(str(tmp_path))
    engine = Engine.from_config(manager.load_initial_config())
    manager.accept_updates()
    return manager, engine, current


def _process_until_done(
    manager: ProfileManager,
    engine: Engine,
    future: Future[Profile],
) -> Profile:
    deadline = time.monotonic() + 1
    while not future.done():
        manager.process_pending(engine)
        if time.monotonic() >= deadline:
            raise AssertionError("Profile application did not finish")
        time.sleep(0.005)
    return future.result()


def test_profile_manager_initializes_from_persisted_profile(tmp_path: Path):
    executable = _wallpaper_engine_path(tmp_path, ("WORK", 7))
    profile = _profile(executable)
    ProfileStore(str(tmp_path)).commit(profile)
    manager = ProfileManager(str(tmp_path))

    config = manager.load_initial_config()

    assert config.scenes[SceneId.DAY_WORK].item_count == 7
    assert manager.get_profile() == profile


def test_profile_manager_missing_profile_is_an_explicit_startup_state(tmp_path: Path):
    manager = ProfileManager(str(tmp_path))

    with pytest.raises(ProfileNotFoundError):
        manager.load_initial_config()


def test_create_initial_profile_validates_persists_and_publishes(tmp_path: Path):
    executable = _wallpaper_engine_path(tmp_path, ("WORK", 7))
    draft = _profile(executable)
    manager = ProfileManager(str(tmp_path))

    committed = manager.create_initial_profile(draft)

    assert committed == draft
    assert manager.get_profile() == draft
    assert manager.load_initial_config().scenes[SceneId.DAY_WORK].item_count == 7


def test_create_initial_profile_rejects_existing_persisted_profile(tmp_path: Path):
    executable = _wallpaper_engine_path(tmp_path, ("WORK", 1), ("NEW", 2))
    current = _profile(executable)
    replacement = _profile(executable, playlist="NEW")
    ProfileStore(str(tmp_path)).commit(current)
    manager = ProfileManager(str(tmp_path))

    with pytest.raises(ProfileAlreadyExists):
        manager.create_initial_profile(replacement)


def test_create_initial_profile_compile_failure_does_not_persist(tmp_path: Path):
    manager = ProfileManager(str(tmp_path))
    draft = _profile(r"Z:\missing\wallpaper64.exe")

    with pytest.raises(ProfileApplyFailed, match="wallpaper_engine_config_not_found") as exc_info:
        manager.create_initial_profile(draft)

    assert exc_info.value.stage == "compile"


def test_profile_application_is_committed_at_the_scheduler_safe_point(tmp_path: Path):
    manager, engine, current = _initialized_manager(tmp_path)
    draft = _profile(current.wallpaper_engine_path, playlist="NEW")

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(manager.apply_profile, draft, timeout=1)
        assert ProfileStore(str(tmp_path)).load() == current

        committed = _process_until_done(manager, engine, pending)

    assert committed == draft
    assert manager.get_profile() == draft
    assert ProfileStore(str(tmp_path)).load() == draft
    assert set(engine.config.scenes) == {SceneId.DAY_WORK}
    assert engine.config.scenes[SceneId.DAY_WORK].playlist == "NEW"


def test_timed_out_profile_application_does_not_change_committed_state(tmp_path: Path):
    manager, engine, current = _initialized_manager(tmp_path)
    draft = _profile(current.wallpaper_engine_path, playlist="NEW")

    with pytest.raises(ProfileApplyTimeout):
        manager.apply_profile(draft, timeout=0)

    manager.process_pending(engine)

    assert manager.get_profile() == current
    assert ProfileStore(str(tmp_path)).load() == current
    assert set(engine.config.scenes) == {SceneId.DAY_WORK}
    assert engine.config.scenes[SceneId.DAY_WORK].playlist == "WORK"


def test_profile_application_is_unavailable_before_startup(tmp_path: Path):
    executable = _wallpaper_engine_path(tmp_path, ("WORK", 1))
    manager = ProfileManager(str(tmp_path))

    with pytest.raises(ProfileApplyUnavailable):
        manager.apply_profile(_profile(executable), timeout=1)
