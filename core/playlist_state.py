from __future__ import annotations

from dataclasses import dataclass

from core.playlist import Playlists
from utils.we_config import FactualPlaylistState, FactualPlaylistStatus


@dataclass(frozen=True)
class PlaylistStateResolution:
    active_playlists: Playlists
    recovery_needed: bool = False


def resolve_playlist_state(
    factual: FactualPlaylistState,
    cached_playlists: Playlists,
    paused: bool,
) -> PlaylistStateResolution:
    """
    空 active_playlists 表示本 tick 已知 WE 不处于任何可信的 managed playlist 中。
    它不是缓存值。这防止普通调度把过期 cached_playlists 当成当前 playlist。
    """
    if factual.status == FactualPlaylistStatus.PLAYLIST:
        playlist = factual.playlist
        if Playlists.is_managed(playlist):
            if playlist in cached_playlists:
                return PlaylistStateResolution(active_playlists=cached_playlists)
            else:
                return PlaylistStateResolution(active_playlists=Playlists([playlist]))
        else:
            return PlaylistStateResolution(
                active_playlists=Playlists([]),
                recovery_needed=not paused,
            )
    elif factual.status == FactualPlaylistStatus.NO_PLAYLIST:
        return PlaylistStateResolution(
            active_playlists=Playlists([]),
            recovery_needed=not paused,
        )
    else:
        return PlaylistStateResolution(active_playlists=cached_playlists)
