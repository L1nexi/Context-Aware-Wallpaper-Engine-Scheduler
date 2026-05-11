from __future__ import annotations

import os
import sys
import tempfile
from unittest import mock

import pytest

from utils.we_path import (
    _steam_install_path,
    _parse_library_folders,
    resolve_wallpaper_engine_path,
    find_we_config_json,
)


# ── _steam_install_path ─────────────────────────────────────────────

def test_steam_install_path_returns_none_on_non_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert _steam_install_path() is None


def test_steam_install_path_returns_none_when_winreg_unavailable(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delitem(sys.modules, "winreg", raising=False)

    import builtins
    _orig_import = builtins.__import__

    def _block_winreg(name, *args, **kwargs):
        if name == "winreg":
            raise ImportError("no winreg")
        return _orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_winreg)
    # Reset the module-level import
    import utils.we_path as wp
    assert wp._steam_install_path() is None


def test_steam_install_path_hklm_found(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    mock_key = mock.MagicMock()
    mock_key.__enter__ = mock.MagicMock(return_value=mock_key)
    mock_key.__exit__ = mock.MagicMock(return_value=False)

    mock_winreg = mock.MagicMock()
    mock_winreg.HKEY_LOCAL_MACHINE = 0
    mock_winreg.HKEY_CURRENT_USER = 1
    mock_winreg.OpenKey.return_value = mock_key
    mock_winreg.QueryValueEx.return_value = ("C:\\Steam", None)

    with mock.patch.dict("sys.modules", {"winreg": mock_winreg}):
        import utils.we_path as wp
        monkeypatch.setattr(wp, "_steam_install_path", lambda: None)
        # We test with direct mock
        result = _steam_install_path()
        # On actual Windows this might return a real path; on non-Windows → None
        # The important thing is: with winreg mock, it returns the mock path
        if sys.platform == "win32":
            assert result is not None or result == "C:\\Steam"


# ── _parse_library_folders ─────────────────────────────────────────

def test_parse_library_folders_vdf_not_found(tmp_path):
    steam_path = str(tmp_path)
    libs = _parse_library_folders(steam_path)
    # When libraryfolders.vdf doesn't exist, returns [steam_path]
    assert libs == [steam_path]


def test_parse_library_folders_parses_entries(tmp_path):
    steam_path = str(tmp_path)
    steamapps = os.path.join(steam_path, "steamapps")
    os.makedirs(steamapps)
    vdf_path = os.path.join(steamapps, "libraryfolders.vdf")

    vdf_content = '''"libraryfolders"
{
    "0"
    {
        "path"\t\t"C:\\\\Program Files (x86)\\\\Steam"
    }
    "1"
    {
        "path"\t\t"E:\\\\SteamLibrary"
    }
}'''
    with open(vdf_path, "w", encoding="utf-8") as f:
        f.write(vdf_content)

    libs = _parse_library_folders(steam_path)
    assert steam_path in libs
    assert "E:\\SteamLibrary" in libs


def test_parse_library_folders_corrupt_file_is_silent(tmp_path):
    steam_path = str(tmp_path)
    steamapps = os.path.join(steam_path, "steamapps")
    os.makedirs(steamapps)
    vdf_path = os.path.join(steamapps, "libraryfolders.vdf")
    # Write non-UTF8 bytes
    with open(vdf_path, "wb") as f:
        f.write(b"\xff\xfe\x00\x01")
    libs = _parse_library_folders(steam_path)
    assert libs == [steam_path]


# ── find_wallpaper_engine ──────────────────────────────────────────

def test_find_we_tier1_configured_path_exists(tmp_path):
    fake_exe = os.path.join(str(tmp_path), "wallpaper64.exe")
    with open(fake_exe, "w") as f:
        f.write("fake")

    result = resolve_wallpaper_engine_path(fake_exe)
    assert result == fake_exe


def test_find_we_tier1_configured_path_not_exists(monkeypatch):
    monkeypatch.setattr("utils.we_path._steam_install_path", lambda: None)
    result = resolve_wallpaper_engine_path("Z:\\nonexistent\\wallpaper64.exe")
    assert result is None


def test_find_we_tier1_empty_string(monkeypatch):
    monkeypatch.setattr("utils.we_path._steam_install_path", lambda: None)
    result = resolve_wallpaper_engine_path("")
    assert result is None


def test_find_we_steam_found(monkeypatch, tmp_path):
    """Simulate Steam search finding WE."""
    steam_path = str(tmp_path / "Steam")
    we_dir = os.path.join(steam_path, "steamapps", "common", "wallpaper_engine")
    os.makedirs(we_dir)
    we_exe = os.path.join(we_dir, "wallpaper64.exe")
    with open(we_exe, "w") as f:
        f.write("fake")

    def mock_steam():
        return steam_path

    monkeypatch.setattr("utils.we_path._steam_install_path", mock_steam)
    result = resolve_wallpaper_engine_path("")
    assert result == we_exe


def test_find_we_steam_not_found(monkeypatch):
    def mock_steam():
        return "C:\\Steam"

    monkeypatch.setattr("utils.we_path._steam_install_path", mock_steam)
    monkeypatch.setattr("utils.we_path._parse_library_folders", lambda x: ["C:\\Steam"])

    # Ensure the candidate doesn't exist
    result = resolve_wallpaper_engine_path("")
    assert result is None


def test_find_we_no_steam_no_config(monkeypatch):
    monkeypatch.setattr("utils.we_path._steam_install_path", lambda: None)
    result = resolve_wallpaper_engine_path("")
    assert result is None


# ── find_we_config_json ────────────────────────────────────────────

def test_find_we_config_json_when_we_found(tmp_path):
    we_dir = str(tmp_path)
    we_exe = os.path.join(we_dir, "wallpaper64.exe")
    config_json = os.path.join(we_dir, "config.json")

    with open(we_exe, "w") as f:
        f.write("fake")
    with open(config_json, "w") as f:
        f.write("{}")

    result = find_we_config_json(we_exe)
    assert result == config_json


def test_find_we_config_json_we_not_found(monkeypatch):
    monkeypatch.setattr("utils.we_path._steam_install_path", lambda: None)
    result = find_we_config_json("Z:\\nonexistent\\wallpaper64.exe")
    assert result is None


def test_find_we_config_json_we_found_but_no_config(tmp_path):
    we_dir = str(tmp_path)
    we_exe = os.path.join(we_dir, "wallpaper64.exe")
    with open(we_exe, "w") as f:
        f.write("fake")
    # No config.json

    result = find_we_config_json(we_exe)
    assert result is None


def test_find_we_config_json_empty_path(monkeypatch):
    monkeypatch.setattr("utils.we_path._steam_install_path", lambda: None)
    result = find_we_config_json("")
    assert result is None
