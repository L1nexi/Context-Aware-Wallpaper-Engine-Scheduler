from __future__ import annotations

import getpass
import json
from pathlib import Path

from app.startup import ensure_initial_profile
from configurations.profile import Profile
from core.models.scene import SceneId
from core.runtime.profile_manager import ProfileManager


def _profile(tmp_path: Path) -> Profile:
    executable = tmp_path / "wallpaper64.exe"
    executable.write_text("fake", encoding="utf-8")
    config = {
        getpass.getuser(): {
            "general": {
                "playlists": [
                    {"name": "WORK", "items": ["item-1", "item-2"]},
                ]
            }
        }
    }
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return Profile.model_validate(
        {
            "wallpaper_engine_path": str(executable),
            "weather": {
                "api_key": "test-key",
                "location": {
                    "name": "上海",
                    "latitude": 31.2304,
                    "longitude": 121.4737,
                },
            },
            "scenes": {"day_work": "WORK"},
        }
    )


def test_startup_accepts_profile_when_setup_exits_after_creation(tmp_path: Path):
    manager = ProfileManager(str(tmp_path / "profile"))
    draft = _profile(tmp_path)

    class SetupProcess:
        @staticmethod
        def wait() -> int:
            manager.create_initial_profile(draft)
            return 0

    ready = ensure_initial_profile(manager, SetupProcess)

    assert ready is True
    assert manager.get_profile() == draft
    assert manager.compile_initial_config().scenes[SceneId.DAY_WORK].playlist == "WORK"


def test_startup_returns_none_when_setup_closes_before_creating_profile(tmp_path: Path):
    manager = ProfileManager(str(tmp_path / "profile"))

    class SetupProcess:
        @staticmethod
        def wait() -> int:
            return 0

    ready = ensure_initial_profile(manager, SetupProcess)

    assert ready is False
    assert manager.get_profile() is None
