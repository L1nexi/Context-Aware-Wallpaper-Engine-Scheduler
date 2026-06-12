# tests/test_scheduler_pipeline.py
from __future__ import annotations

from core.models.playlist import Playlists
from core.models.trace import Action, ActionResult, ActPlan, Decision, DecisionMode, Match, ScheduleTrace, TickTrace
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
        target=Playlists(["X"]),
    )
    plan = ActPlan(mode=DecisionMode.NORMAL, active_playlists=Playlists(["A"]))
    executed_action = ActionResult(
        target_playlist="X",
        executed=True,
    )
    schedule = ScheduleTrace(
        context=None,
        match=Match(best_playlists=Playlists(["X"])),
        plan=plan,
        decision=decision,
        action=executed_action,
    )
    trace = TickTrace(
        tick_id=1,
        ts=0.0,
        paused=False,
        pause_until=0.0,
        schedule=schedule,
    )
    assert trace.cache_update == Playlists(["X"])

    not_executed_action = ActionResult(
        target_playlist=None,
        executed=False,
    )
    trace2 = TickTrace(
        tick_id=2,
        ts=0.0,
        paused=False,
        pause_until=0.0,
        schedule=ScheduleTrace(
            context=None,
            match=schedule.match,
            plan=plan,
            decision=decision,
            action=not_executed_action,
        ),
    )
    assert trace2.cache_update is None


def test_cache_update_none_for_non_switch():
    """cache_update returns None for hold/cycle/pause actions."""
    for action_kind in (Action.HOLD, Action.CYCLE, Action.PAUSE, Action.NONE):
        decision = Decision(
            action=action_kind,
            target=Playlists(["A"]),
        )
        plan = ActPlan(mode=DecisionMode.NORMAL, active_playlists=Playlists(["A"]))
        action = ActionResult(
            executed=True,
        )
        trace = TickTrace(
            tick_id=1,
            ts=0.0,
            paused=False,
            pause_until=0.0,
            schedule=ScheduleTrace(
                context=None,
                match=Match(best_playlists=Playlists(["A"])),
                plan=plan,
                decision=decision,
                action=action,
            ),
        )
        assert trace.cache_update is None, f"Expected None for {action_kind}"
