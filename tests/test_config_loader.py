from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from utils.config_loader import ConfigLoader, PLAYLIST_AUTO_COLOR_PALETTE


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
                "process_rules": {
                    "Code.exe": "focus",
                },
                "title_rules": {
                    "YouTube": "chill",
                },
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
    root = Path.cwd() / "data" / "pytest-config-loader"
    root.mkdir(parents=True, exist_ok=True)
    scratch = root / uuid4().hex
    scratch.mkdir()
    return scratch


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
        ConfigLoader(str(config_dir)).load()

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
        ConfigLoader(str(config_dir)).load()

    error_text = str(exc_info.value)
    assert "scheduler.yaml" in error_text
    assert "version" in error_text


@pytest.mark.parametrize(
    ("file_name", "content", "message"),
    [
        (
            "tags.yaml",
            "tags:\n  focus: &base\n    fallback: {}\n",
            "YAML anchors are not supported",
        ),
        (
            "tags.yaml",
            "tags:\n  focus:\n    fallback: *base\n",
            "YAML aliases are not supported",
        ),
        (
            "playlists.yaml",
            "playlists:\n  BASE:\n    display: Base\n    tags:\n      focus: 1.0\n  COPY:\n    <<:\n      display: Base\n      tags:\n        focus: 1.0\n",
            "YAML merge keys are not supported",
        ),
    ],
)
def test_config_loader_rejects_yaml_advanced_features(
    file_name: str,
    content: str,
    message: str,
):
    config_dir = _write_config_dir()
    (config_dir / file_name).write_text(content, encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        ConfigLoader(str(config_dir)).load()

    error_text = str(exc_info.value)
    assert file_name in error_text
    assert message in error_text


def test_config_loader_parses_playlist_map_and_assigns_missing_colors():
    config_dir = _write_config_dir()

    config = ConfigLoader(str(config_dir)).load()

    assert config.wallpaper_engine_path == ""
    assert set(config.playlists) == {"FOCUS", "CHILL"}
    assert config.playlists["FOCUS"].display == "Focus"
    assert config.playlists["FOCUS"].color == PLAYLIST_AUTO_COLOR_PALETTE[0]
    assert config.playlists["CHILL"].color == "#4A90D9"
    assert config.policies.activity.process_rules["Code.exe"] == "focus"


def test_config_loader_rejects_undeclared_tag_references():
    documents = _base_documents()
    documents["playlists.yaml"]["playlists"]["FOCUS"]["tags"]["unknown"] = 0.2
    config_dir = _write_config_dir(overrides={"playlists.yaml": documents["playlists.yaml"]})

    with pytest.raises(ValueError) as exc_info:
        ConfigLoader(str(config_dir)).load()

    error_text = str(exc_info.value)
    assert "playlists.yaml" in error_text
    assert "playlists.FOCUS.tags.unknown" in error_text
    assert "must be declared in tags.yaml" in error_text


def test_config_loader_error_includes_source_file_and_field_path():
    documents = _base_documents()
    documents["activity.yaml"]["activity"]["process_rules"]["Code.exe"] = "#focus"
    config_dir = _write_config_dir(overrides={"activity.yaml": documents["activity.yaml"]})

    with pytest.raises(ValueError) as exc_info:
        ConfigLoader(str(config_dir)).load()

    error_text = str(exc_info.value)
    assert "activity.yaml" in error_text
    assert "activity.process_rules['Code.exe']" in error_text
    assert "must not use a '#' prefix" in error_text
