from __future__ import annotations

import getpass
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from core.runtime.we_path import find_we_config_json


class FactualPlaylistStatus(StrEnum):
    PLAYLIST = "playlist"
    NO_PLAYLIST = "no_playlist"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class FactualPlaylistState:
    status: FactualPlaylistStatus
    playlist: str | None = None
    source: str | None = None
    issue: str | None = None


class WEConfigReadError(Exception):
    def __init__(self, code: str, config_json: str | None = None):
        super().__init__(code)
        self.code = code
        self.config_json = config_json


class WEConfigProber:
    def __init__(self, we_exe_path: str):
        self.we_exe_path = we_exe_path

    def probe_playlist(self) -> FactualPlaylistState:
        try:
            config_json, data = self._load_config()
        except WEConfigReadError as exc:
            return FactualPlaylistState(
                status=FactualPlaylistStatus.UNKNOWN,
                source=exc.config_json,
                issue=exc.code,
            )

        general = _user_general(data)
        if general is None:
            return FactualPlaylistState(
                status=FactualPlaylistStatus.NO_PLAYLIST,
                source=config_json,
            )

        wallpaper_config = general.get("wallpaperconfig")
        names = _extract_current_playlist_names(wallpaper_config.get("selectedwallpapers")) if isinstance(wallpaper_config, dict) else set()
        if not names:
            return FactualPlaylistState(
                status=FactualPlaylistStatus.NO_PLAYLIST,
                source=config_json,
            )
        if len(names) > 1:
            return FactualPlaylistState(
                status=FactualPlaylistStatus.AMBIGUOUS,
                source=config_json,
                issue="multiple_wallpaper_playlists",
            )
        return FactualPlaylistState(
            status=FactualPlaylistStatus.PLAYLIST,
            playlist=next(iter(names)),
            source=config_json,
        )

    def scan_playlist_names(self) -> list[str]:
        """Return playlist names declared in WE config.

        Raises:
            WEConfigReadError: When config.json is missing, unreadable, or not a
                JSON object.
        """
        _config_json, data = self._load_config()
        general = _user_general(data)
        if general is None:
            return []

        playlists = general.get("playlists", [])
        if not isinstance(playlists, list):
            return []

        names: list[str] = []
        for playlist in playlists:
            if not isinstance(playlist, dict):
                continue
            name = playlist.get("name")
            if not isinstance(name, str):
                continue
            normalized = name.strip()
            if normalized:
                names.append(normalized)
        return names

    def probe_item_counts(self) -> dict[str, int]:
        """Return wallpaper count per playlist from WE config.

        Raises:
            WEConfigReadError: When config.json is missing, unreadable, or not a
                JSON object.
        """
        _config_json, data = self._load_config()

        general = _user_general(data)
        if general is None:
            return {}

        playlists = general.get("playlists", [])
        if not isinstance(playlists, list):
            return {}

        result: dict[str, int] = {}
        for playlist in playlists:
            if not isinstance(playlist, dict):
                continue
            name = playlist.get("name")
            if not isinstance(name, str):
                continue
            normalized = name.strip()
            if not normalized:
                continue
            items = playlist.get("items")
            if isinstance(items, list):
                result[normalized] = len(items)
        return result

    def _load_config(self) -> tuple[str, dict[str, Any]]:
        """Load WE config.json as a dictionary.

        Raises:
            WEConfigReadError: When config.json is missing, unreadable, or not a
                JSON object.
        """
        config_json = find_we_config_json(self.we_exe_path)
        if config_json is None:
            raise WEConfigReadError("wallpaper_engine_config_not_found")

        try:
            with open(config_json, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            raise WEConfigReadError(
                "wallpaper_engine_config_read_failed",
                config_json,
            ) from exc

        if not isinstance(data, dict):
            raise WEConfigReadError(
                "unexpected_wallpaper_engine_config_format",
                config_json,
            )
        return config_json, data


def _user_general(data: dict[str, Any]) -> dict[str, Any] | None:
    user_entry = data.get(getpass.getuser())
    if not isinstance(user_entry, dict):
        return None
    general = user_entry.get("general")
    if not isinstance(general, dict):
        return None
    return general


def _extract_current_playlist_names(value: Any) -> set[str]:
    if not isinstance(value, dict):
        return set()

    names: set[str] = set()
    for selected_wallpaper in value.values():
        if not isinstance(selected_wallpaper, dict):
            continue

        playlist = selected_wallpaper.get("playlist")
        name = playlist.get("name") if isinstance(playlist, dict) else None
        if not isinstance(name, str):
            continue

        name = name.strip()
        if name:
            names.add(name)

    return names
