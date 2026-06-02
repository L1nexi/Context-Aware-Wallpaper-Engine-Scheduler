from __future__ import annotations

from dataclasses import dataclass

from core.controller import DecisionMode
from core.playlist import Playlists
from utils.we_config import FactualPlaylistState
from utils.we_config import FactualPlaylistStatus as Status


@dataclass(frozen=True)
class ActPlan:
    mode: DecisionMode
    active_playlists: Playlists


def plan_actuation(
    factual: FactualPlaylistState,
    cached_playlists: Playlists,
    paused: bool,
    manual_requested: bool,
) -> ActPlan:
    if manual_requested:
        return ActPlan(DecisionMode.MANUAL, cached_playlists)

    if paused:
        return ActPlan(DecisionMode.PAUSE, cached_playlists)

    if factual.status == Status.NO_PLAYLIST:
        return ActPlan(DecisionMode.RECOVERY, Playlists())

    if factual.status == Status.PLAYLIST:
        playlist = factual.playlist
        if not Playlists.is_managed(playlist):
            return ActPlan(DecisionMode.RECOVERY, Playlists())
        if playlist in cached_playlists:
            return ActPlan(DecisionMode.NORMAL, cached_playlists)
        return ActPlan(DecisionMode.NORMAL, Playlists([playlist]))

    return ActPlan(DecisionMode.NORMAL, cached_playlists)
