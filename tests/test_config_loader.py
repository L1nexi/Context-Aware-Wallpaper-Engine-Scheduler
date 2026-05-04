from __future__ import annotations

import json

import pytest

from utils.config_loader import ConfigLoader


def _write_config(tmp_path, playlists):
    path = tmp_path / "scheduler_config.json"
    path.write_text(
        json.dumps(
            {
                "wallpaper_engine_path": "C:\\fake\\wallpaper64.exe",
                "tags": {},
                "playlists": playlists,
                "policies": {},
                "scheduling": {},
            }
        ),
        encoding="utf-8",
    )
    return str(path)


def test_config_loader_accepts_six_digit_hex_playlist_color(tmp_path):
    path = _write_config(
        tmp_path,
        [
            {"name": "focus", "color": "#F5C518", "tags": {"#focus": 1.0}},
            {"name": "rainy", "color": "#4a90d9", "tags": {"#rain": 1.0}},
        ],
    )

    config = ConfigLoader(path).load()

    assert config.playlists[0].color == "#F5C518"
    assert config.playlists[1].color == "#4a90d9"


def test_config_loader_rejects_missing_playlist_color(tmp_path):
    path = _write_config(
        tmp_path,
        [
            {"name": "focus", "tags": {"#focus": 1.0}},
        ],
    )

    with pytest.raises(ValueError) as exc_info:
        ConfigLoader(path).load()

    assert "playlists.0.color" in str(exc_info.value)


@pytest.mark.parametrize("color", ["#FFF", "rgb(255,0,0)", ""])
def test_config_loader_rejects_invalid_playlist_color_format(tmp_path, color):
    path = _write_config(
        tmp_path,
        [
            {"name": "focus", "color": color, "tags": {"#focus": 1.0}},
        ],
    )

    with pytest.raises(ValueError) as exc_info:
        ConfigLoader(path).load()

    assert "playlists.0.color" in str(exc_info.value)
