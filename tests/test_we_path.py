from __future__ import annotations

from pathlib import Path

from core.runtime.we_path import find_we_config_json, resolve_wallpaper_engine_path


def test_configured_wallpaper_engine_executable_is_resolved(tmp_path: Path):
    executable = tmp_path / "wallpaper64.exe"
    executable.write_text("fake", encoding="utf-8")

    assert resolve_wallpaper_engine_path(str(executable)) == str(executable)


def test_missing_configured_wallpaper_engine_executable_is_rejected():
    assert resolve_wallpaper_engine_path(r"Z:\missing\wallpaper64.exe") is None


def test_wallpaper_engine_config_is_found_beside_resolved_executable(tmp_path: Path):
    executable = tmp_path / "wallpaper64.exe"
    executable.write_text("fake", encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")

    assert find_we_config_json(str(executable)) == str(config)


def test_missing_wallpaper_engine_config_is_reported(tmp_path: Path):
    executable = tmp_path / "wallpaper64.exe"
    executable.write_text("fake", encoding="utf-8")

    assert find_we_config_json(str(executable)) is None


def test_wallpaper_engine_config_requires_a_resolved_executable():
    assert find_we_config_json(None) is None
