from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from core.playlist import Playlists
from utils.we_config import FactualPlaylistState, FactualPlaylistStatus


class PlaylistRecoveryReason(StrEnum):
    NO_PLAYLIST = "recovery_no_playlist"
    UNMANAGED_PLAYLIST = "recovery_unmanaged_playlist"


@dataclass(frozen=True)
class PlaylistStateResolution:
    effective_playlists: Playlists
    recovery_needed: bool = False
    recovery_reason: PlaylistRecoveryReason | None = None


def resolve_playlist_state(
    factual: FactualPlaylistState,
    cached_playlists: Playlists,
    paused: bool,
) -> PlaylistStateResolution:
    """
    空 effective_playlists 表示本 tick 已知 WE 不处于任何可信的 managed playlist 中。
    它不是缓存值。这防止普通调度把过期 cached_playlists 当成当前 playlist。
    """
    if factual.status == FactualPlaylistStatus.PLAYLIST:
        playlist = factual.playlist
        if Playlists.is_managed(playlist):
            return PlaylistStateResolution(
                effective_playlists=Playlists([playlist]),
            )
        return PlaylistStateResolution(
            effective_playlists=Playlists([]),
            recovery_needed=not paused,
            recovery_reason=PlaylistRecoveryReason.UNMANAGED_PLAYLIST,
        )

    if factual.status == FactualPlaylistStatus.NO_PLAYLIST:
        return PlaylistStateResolution(
            effective_playlists=Playlists([]),
            recovery_needed=not paused,
            recovery_reason=PlaylistRecoveryReason.NO_PLAYLIST,
        )

    return PlaylistStateResolution(
        effective_playlists=cached_playlists,
    )
