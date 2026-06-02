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
    mode = DecisionMode.NORMAL
    active_playlists = cached_playlists

    if manual_requested:
        mode = DecisionMode.MANUAL
    elif paused:
        mode = DecisionMode.PAUSE
    elif factual.status == Status.NO_PLAYLIST:
        mode = DecisionMode.RECOVERY
        active_playlists = Playlists()
    elif factual.status == Status.PLAYLIST:
        playlist = factual.playlist
        if not Playlists.is_managed(playlist):
            mode = DecisionMode.RECOVERY
            active_playlists = Playlists()
        elif playlist not in cached_playlists:
            active_playlists = Playlists([playlist])

    return ActPlan(mode=mode, active_playlists=active_playlists)
