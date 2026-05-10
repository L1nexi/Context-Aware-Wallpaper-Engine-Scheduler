"""
WE installation path detection.

Resolves wallpaper_engine_path in three tiers:
1. From scheduler runtime config (already configured)
2. Via Steam registry → libraryfolders.vdf search
3. Returns None if not found

Does NOT require WE to be running.
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


def find_wallpaper_engine(config_wallpaper_engine_path: str) -> str | None:
    """Find wallpaper64.exe, returning the full path or None.

    Tier 1: Use the configured path if it exists.
    Tier 2: Search Steam library folders for the WE installation.
    """
    # Tier 1: configured path
    if config_wallpaper_engine_path and os.path.isfile(config_wallpaper_engine_path):
        return config_wallpaper_engine_path

    # Tier 2: Steam library search
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


def find_we_config_json(config_wallpaper_engine_path: str) -> str | None:
    """Find WE's config.json given the configured wallpaper_engine_path.

    Returns the full path to WE's config.json, or None.
    """
    we_exe = find_wallpaper_engine(config_wallpaper_engine_path)
    if we_exe:
        config_json = os.path.join(os.path.dirname(we_exe), "config.json")
        if os.path.isfile(config_json):
            return config_json
    return None
