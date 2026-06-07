from __future__ import annotations

from core.models.playlist import Playlists
from core.models.trace import ActPlan, DecisionMode
from core.runtime.we_config import FactualPlaylistState
from core.runtime.we_config import FactualPlaylistStatus as Status


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
