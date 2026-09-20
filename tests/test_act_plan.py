from __future__ import annotations

import pytest

from configurations.runtime_models import SceneConfig
from core.models.scene import SceneId, Scenes
from core.models.trace import DecisionMode
from core.runtime.act_plan import plan_actuation
from core.runtime.we_config import FactualPlaylistState, FactualPlaylistStatus


@pytest.fixture(autouse=True)
def _managed_scenes():
    Scenes.configure(
        {
            SceneId.DAY_WORK: SceneConfig(playlist="A", item_count=5),
            SceneId.DAY_LEISURE: SceneConfig(playlist="A", item_count=5),
            SceneId.NIGHT_WORK: SceneConfig(playlist="B", item_count=3),
            SceneId.RAIN: SceneConfig(playlist="C", item_count=8),
        }
    )
    yield
    Scenes.configure({})


def test_manual_requested_takes_priority_over_paused():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.UNKNOWN),
        cached_scenes=Scenes([SceneId.DAY_WORK]),
        paused=True,
        manual_requested=True,
    )
    assert plan.mode == DecisionMode.MANUAL


def test_paused_takes_priority_over_recovery():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.NO_PLAYLIST),
        cached_scenes=Scenes([SceneId.DAY_WORK]),
        paused=True,
        manual_requested=False,
    )
    assert plan.mode == DecisionMode.PAUSE


def test_no_factual_playlist_triggers_recovery_when_not_paused():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.NO_PLAYLIST),
        cached_scenes=Scenes([SceneId.DAY_WORK]),
        paused=False,
        manual_requested=False,
    )
    assert plan.mode == DecisionMode.RECOVERY


def test_unmanaged_factual_playlist_triggers_recovery():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.PLAYLIST, playlist="Other"),
        cached_scenes=Scenes([SceneId.DAY_WORK]),
        paused=False,
        manual_requested=False,
    )
    assert plan.mode == DecisionMode.RECOVERY
    assert plan.active_scenes == Scenes()


def test_factual_playlist_targeted_by_cached_scene_preserves_cached_pool():
    cached = Scenes([SceneId.DAY_WORK, SceneId.NIGHT_WORK])

    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.PLAYLIST, playlist="A"),
        cached_scenes=cached,
        paused=False,
        manual_requested=False,
    )

    assert plan.mode == DecisionMode.NORMAL
    assert plan.active_scenes == cached


def test_factual_playlist_outside_cache_recovers_every_assigned_scene():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.PLAYLIST, playlist="A"),
        cached_scenes=Scenes([SceneId.RAIN]),
        paused=False,
        manual_requested=False,
    )

    assert plan.active_scenes == Scenes([SceneId.DAY_WORK, SceneId.DAY_LEISURE])


@pytest.mark.parametrize("status", [FactualPlaylistStatus.UNKNOWN, FactualPlaylistStatus.AMBIGUOUS])
def test_unknown_factual_state_preserves_cached_scenes(status: FactualPlaylistStatus):
    cached = Scenes([SceneId.DAY_WORK, SceneId.NIGHT_WORK])

    plan = plan_actuation(
        factual=FactualPlaylistState(status=status),
        cached_scenes=cached,
        paused=False,
        manual_requested=False,
    )

    assert plan.mode == DecisionMode.NORMAL
    assert plan.active_scenes == cached


def test_cached_scene_removed_from_runtime_is_discarded():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.UNKNOWN),
        cached_scenes=Scenes([SceneId.WINTER]),
        paused=False,
        manual_requested=False,
    )

    assert plan.active_scenes == Scenes()
