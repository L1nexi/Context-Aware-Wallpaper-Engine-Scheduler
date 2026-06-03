from __future__ import annotations

import json
import os

import pytest

from core.runtime.we_config import FactualPlaylistStatus, WEConfigProber, WEConfigReadError


def _write_we_config(tmp_path, data: object) -> str:
    exe = tmp_path / "wallpaper64.exe"
    exe.write_text("fake", encoding="utf-8")
    (tmp_path / "config.json").write_text(
        json.dumps(data),
        encoding="utf-8",
    )
    return str(exe)


def _user_config(general: dict) -> dict:
    return {
        "test-user": {
            "general": general,
        }
    }


def test_probe_playlist_reads_current_playlist(monkeypatch, tmp_path):
    monkeypatch.setattr("core.runtime.we_config.getpass.getuser", lambda: "test-user")
    exe = _write_we_config(
        tmp_path,
        _user_config(
            {
                "wallpaperconfig": {
                    "selectedwallpapers": {
                        "monitor0": {"playlist": {"name": "Focus"}},
                    }
                }
            }
        ),
    )

    state = WEConfigProber(exe).probe_playlist()

    assert state.status == FactualPlaylistStatus.PLAYLIST
    assert state.playlist == "Focus"
    assert state.source == os.path.join(str(tmp_path), "config.json")


def test_probe_playlist_reports_no_playlist_for_single_wallpaper(monkeypatch, tmp_path):
    monkeypatch.setattr("core.runtime.we_config.getpass.getuser", lambda: "test-user")
    exe = _write_we_config(
        tmp_path,
        _user_config(
            {
                "wallpaperconfig": {
                    "selectedwallpapers": {
                        "monitor0": {"file": "projects/example/project.json"},
                    }
                }
            }
        ),
    )

    state = WEConfigProber(exe).probe_playlist()

    assert state.status == FactualPlaylistStatus.NO_PLAYLIST
    assert state.playlist is None


def test_probe_playlist_reports_no_playlist_without_wallpaperconfig(monkeypatch, tmp_path):
    monkeypatch.setattr("core.runtime.we_config.getpass.getuser", lambda: "test-user")
    exe = _write_we_config(
        tmp_path,
        _user_config({"playlists": [{"name": "Focus"}]}),
    )

    state = WEConfigProber(exe).probe_playlist()

    assert state.status == FactualPlaylistStatus.NO_PLAYLIST


def test_probe_playlist_reports_unknown_for_unreadable_json(tmp_path):
    exe = tmp_path / "wallpaper64.exe"
    exe.write_text("fake", encoding="utf-8")
    (tmp_path / "config.json").write_text("{not json", encoding="utf-8")

    state = WEConfigProber(str(exe)).probe_playlist()

    assert state.status == FactualPlaylistStatus.UNKNOWN
    assert state.issue == "wallpaper_engine_config_read_failed"


def test_probe_playlist_accepts_same_playlist_on_multiple_displays(monkeypatch, tmp_path):
    monkeypatch.setattr("core.runtime.we_config.getpass.getuser", lambda: "test-user")
    exe = _write_we_config(
        tmp_path,
        _user_config(
            {
                "wallpaperconfig": {
                    "selectedwallpapers": {
                        "monitor0": {"playlist": {"name": "Focus"}},
                        "monitor1": {"playlist": {"name": "Focus"}},
                    }
                }
            }
        ),
    )

    state = WEConfigProber(exe).probe_playlist()

    assert state.status == FactualPlaylistStatus.PLAYLIST
    assert state.playlist == "Focus"


def test_probe_playlist_reports_ambiguous_for_different_display_playlists(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr("core.runtime.we_config.getpass.getuser", lambda: "test-user")
    exe = _write_we_config(
        tmp_path,
        _user_config(
            {
                "wallpaperconfig": {
                    "selectedwallpapers": {
                        "monitor0": {"playlist": {"name": "Focus"}},
                        "monitor1": {"playlist": {"name": "Rain"}},
                    }
                }
            }
        ),
    )

    state = WEConfigProber(exe).probe_playlist()

    assert state.status == FactualPlaylistStatus.AMBIGUOUS
    assert state.issue == "multiple_wallpaper_playlists"


def test_scan_playlist_names_reads_playlist_list(monkeypatch, tmp_path):
    monkeypatch.setattr("core.runtime.we_config.getpass.getuser", lambda: "test-user")
    exe = _write_we_config(
        tmp_path,
        _user_config(
            {
                "playlists": [
                    {"name": " Focus "},
                    {"name": ""},
                    {"name": "Rain"},
                    {"title": "ignored"},
                ]
            }
        ),
    )

    names = WEConfigProber(exe).scan_playlist_names()

    assert names == ["Focus", "Rain"]


def test_probe_item_counts_returns_item_count_per_playlist(monkeypatch, tmp_path):
    monkeypatch.setattr("core.runtime.we_config.getpass.getuser", lambda: "test-user")
    exe = _write_we_config(
        tmp_path,
        _user_config(
            {
                "playlists": [
                    {"name": "Focus", "items": ["a.mp4", "b.pkg", "c.mp4"]},
                    {"name": "Rain", "items": ["x.pkg"]},
                ]
            }
        ),
    )

    counts = WEConfigProber(exe).probe_item_counts()

    assert counts == {"Focus": 3, "Rain": 1}


def test_probe_item_counts_skips_entries_without_items(monkeypatch, tmp_path):
    monkeypatch.setattr("core.runtime.we_config.getpass.getuser", lambda: "test-user")
    exe = _write_we_config(
        tmp_path,
        _user_config(
            {
                "playlists": [
                    {"name": "Focus", "items": ["a.mp4"]},
                    {"name": "Empty"},
                    {"name": "Bad", "items": "not_a_list"},
                ]
            }
        ),
    )

    counts = WEConfigProber(exe).probe_item_counts()

    assert counts == {"Focus": 1}


def test_probe_item_counts_raises_on_read_error(tmp_path):
    exe = tmp_path / "wallpaper64.exe"
    exe.write_text("fake", encoding="utf-8")
    (tmp_path / "config.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(WEConfigReadError):
        WEConfigProber(str(exe)).probe_item_counts()
