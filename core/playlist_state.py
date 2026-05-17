from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from utils.we_config import FactualPlaylistState, FactualPlaylistStatus


class PlaylistRecoveryReason(StrEnum):
    NO_PLAYLIST = "recovery_no_playlist"
    UNMANAGED_PLAYLIST = "recovery_unmanaged_playlist"


@dataclass(frozen=True)
class PlaylistStateResolution:
    effective_playlist: str
    recovery_needed: bool = False
    recovery_reason: PlaylistRecoveryReason | None = None


def resolve_playlist_state(
    factual: FactualPlaylistState,
    cached_playlist: str,
    managed_playlists: set[str],
    paused: bool,
) -> PlaylistStateResolution:
    """空 effective_playlist 表示本 tick 已知 WE 不处于任何可信的 managed playlist 中。
    它不是缓存值，而是防止普通调度把过期 cached_playlist 当成当前 playlist。
    """
    if factual.status == FactualPlaylistStatus.PLAYLIST:
        playlist = factual.playlist
        if playlist in managed_playlists:
            return PlaylistStateResolution(
                effective_playlist=playlist,    # Factual managed playlist
            )
        return PlaylistStateResolution(
            effective_playlist="",
            recovery_needed=not paused,
            recovery_reason=PlaylistRecoveryReason.UNMANAGED_PLAYLIST,
        )

    if factual.status == FactualPlaylistStatus.NO_PLAYLIST:
        return PlaylistStateResolution(
            effective_playlist="",
            recovery_needed=not paused,
            recovery_reason=PlaylistRecoveryReason.NO_PLAYLIST,
        )

    return PlaylistStateResolution(
        effective_playlist=cached_playlist,     # Unknown/Ambiguous
    )
