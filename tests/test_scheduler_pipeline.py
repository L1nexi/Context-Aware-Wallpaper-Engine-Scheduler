# tests/test_scheduler_pipeline.py
from __future__ import annotations

from core.models.playlist import Playlists
from core.models.trace import Action, ActionReason, ActionResult, Decision
from core.state.scheduler import SchedulerState


def test_manual_apply_request_is_consumed_once():
    s = SchedulerState()
    s.request_manual_apply()
    assert s.consume_manual_apply_request() is True
    assert s.consume_manual_apply_request() is False


def test_consume_without_request_returns_false():
    s = SchedulerState()
    assert s.consume_manual_apply_request() is False


def test_cache_update_only_on_executed_switch():
    """cache_update returns playlists only for executed switch actions."""
    decision = Decision(
        action=Action.SWITCH,
        reason=ActionReason.SWITCH_ALLOWED,
        matched=Playlists(["X"]),
    )
    executed = ActionResult(
        decision=decision,
        active_playlists_before=Playlists(["A"]),
        active_playlists_after=Playlists(["X"]),
        target_playlist="X",
        executed=True,
    )
    assert executed.cache_update == Playlists(["X"])

    not_executed = ActionResult(
        decision=decision,
        active_playlists_before=Playlists(["A"]),
        active_playlists_after=Playlists(["A"]),
        target_playlist=None,
        executed=False,
    )
    assert not_executed.cache_update is None


def test_cache_update_none_for_non_switch():
    """cache_update returns None for hold/cycle/pause actions."""
    for action_kind in (Action.HOLD, Action.CYCLE, Action.PAUSE, Action.NONE):
        decision = Decision(
            action=action_kind,
            reason=ActionReason.HOLD_SAME_PLAYLIST,
            matched=Playlists(["A"]),
        )
        result = ActionResult(
            decision=decision,
            active_playlists_before=Playlists(["A"]),
            active_playlists_after=Playlists(["A"]),
            executed=True,
        )
        assert result.cache_update is None, f"Expected None for {action_kind}"
