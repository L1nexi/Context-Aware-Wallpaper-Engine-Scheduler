from __future__ import annotations

from core.models.scene import Scenes
from core.models.trace import ActPlan, DecisionMode
from core.runtime.we_config import FactualPlaylistState
from core.runtime.we_config import FactualPlaylistStatus as Status


def plan_actuation(
    factual: FactualPlaylistState,
    cached_scenes: Scenes,
    paused: bool,
    manual_requested: bool,
) -> ActPlan:
    mode = DecisionMode.NORMAL
    active_scenes = cached_scenes.managed_subset()

    if manual_requested:
        mode = DecisionMode.MANUAL
    elif paused:
        mode = DecisionMode.PAUSE
    elif factual.status == Status.NO_PLAYLIST:
        mode = DecisionMode.RECOVERY
        active_scenes = Scenes()
    elif factual.status == Status.PLAYLIST:
        playlist = factual.playlist
        if not Scenes.manages_playlist(playlist):
            mode = DecisionMode.RECOVERY
            active_scenes = Scenes()
        elif not active_scenes.targets_playlist(playlist):
            active_scenes = Scenes.for_playlist(playlist)

    return ActPlan(mode=mode, active_scenes=active_scenes)
