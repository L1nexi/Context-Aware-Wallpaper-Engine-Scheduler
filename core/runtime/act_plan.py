from __future__ import annotations

import logging

from core.models.playlist import Playlists
from core.models.trace import ActPlan, DecisionMode
from core.runtime.we_config import FactualPlaylistState
from core.runtime.we_config import FactualPlaylistStatus as Status

logger = logging.getLogger("WEScheduler.ActPlan")


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
        logger.info("Manual apply requested")
    elif paused:
        mode = DecisionMode.PAUSE
    elif factual.status == Status.NO_PLAYLIST:
        mode = DecisionMode.RECOVERY
        active_playlists = Playlists()
        logger.info("Recovery mode: %s", factual.status.value)
    elif factual.status == Status.PLAYLIST:
        playlist = factual.playlist
        if not Playlists.is_managed(playlist):
            mode = DecisionMode.RECOVERY
            active_playlists = Playlists()
            logger.info("Recovery mode: unmanaged playlist '%s'", playlist)
        elif playlist not in cached_playlists:
            active_playlists = Playlists([playlist])

    return ActPlan(mode=mode, active_playlists=active_playlists)
