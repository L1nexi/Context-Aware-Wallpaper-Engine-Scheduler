from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from core.policies import get_policy_fixed_output_tags
from utils.config_errors import ConfigLoadError
from utils.config_loader import ConfigLoader
from utils.runtime_config import PLAYLIST_AUTO_COLOR_PALETTE


@pytest.fixture(autouse=True)
def mock_resolved_wallpaper_engine_path(monkeypatch, tmp_path):
    fake_exe = tmp_path / "wallpaper64.exe"
    fake_exe.write_text("fake", encoding="utf-8")

    def _resolve(path: str) -> str | None:
        if path:
            return path if Path(path).is_file() else None
        return str(fake_exe)

    monkeypatch.setattr("utils.config_documents.resolve_wallpaper_engine_path", _resolve)
    return str(fake_exe)


def _base_documents() -> dict[str, dict]:
    tag_names = [
        "focus",
        "chill",
        "dawn",
        "day",
        "sunset",
        "night",
        "spring",
        "summer",
        "autumn",
        "winter",
        "clear",
        "cloudy",
        "rain",
        "storm",
        "snow",
        "fog",
    ]
    return {
        "scheduler.yaml": {
            "version": 2,
            "runtime": {
                "wallpaper_engine_path": None,
                "language": None,
            },
        },
        "playlists.yaml": {
            "playlists": {
                "FOCUS": {
                    "display": "Focus",
                    "tags": {
                        "focus": 1.0,
                        "day": 0.8,
                        "clear": 0.4,
                    },
                },
                "CHILL": {
                    "display": "Chill",
                    "color": "#4A90D9",
                    "tags": {
                        "chill": 1.0,
                        "night": 0.7,
                        "rain": 0.3,
                    },
                },
            }
        },
        "tags.yaml": {
            "tags": {
                tag_name: {"fallback": {}}
                for tag_name in tag_names
            }
        },
        "activity.yaml": {
            "activity": {
                "enabled": True,
                "weight": 1.2,
                "smoothing_window": 120,
                "process": {
                    "Code": "focus",
                },
                "title": {
                    "YouTube": "chill",
                },
                "matchers": [
                    {
                        "source": "title",
                        "match": "regex",
                        "pattern": "^GitHub .* Actions$",
                        "tag": "focus",
                    }
                ],
            }
        },
        "context.yaml": {
            "time": {
                "enabled": True,
                "weight": 0.8,
                "auto": True,
                "day_start_hour": 8,
                "night_start_hour": 20,
            },
            "season": {
                "enabled": True,
                "weight": 0.65,
                "spring_peak": 80,
                "summer_peak": 172,
                "autumn_peak": 265,
                "winter_peak": 355,
            },
            "weather": {
                "enabled": True,
                "weight": 1.5,
                "api_key": "",
                "lat": 31.2,
                "lon": 121.5,
                "fetch_interval": 600,
                "request_timeout": 10,
                "warmup_timeout": 3,
            },
        },
        "scheduling.yaml": {
            "scheduling": {
                "startup_delay": 15,
                "idle_threshold": 20,
                "switch_cooldown": 150,
                "cycle_cooldown": 900,
                "force_after": 3600,
                "cpu_threshold": 85,
                "cpu_sample_window": 10,
                "pause_on_fullscreen": True,
            }
        },
    }


def _scratch_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="wes-config-loader-"))


def _write_config_dir(overrides: dict[str, object] | None = None) -> Path:
    config_dir = _scratch_root() / "config"
    config_dir.mkdir()
    documents = _base_documents()
    if overrides:
        for file_name, value in overrides.items():
            if value is None:
                documents.pop(file_name, None)
            else:
                documents[file_name] = value

    for file_name, document in documents.items():
        (config_dir / file_name).write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    return config_dir


def test_config_loader_requires_all_six_yaml_files():
    config_dir = _write_config_dir(overrides={"context.yaml": None})

    with pytest.raises(ValueError) as exc_info:
        ConfigLoader(str(config_dir)).load_verified_config()

    assert "context.yaml" in str(exc_info.value)
    assert "missing required file" in str(exc_info.value)


@pytest.mark.parametrize(
    "scheduler_document",
    [
        {"runtime": {"wallpaper_engine_path": None}},
        {"version": 1, "runtime": {"wallpaper_engine_path": None}},
    ],
)
def test_config_loader_requires_version_2(scheduler_document: dict):
    config_dir = _write_config_dir(overrides={"scheduler.yaml": scheduler_document})

    with pytest.raises(ValueError) as exc_info:
        ConfigLoader(str(config_dir)).load_verified_config()

    error_text = str(exc_info.value)
    assert "scheduler.yaml" in error_text
    assert "version" in error_text


def test_config_loader_allows_yaml_merge_alias_and_anchor_features():
    config_dir = _write_config_dir()
    (config_dir / "playlists.yaml").write_text(
        (
            "playlists:\n"
            "  BASE: &base\n"
            "    display: Base\n"
            "    tags:\n"
            "      focus: 1.0\n"
            "  COPY:\n"
            "    <<: *base\n"
            "    color: amber\n"
        ),
        encoding="utf-8",
    )

    config = ConfigLoader(str(config_dir)).load_verified_config()

    assert config.playlists["BASE"].display == "Base"
    assert config.playlists["COPY"].display == "Base"
    assert config.playlists["COPY"].color == "#CA8A04"
    assert config.playlists["COPY"].tags == {"focus": 1.0}


def test_config_loader_rejects_duplicate_yaml_keys_with_location():
    config_dir = _write_config_dir()
    (config_dir / "tags.yaml").write_text(
        "tags:\n  focus:\n    fallback: {}\n  focus:\n    fallback: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigLoadError) as exc_info:
        ConfigLoader(str(config_dir)).load_verified_config()

    assert len(exc_info.value.issues) == 1
    issue = exc_info.value.issues[0]
    assert issue.source_file == "tags.yaml"
    assert issue.field_path == ("tags", "focus")
    assert issue.line == 4
    assert issue.column == 3
    assert "duplicate YAML key 'focus'" in str(exc_info.value)


def test_policy_fixed_output_tags_come_from_policy_registry_metadata():
    assert get_policy_fixed_output_tags() == {
        "time": ("dawn", "day", "sunset", "night"),
        "season": ("spring", "summer", "autumn", "winter"),
        "weather": ("clear", "cloudy", "rain", "storm", "snow", "fog"),
    }


def test_config_loader_parses_playlist_map_and_assigns_missing_colors(
    mock_resolved_wallpaper_engine_path,
):
    config_dir = _write_config_dir()

    config = ConfigLoader(str(config_dir)).load_verified_config()

    assert config.wallpaper_engine_path == mock_resolved_wallpaper_engine_path
    assert set(config.playlists) == {"FOCUS", "CHILL"}
    assert config.playlists["FOCUS"].display == "Focus"
    assert config.playlists["FOCUS"].color == PLAYLIST_AUTO_COLOR_PALETTE[0]
    assert config.playlists["CHILL"].color == "#4A90D9"
    assert len(config.policies.activity.matchers) == 3
    assert config.policies.activity.matchers[0].source == "process"
    assert config.policies.activity.matchers[0].match == "exact"
    assert config.policies.activity.matchers[0].pattern == "Code"
    assert config.policies.activity.matchers[1].source == "title"
    assert config.policies.activity.matchers[1].match == "contains"
    assert config.policies.activity.matchers[1].pattern == "YouTube"
    assert config.policies.activity.matchers[2].match == "regex"


def test_config_loader_allows_empty_playlist_tag_vector():
    documents = _base_documents()
    documents["playlists.yaml"]["playlists"]["FOCUS"]["tags"] = {}
    config_dir = _write_config_dir(overrides={"playlists.yaml": documents["playlists.yaml"]})

    config = ConfigLoader(str(config_dir)).load_verified_config()

    assert config.playlists["FOCUS"].tags == {}


def test_config_loader_normalizes_named_and_hashless_playlist_colors():
    documents = _base_documents()
    documents["playlists.yaml"]["playlists"]["FOCUS"]["color"] = "amber"
    documents["playlists.yaml"]["playlists"]["CHILL"]["color"] = "2e5f8a"
    config_dir = _write_config_dir(overrides={"playlists.yaml": documents["playlists.yaml"]})

    config = ConfigLoader(str(config_dir)).load_verified_config()

    assert config.playlists["FOCUS"].color == "#CA8A04"
    assert config.playlists["CHILL"].color == "#2E5F8A"


def test_config_loader_rejects_undeclared_tag_references():
    documents = _base_documents()
    documents["playlists.yaml"]["playlists"]["FOCUS"]["tags"]["unknown"] = 0.2
    config_dir = _write_config_dir(overrides={"playlists.yaml": documents["playlists.yaml"]})

    with pytest.raises(ValueError) as exc_info:
        ConfigLoader(str(config_dir)).load_verified_config()

    error_text = str(exc_info.value)
    assert "playlists.yaml" in error_text
    assert "playlists.FOCUS.tags.unknown" in error_text
    assert "must be declared in tags.yaml" in error_text


def test_config_loader_error_includes_source_file_and_field_path():
    documents = _base_documents()
    documents["activity.yaml"]["activity"]["process"]["Code"] = "#focus"
    config_dir = _write_config_dir(overrides={"activity.yaml": documents["activity.yaml"]})

    with pytest.raises(ValueError) as exc_info:
        ConfigLoader(str(config_dir)).load_verified_config()

    error_text = str(exc_info.value)
    assert "activity.yaml" in error_text
    assert "activity.process.Code" in error_text
    assert "must be declared in tags.yaml" in error_text


def test_config_loader_collects_errors_across_files_before_cross_validation():
    config_dir = _write_config_dir()
    (config_dir / "scheduler.yaml").write_text(
        yaml.safe_dump({"runtime": {"wallpaper_engine_path": None}}, sort_keys=False),
        encoding="utf-8",
    )
    (config_dir / "playlists.yaml").write_text(
        yaml.safe_dump({"playlists": {"": {"tags": {"focus": 1.0}}}}, sort_keys=False),
        encoding="utf-8",
    )
    (config_dir / "activity.yaml").write_text(
        yaml.safe_dump({"activity": {"unknown_block": {"Code.exe": "focus"}}}, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        ConfigLoader(str(config_dir)).load_verified_config()

    error_text = str(exc_info.value)
    assert "scheduler.yaml" in error_text
    assert "version" in error_text
    assert "playlists.yaml" in error_text
    assert "playlist name must not be empty" in error_text
    assert "activity.yaml" in error_text
    assert "unknown_block" in error_text


def test_load_configured_wallpaper_engine_path_reads_scheduler_yaml():
    config_dir = _write_config_dir()

    configured_path = ConfigLoader.load_configured_wallpaper_engine_path(str(config_dir))

    assert configured_path is None


def test_config_loader_rejects_unresolved_auto_detect(monkeypatch):
    monkeypatch.setattr("utils.config_documents.resolve_wallpaper_engine_path", lambda _path: None)
    config_dir = _write_config_dir()

    with pytest.raises(ConfigLoadError) as exc_info:
        ConfigLoader(str(config_dir)).load_verified_config()

    assert len(exc_info.value.issues) == 1
    issue = exc_info.value.issues[0]
    assert issue.source_file == "scheduler.yaml"
    assert issue.field_path == ("runtime", "wallpaper_engine_path")
    assert issue.code == "wallpaper_engine_path_unresolved"
    assert "could not be auto-detected" in issue.message
