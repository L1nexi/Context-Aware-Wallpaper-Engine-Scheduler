from __future__ import annotations

import pytest

from core.act_plan import plan_actuation
from core.controller import DecisionMode
from core.playlist import PlaylistInfo, Playlists
from utils.we_config import FactualPlaylistState, FactualPlaylistStatus


@pytest.fixture(autouse=True)
def _managed_playlists():
    """Register A, B, C as managed playlists for all tests."""
    Playlists._configs = {
        "A": PlaylistInfo(display="A", color="#ffffff", item_count=5),
        "B": PlaylistInfo(display="B", color="#aaaaaa", item_count=3),
        "C": PlaylistInfo(display="C", color="#bbbbbb", item_count=8),
    }
    yield
    Playlists._configs = {}


# --- Mode priority tests ---


def test_manual_requested_takes_priority_over_paused():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.UNKNOWN),
        cached_playlists=Playlists(["A"]),
        paused=True,
        manual_requested=True,
    )
    assert plan.mode == DecisionMode.MANUAL


def test_paused_takes_priority_over_recovery():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.NO_PLAYLIST),
        cached_playlists=Playlists(["A"]),
        paused=True,
        manual_requested=False,
    )
    assert plan.mode == DecisionMode.PAUSE


def test_unmanaged_triggers_recovery_when_not_paused():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.NO_PLAYLIST),
        cached_playlists=Playlists(["A"]),
        paused=False,
        manual_requested=False,
    )
    assert plan.mode == DecisionMode.RECOVERY


def test_unmanaged_playlist_triggers_recovery():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.PLAYLIST, playlist="Other"),
        cached_playlists=Playlists(["A"]),
        paused=False,
        manual_requested=False,
    )
    assert plan.mode == DecisionMode.RECOVERY


def test_normal_when_factual_managed():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.PLAYLIST, playlist="A"),
        cached_playlists=Playlists(["A"]),
        paused=False,
        manual_requested=False,
    )
    assert plan.mode == DecisionMode.NORMAL


def test_factual_ambiguous_returns_cached_and_normal():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.AMBIGUOUS),
        cached_playlists=Playlists(["A", "B"]),
        paused=False,
        manual_requested=False,
    )
    assert plan.mode == DecisionMode.NORMAL
    assert plan.active_playlists == Playlists(["A", "B"])


# --- active_playlists derivation tests ---


def test_factual_managed_in_cache_preserves_pool():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.PLAYLIST, playlist="A"),
        cached_playlists=Playlists(["A", "B"]),
        paused=False,
        manual_requested=False,
    )
    assert plan.active_playlists == Playlists(["A", "B"])


def test_factual_managed_not_in_cache_returns_single():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.PLAYLIST, playlist="C"),
        cached_playlists=Playlists(["A", "B"]),
        paused=False,
        manual_requested=False,
    )
    assert plan.active_playlists == Playlists(["C"])


def test_factual_unmanaged_returns_empty():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.NO_PLAYLIST),
        cached_playlists=Playlists(["A"]),
        paused=False,
        manual_requested=False,
    )
    assert plan.active_playlists == Playlists()


def test_factual_unknown_returns_cached():
    plan = plan_actuation(
        factual=FactualPlaylistState(status=FactualPlaylistStatus.UNKNOWN),
        cached_playlists=Playlists(["A", "B"]),
        paused=False,
        manual_requested=False,
    )
    assert plan.active_playlists == Playlists(["A", "B"])
