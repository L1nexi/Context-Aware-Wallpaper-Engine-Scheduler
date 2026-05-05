from __future__ import annotations

import json

import pytest

from utils.config_loader import AppConfig, ConfigLoader, PLAYLIST_AUTO_COLOR_PALETTE


def _write_config(tmp_path, config):
    path = tmp_path / "scheduler_config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return str(path)


def _base_config(*, playlists=None, policies=None):
    return {
        "wallpaper_engine_path": "C:\\fake\\wallpaper64.exe",
        "tags": {},
        "playlists": playlists
        if playlists is not None
        else [
            {"name": "focus", "color": "#F5C518", "tags": {"#focus": 1.0}},
        ],
        "policies": {} if policies is None else policies,
    }


def test_app_config_defaults_form_complete_canonical_tree():
    defaults = AppConfig()

    assert defaults.wallpaper_engine_path == ""
    assert defaults.language is None
    assert defaults.playlists == []
    assert defaults.tags == {}
    assert defaults.policies.activity.enabled is True
    assert defaults.policies.time.auto is True
    assert defaults.policies.season.spring_peak == 80
    assert defaults.policies.weather.lat is None
    assert defaults.policies.weather.lon is None
    assert defaults.scheduling.startup_delay == 30.0


def test_config_loader_normalizes_sparse_config(tmp_path):
    path = _write_config(
        tmp_path,
        {
            "wallpaper_engine_path": "C:\\fake\\wallpaper64.exe",
            "playlists": [{"name": "focus", "color": "#F5C518", "tags": {"#focus": 1.0}}],
        },
    )

    config = ConfigLoader(path).load()

    assert config.language is None
    assert config.tags == {}
    assert config.playlists[0].display == ""
    assert config.policies.activity.enabled is True
    assert config.policies.weather.enabled is True
    assert config.policies.weather.lat is None
    assert config.scheduling.pause_on_fullscreen is True


def test_config_loader_allows_empty_general_and_playlist_sections(tmp_path):
    config = _base_config(playlists=[], policies={})
    config["wallpaper_engine_path"] = ""
    path = _write_config(
        tmp_path,
        config,
    )
    loaded = ConfigLoader(path).load()

    assert loaded.wallpaper_engine_path == ""
    assert loaded.playlists == []
    assert loaded.policies.time.enabled is True


def test_config_loader_accepts_six_digit_hex_playlist_color(tmp_path):
    path = _write_config(
        tmp_path,
        _base_config(
            playlists=[
                {"name": "focus", "color": "#F5C518", "tags": {"#focus": 1.0}},
                {"name": "rainy", "color": "#4a90d9", "tags": {"#rain": 1.0}},
            ]
        ),
    )

    config = ConfigLoader(path).load()

    assert config.playlists[0].color == "#F5C518"
    assert config.playlists[1].color == "#4a90d9"


def test_config_loader_assigns_palette_color_to_missing_playlist_color(tmp_path):
    path = _write_config(
        tmp_path,
        _base_config(
            playlists=[
                {"name": "focus", "tags": {"#focus": 1.0}},
            ]
        ),
    )

    config = ConfigLoader(path).load()

    assert config.playlists[0].color == PLAYLIST_AUTO_COLOR_PALETTE[0]


def test_config_loader_assigns_palette_color_to_null_playlist_color(tmp_path):
    path = _write_config(
        tmp_path,
        _base_config(
            playlists=[
                {"name": "focus", "color": None, "tags": {"#focus": 1.0}},
            ]
        ),
    )

    config = ConfigLoader(path).load()

    assert config.playlists[0].color == PLAYLIST_AUTO_COLOR_PALETTE[0]


def test_config_loader_assigns_palette_colors_only_to_missing_entries(tmp_path):
    path = _write_config(
        tmp_path,
        _base_config(
            playlists=[
                {"name": "focus", "color": "#F5C518", "tags": {"#focus": 1.0}},
                {"name": "rainy", "tags": {"#rain": 1.0}},
                {"name": "night", "color": "#2E5F8A", "tags": {"#night": 1.0}},
                {"name": "weekend", "color": None, "tags": {"#weekend": 1.0}},
            ]
        ),
    )

    config = ConfigLoader(path).load()

    assert [playlist.color for playlist in config.playlists] == [
        "#F5C518",
        PLAYLIST_AUTO_COLOR_PALETTE[0],
        "#2E5F8A",
        PLAYLIST_AUTO_COLOR_PALETTE[1],
    ]


def test_config_loader_restarts_auto_color_assignment_on_every_load(tmp_path):
    path = _write_config(
        tmp_path,
        _base_config(
            playlists=[
                {"name": "focus", "tags": {"#focus": 1.0}},
                {"name": "rainy", "tags": {"#rain": 1.0}},
            ]
        ),
    )
    loader = ConfigLoader(path)

    first = loader.load()
    second = loader.load()

    assert [playlist.color for playlist in first.playlists] == [
        PLAYLIST_AUTO_COLOR_PALETTE[0],
        PLAYLIST_AUTO_COLOR_PALETTE[1],
    ]
    assert [playlist.color for playlist in second.playlists] == [
        PLAYLIST_AUTO_COLOR_PALETTE[0],
        PLAYLIST_AUTO_COLOR_PALETTE[1],
    ]


@pytest.mark.parametrize("color", ["#FFF", "rgb(255,0,0)", ""])
def test_config_loader_rejects_invalid_playlist_color_format(tmp_path, color):
    path = _write_config(
        tmp_path,
        _base_config(
            playlists=[
                {"name": "focus", "color": color, "tags": {"#focus": 1.0}},
            ]
        ),
    )

    with pytest.raises(ValueError) as exc_info:
        ConfigLoader(path).load()

    assert "playlists.0.color" in str(exc_info.value)


def test_config_loader_accepts_null_weather_coordinates(tmp_path):
    path = _write_config(
        tmp_path,
        _base_config(
            policies={
                "weather": {
                    "api_key": "abc",
                    "lat": None,
                    "lon": None,
                }
            }
        ),
    )

    config = ConfigLoader(path).load()

    assert config.policies.weather.api_key == "abc"
    assert config.policies.weather.lat is None
    assert config.policies.weather.lon is None


def test_config_loader_accepts_numeric_weather_coordinates(tmp_path):
    path = _write_config(
        tmp_path,
        _base_config(
            policies={
                "weather": {
                    "lat": 31,
                    "lon": 121.5,
                }
            }
        ),
    )

    config = ConfigLoader(path).load()

    assert config.policies.weather.lat == 31.0
    assert config.policies.weather.lon == 121.5


def test_config_loader_rejects_string_weather_coordinates(tmp_path):
    path = _write_config(
        tmp_path,
        _base_config(
            policies={
                "weather": {
                    "lat": "31.2",
                    "lon": 121.5,
                }
            }
        ),
    )

    with pytest.raises(ValueError) as exc_info:
        ConfigLoader(path).load()

    assert "policies.weather.lat" in str(exc_info.value)


@pytest.mark.parametrize(
    ("field", "value", "message_fragment"),
    [
        ("lat", 90.1, "less than or equal to 90"),
        ("lat", -90.1, "greater than or equal to -90"),
        ("lon", 180.1, "less than or equal to 180"),
        ("lon", -180.1, "greater than or equal to -180"),
    ],
)
def test_config_loader_rejects_out_of_range_weather_coordinates(
    tmp_path,
    field,
    value,
    message_fragment,
):
    path = _write_config(
        tmp_path,
        _base_config(
            policies={
                "weather": {
                    field: value,
                }
            }
        ),
    )

    with pytest.raises(ValueError) as exc_info:
        ConfigLoader(path).load()

    assert f"policies.weather.{field}" in str(exc_info.value)
    assert message_fragment in str(exc_info.value)


def test_config_loader_rejects_unknown_policy_key(tmp_path):
    path = _write_config(
        tmp_path,
        _base_config(
            policies={
                "moon": {
                    "enabled": True,
                }
            }
        ),
    )

    with pytest.raises(ValueError) as exc_info:
        ConfigLoader(path).load()

    assert "policies.moon" in str(exc_info.value)
