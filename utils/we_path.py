"""Wallpaper Engine path detection helpers.

Startup / reload code should resolve the executable path before constructing
runtime components. This module intentionally does not deal with process
readiness or command execution.
"""

from __future__ import annotations
import os
import sys
import logging

logger = logging.getLogger("WEScheduler.WEPath")


def _steam_install_path() -> str | None:
    """Read Steam install path from Windows registry."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None

    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for subkey in (r"Software\Valve\Steam", r"SOFTWARE\Valve\Steam"):
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    val, _ = winreg.QueryValueEx(key, "SteamPath")
                    return val.replace("/", "\\")
            except OSError:
                continue
    return None


def _parse_library_folders(steam_path: str) -> list[str]:
    """Parse libraryfolders.vdf to get all Steam library roots."""
    vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if not os.path.exists(vdf_path):
        return [steam_path]

    libraries = [steam_path]
    try:
        with open(vdf_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith('"path"'):
                    # Format: "path"\t\t"E:\\SteamLibrary"
                    parts = line.split('"')
                    if len(parts) >= 4:
                        lib = parts[3].replace("\\\\", "\\")
                        libraries.append(lib)
    except Exception:
        pass
    return libraries


def resolve_wallpaper_engine_path(configured_path: str) -> str | None:
    """Resolve wallpaper64.exe from a configured path or Steam libraries.

    When ``configured_path`` is a non-empty string, this function only checks
    that exact path and never falls back to auto-detection. An empty string
    means "auto-detect".
    """
    if configured_path:
        if os.path.isfile(configured_path):
            return configured_path
        return None

    steam = _steam_install_path()
    if steam:
        for lib in _parse_library_folders(steam):
            candidate = os.path.join(
                lib, "steamapps", "common", "wallpaper_engine", "wallpaper64.exe"
            )
            if os.path.isfile(candidate):
                logger.info("Found WE at: %s", candidate)
                return candidate

    return None

def find_we_config_json(we_exe_path: str | None) -> str | None:
    """Find WE's config.json from an already resolved executable path.

    Returns the full path to WE's config.json, or None.
    """
    if we_exe_path:
        config_json = os.path.join(os.path.dirname(we_exe_path), "config.json")
        if os.path.isfile(config_json):
            return config_json
    return None
