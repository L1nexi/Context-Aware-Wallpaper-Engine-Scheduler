# tests/test_scheduler_pipeline.py
from __future__ import annotations

from core.models.scene import SceneId, Scenes
from core.models.trace import Action, ActionResult, ActPlan, Decision, DecisionMode, Match, ScheduleTrace, TickTrace
from core.state.scheduler import SchedulerState


def test_manual_apply_request_is_consumed_once():
    s = SchedulerState()
    s.request_manual_apply()
    assert s.consume_manual_apply_request() is True
    assert s.consume_manual_apply_request() is False


def test_cache_update_only_on_executed_switch():
    """cache_update returns scenes only for executed switch actions."""
    decision = Decision(
        action=Action.SWITCH,
        target=Scenes([SceneId.RAIN]),
    )
    plan = ActPlan(mode=DecisionMode.NORMAL, active_scenes=Scenes([SceneId.DAY_WORK]))
    executed_action = ActionResult(
        target_playlist="X",
        executed=True,
    )
    schedule = ScheduleTrace(
        context=None,
        match=Match(best_scenes=Scenes([SceneId.RAIN])),
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
    assert trace.cache_update == Scenes([SceneId.RAIN])

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
            target=Scenes([SceneId.DAY_WORK]),
        )
        plan = ActPlan(mode=DecisionMode.NORMAL, active_scenes=Scenes([SceneId.DAY_WORK]))
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
                match=Match(best_scenes=Scenes([SceneId.DAY_WORK])),
                plan=plan,
                decision=decision,
                action=action,
            ),
        )
        assert trace.cache_update is None, f"Expected None for {action_kind}"
