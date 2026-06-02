# tests/test_scheduler_pipeline.py
from __future__ import annotations

from core.playlist import Playlists
from core.trace import Action, ActionResult, Decision


class FakeScheduler:
    """Minimal scheduler for testing the pending-manual-apply flow."""

    def __init__(self):
        self._manual_apply_pending = False

    def apply_current_match_now(self) -> None:
        self._manual_apply_pending = True

    def _consume_manual_apply_request(self) -> bool:
        if self._manual_apply_pending:
            self._manual_apply_pending = False
            return True
        return False


def test_apply_current_match_now_sets_pending():
    s = FakeScheduler()
    assert s._manual_apply_pending is False
    s.apply_current_match_now()
    assert s._manual_apply_pending is True


def test_consume_manual_request_returns_true_once():
    s = FakeScheduler()
    s.apply_current_match_now()
    assert s._consume_manual_apply_request() is True
    # Second consume should return False
    assert s._consume_manual_apply_request() is False


def test_consume_without_request_returns_false():
    s = FakeScheduler()
    assert s._consume_manual_apply_request() is False


def test_cache_update_only_on_executed_switch():
    """cache_update returns playlists only for executed switch actions."""
    decision = Decision(
        action=Action.SWITCH,
        reason="switch_allowed",
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
            reason="hold_same_playlist",
            matched=Playlists(["A"]),
        )
        result = ActionResult(
            decision=decision,
            active_playlists_before=Playlists(["A"]),
            active_playlists_after=Playlists(["A"]),
            executed=True,
        )
        assert result.cache_update is None, f"Expected None for {action_kind}"
