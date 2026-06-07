from __future__ import annotations

import logging
from unittest import mock

import pytest

from configurations.runtime_models import (
    ActivityPolicyConfig,
    PlaylistConfig,
    SchedulingConfig,
    TagSpec,
    TimePolicyConfig,
    WeatherPolicyConfig,
)
from core.models.context import Context, WindowData
from core.models.event import EventType
from core.models.playlist import PlaylistInfo, Playlists
from core.models.trace import (
    Action,
    ActionReason,
    ActionResult,
    ActivityDetails,
    ActivityEvaluation,
    Blocker,
    BlockerEvaluation,
    Decision,
    Match,
    ThinkResult,
    TickTrace,
)
from core.policies import ActivityPolicy, TimePolicy, WeatherPolicy
from core.models.trace import ActPlan, DecisionMode
from core.runtime.actuator import Actuator
from core.runtime.controller import CONTINUITY_DECAY_PER_TICK, Intent, SchedulingController, weighted_jaccard
from core.runtime.engine import Engine, _BuiltEngine
from core.runtime.matcher import Matcher
from core.runtime.scheduler import WEScheduler
from core.runtime.we_config import FactualPlaylistState, FactualPlaylistStatus
from core.state.action_history import ActionHistoryWriter
from core.state.persisted import PersistedState
from ui.dashboard_analysis import map_tick_snapshot


@pytest.fixture(autouse=True)
def _configure_playlists():
    Playlists._configs = {
        "focus": PlaylistInfo(display="Focus Flow", color="#F5C518", item_count=10),
        "rain": PlaylistInfo(display="Rain", color="#2563EB", item_count=5),
        "A": PlaylistInfo(display="A", color="#FF0000", item_count=10),
        "B": PlaylistInfo(display="B", color="#00FF00", item_count=40),
        "C": PlaylistInfo(display="C", color="#0000FF", item_count=0),
        "STRONG": PlaylistInfo(display="STRONG", color="#FF0000", item_count=0),
        "WEAK": PlaylistInfo(display="WEAK", color="#00FF00", item_count=0),
        **{f"P{i}": PlaylistInfo(display=f"P{i}", color="#FF0000", item_count=0) for i in range(6)},
    }
    yield
    Playlists._configs = {}


class _MutableClock:
    def __init__(self, now: float):
        self.now = now

    def __call__(self) -> float:
        return self.now


def _allowed_gate() -> BlockerEvaluation:
    return BlockerEvaluation()


def _blocked_gate(blocker: Blocker = Blocker.IDLE) -> BlockerEvaluation:
    return BlockerEvaluation(blocked_by=[blocker])


def test_activity_policy_distinguishes_title_and_process_matchers():
    policy = ActivityPolicy(
        ActivityPolicyConfig(
            smoothing_window=1,
            matchers=[
                {
                    "source": "process",
                    "match": "exact",
                    "pattern": "chrome.exe",
                    "tag": "focus",
                },
                {
                    "source": "title",
                    "match": "contains",
                    "pattern": "YouTube",
                    "tag": "chill",
                },
            ],
        )
    )

    title_eval = policy.evaluate(Context(window=WindowData(title="YouTube Music", process="chrome.exe")))
    assert title_eval.active is True
    assert title_eval.details.match_source == "title"
    assert title_eval.details.matched_rule == "YouTube"
    assert title_eval.dominant_tag == "chill"

    process_eval = policy.evaluate(Context(window=WindowData(title="Docs", process="chrome.exe")))
    assert process_eval.active is True
    assert process_eval.details.match_source == "process"
    assert process_eval.details.matched_rule == "chrome.exe"
    assert process_eval.dominant_tag == "focus"


def test_time_policy_outputs_plain_tag_ids():
    policy = TimePolicy(
        TimePolicyConfig(
            enabled=True,
            weight=1.0,
            auto=False,
            day_start_hour=8,
            night_start_hour=20,
        )
    )

    evaluation = policy.evaluate(Context(time=mock.Mock(tm_hour=9, tm_min=0, tm_yday=120)))

    assert evaluation.active is True
    assert evaluation.raw_contribution
    assert all(not tag.startswith("#") for tag in evaluation.raw_contribution)


def test_weather_policy_without_weather_is_inactive():
    policy = WeatherPolicy(WeatherPolicyConfig(api_key="abc"))

    evaluation = policy.evaluate(Context(weather=None))

    assert evaluation.enabled is True
    assert evaluation.active is False
    assert evaluation.details.available is False
    assert evaluation.details.mapped is False
    assert evaluation.raw_contribution == {}


def _decide_normal(
    controller: SchedulingController,
    context: Context,
    match: Match,
    active_playlists: Playlists,
):
    plan = ActPlan(mode=DecisionMode.NORMAL, active_playlists=active_playlists)
    return controller.decide_action(plan, context, match)


def test_matcher_preserves_raw_resolved_and_fallback_vectors():
    stub_policy = mock.Mock()
    stub_policy.evaluate.return_value = ActivityEvaluation(
        policy_id="stub",
        enabled=True,
        active=True,
        weight=1.0,
        salience=1.0,
        intensity=1.0,
        effective_magnitude=1.0,
        direction={"stormy": 1.0},
        raw_contribution={"stormy": 1.0},
        details=ActivityDetails(),
    )

    matcher = Matcher(
        playlist_configs={"focus": PlaylistConfig(color="#F5C518", tags={"focus": 1.0})},
        policies=[stub_policy],
        tag_specs={"stormy": TagSpec(fallback={"focus": 1.0})},
    )

    evaluation = matcher.match(Context())

    assert evaluation.raw_context_vector == {"stormy": 1.0}
    assert evaluation.resolved_context_vector == {"focus": 1.0}
    assert evaluation.best_playlists == Playlists(["focus"])
    assert evaluation.fallback_expansions == {"stormy": {"focus": 1.0}}
    assert evaluation.policy_evaluations[0].resolved_contribution == {"focus": 1.0}


def test_diagnostics_snapshot_uses_playlist_metadata_from_runtime_map():
    trace = TickTrace(
        tick_id=1,
        ts=1.0,
        paused=False,
        pause_until=0.0,
        context=Context(window=WindowData(title="Docs", process="Code.exe")),
        think=ThinkResult(
            match=Match(
                best_playlists=Playlists(["focus"]),
                playlist_matches=[("focus", 0.9)],
                raw_context_vector={"focus": 1.0},
                resolved_context_vector={"focus": 1.0},
                policy_evaluations=[],
            ),
            decision=Decision(
                action=Action.HOLD,
                reason=ActionReason.HOLD_SAME_PLAYLIST,
                target=Playlists(["focus"]),
                evaluation=None,
            ),
            plan=ActPlan(mode=DecisionMode.NORMAL, active_playlists=Playlists(["focus"])),
        ),
        action=ActionResult(
            executed=False,
        ),
    )

    snapshot = map_tick_snapshot(trace).model_dump(mode="json", by_alias=True)

    assert snapshot["summary"]["matchedPlaylists"] == [
        {"name": "focus", "display": "Focus Flow", "color": "#F5C518"},
    ]


def test_controller_evaluation_reports_all_blockers():
    clock = _MutableClock(200.0)
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=0,
            force_after=100,
            cycle_cooldown=15,
            idle_threshold=60,
            cpu_threshold=80,
            cpu_sample_window=1,
            pause_on_fullscreen=True,
        ),
        clock=clock,
    )
    controller.last_action_time = 195.0

    context = Context(idle=10.0, cpu=90.0, fullscreen=True)
    switch_decision = _decide_normal(
        controller,
        context,
        Match(best_playlists=Playlists(["rain"]), playlist_matches=[("rain", 0.8)]),
        Playlists(["focus"]),
    )
    cycle_decision = _decide_normal(
        controller,
        context,
        Match(best_playlists=Playlists(["focus"]), playlist_matches=[("focus", 0.8)]),
        Playlists(["focus"]),
    )
    switch_eval = switch_decision.evaluation
    cycle_eval = cycle_decision.evaluation

    assert switch_eval.allowed is False
    assert switch_eval.cooldown_remaining == pytest.approx(0.0)
    assert switch_eval.force_after_remaining == pytest.approx(95.0)
    assert set(switch_eval.blocked_by) == {
        Blocker.CPU,
        Blocker.FULLSCREEN,
        Blocker.IDLE,
    }

    assert cycle_eval.allowed is False
    assert cycle_eval.cooldown_remaining == pytest.approx(10.0)
    assert set(cycle_eval.blocked_by) == {
        Blocker.COOLDOWN,
        Blocker.CPU,
        Blocker.FULLSCREEN,
        Blocker.IDLE,
    }


def test_controller_warmup_blocks_all_operations():
    """During startup warmup, both switch and cycle are blocked by COOLDOWN,
    and context gates (CPU, fullscreen) are still collected."""
    clock = _MutableClock(100.0)
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=30,
            force_after=100,
            cycle_cooldown=15,
            idle_threshold=60,
            cpu_threshold=80,
            cpu_sample_window=1,
            pause_on_fullscreen=True,
        ),
        clock=clock,
    )
    # t=105: 5s into 30s warmup
    clock.now = 105.0

    context = Context(idle=120.0, cpu=90.0, fullscreen=True)

    switch_decision = _decide_normal(
        controller,
        context,
        Match(best_playlists=Playlists(["rain"]), playlist_matches=[("rain", 0.8)]),
        Playlists(["focus"]),
    )
    cycle_decision = _decide_normal(
        controller,
        context,
        Match(best_playlists=Playlists(["focus"]), playlist_matches=[("focus", 0.8)]),
        Playlists(["focus"]),
    )

    switch_eval = switch_decision.evaluation
    cycle_eval = cycle_decision.evaluation

    # Both blocked despite user being idle (idle=120 >= threshold=60)
    assert switch_eval.allowed is False
    assert Blocker.COOLDOWN in switch_eval.blocked_by
    assert Blocker.IDLE not in switch_eval.blocked_by
    assert switch_eval.cooldown_remaining == pytest.approx(25.0)

    assert cycle_eval.allowed is False
    assert Blocker.COOLDOWN in cycle_eval.blocked_by
    assert Blocker.IDLE not in cycle_eval.blocked_by
    assert cycle_eval.cooldown_remaining == pytest.approx(25.0)

    # Context gates still collected
    assert Blocker.CPU in switch_eval.blocked_by
    assert Blocker.FULLSCREEN in switch_eval.blocked_by


def test_controller_warmup_switch_reason_code():
    """During warmup, a switch decision should report SWITCH_BLOCKED_COOLDOWN."""
    clock = _MutableClock(100.0)
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=30,
            force_after=100,
            cycle_cooldown=15,
            idle_threshold=60,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        ),
        clock=clock,
    )
    clock.now = 105.0

    decision = _decide_normal(
        controller,
        Context(idle=120.0, cpu=1.0),
        Match(best_playlists=Playlists(["rain"]), playlist_matches=[("rain", 0.8)]),
        Playlists(["focus"]),
    )

    assert decision.reason == ActionReason.SWITCH_BLOCKED_COOLDOWN
    assert decision.evaluation.cooldown_remaining == pytest.approx(25.0)


def test_controller_warmup_expires_normal_behavior():
    """After warmup expires, switches proceed with normal idle/force_after logic."""
    clock = _MutableClock(100.0)
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=10,
            force_after=100,
            cycle_cooldown=15,
            idle_threshold=60,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        ),
        clock=clock,
    )
    # t=120: well past 10s warmup, user idle for 80s
    clock.now = 120.0

    decision = _decide_normal(
        controller,
        Context(idle=80.0, cpu=1.0),
        Match(best_playlists=Playlists(["rain"]), playlist_matches=[("rain", 0.8)]),
        Playlists(["focus"]),
    )

    assert decision.action == Action.SWITCH
    assert decision.reason == ActionReason.SWITCH_ALLOWED
    assert Blocker.COOLDOWN not in decision.evaluation.blocked_by
    assert decision.evaluation.cooldown_remaining == pytest.approx(0.0)


def test_controller_switch_has_no_cooldown_gate():
    """Two consecutive switches are not blocked by a cooldown gate."""
    clock = _MutableClock(100.0)
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=0,
            force_after=3600,
            cycle_cooldown=900,
            idle_threshold=10,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        ),
        clock=clock,
    )
    # First switch at t=100
    controller.last_action_time = 100.0

    # Second switch at t=101 — should NOT be blocked by cooldown
    clock.now = 101.0
    evaluation = controller._evaluate_blockers(
        Context(idle=20.0, cpu=1.0),
        intent=Intent.SWITCH,
    )

    assert Blocker.COOLDOWN not in evaluation.blocked_by
    assert evaluation.cooldown_remaining == pytest.approx(0.0)
    assert evaluation.allowed is True


def test_controller_switch_force_after_overrides_idle():
    clock = _MutableClock(500.0)
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=0,
            force_after=100,
            cycle_cooldown=15,
            idle_threshold=60,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        ),
        clock=clock,
    )
    controller.last_action_time = 390.0

    decision = _decide_normal(
        controller,
        Context(idle=5.0, cpu=1.0),
        Match(best_playlists=Playlists(["rain"]), playlist_matches=[("rain", 0.8)]),
        Playlists(["focus"]),
    )
    evaluation = decision.evaluation

    assert decision.reason == ActionReason.SWITCH_ALLOWED
    assert evaluation.allowed is True
    assert evaluation.blocked_by == []
    assert evaluation.force_after_remaining == pytest.approx(0.0)


def test_controller_partial_overlap_keeps_active_pool_for_reference_window():
    Playlists._configs.update(
        {
            "A": PlaylistInfo(display="A", color="#FF0000", item_count=1),
            "B": PlaylistInfo(display="B", color="#00FF00", item_count=1),
            "C": PlaylistInfo(display="C", color="#0000FF", item_count=1),
        }
    )
    clock = _MutableClock(1000.0)
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=0,
            force_after=0,
            cycle_cooldown=0,
            idle_threshold=0,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        ),
        clock=clock,
    )
    active = Playlists(["A", "B"])
    matched = Match(best_playlists=Playlists(["A", "C"]), playlist_matches=[("A", 0.9), ("C", 0.8)])

    for _ in range(119):
        decision = _decide_normal(controller, Context(idle=999.0), matched, active)
        assert decision.action != Action.SWITCH
        assert decision.reason != ActionReason.SWITCH_ALLOWED

    decision = _decide_normal(controller, Context(idle=999.0), matched, active)

    assert decision.action == Action.SWITCH
    assert decision.reason == ActionReason.SWITCH_ALLOWED


def test_controller_partial_overlap_decays_continuity_by_time_only():
    Playlists._configs.update(
        {
            "A": PlaylistInfo(display="A", color="#FF0000", item_count=1),
            "B": PlaylistInfo(display="B", color="#00FF00", item_count=1),
            "C": PlaylistInfo(display="C", color="#0000FF", item_count=1),
        }
    )
    clock = _MutableClock(1000.0)
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=0,
            force_after=0,
            cycle_cooldown=0,
            idle_threshold=0,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        ),
        clock=clock,
    )

    _decide_normal(
        controller,
        Context(idle=999.0),
        Match(best_playlists=Playlists(["A", "C"]), playlist_matches=[("A", 0.9), ("C", 0.8)]),
        Playlists(["A", "B"]),
    )

    assert controller.semantic_continuity_score == pytest.approx(CONTINUITY_DECAY_PER_TICK)


def test_controller_no_match_resets_continuity_without_switching():
    clock = _MutableClock(1000.0)
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=0,
            force_after=0,
            cycle_cooldown=0,
            idle_threshold=0,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        ),
        clock=clock,
    )

    decision = _decide_normal(
        controller,
        Context(idle=999.0),
        Match(best_playlists=Playlists()),
        Playlists(["focus"]),
    )

    assert decision.action == Action.HOLD
    assert decision.reason == ActionReason.NO_MATCH
    assert controller.semantic_continuity_score == pytest.approx(0.0)


def test_controller_semantic_overlap_uses_sqrt_item_count_weights():
    Playlists._configs.update(
        {
            "A": PlaylistInfo(display="A", color="#FF0000", item_count=100),
            "B": PlaylistInfo(display="B", color="#00FF00", item_count=1),
            "C": PlaylistInfo(display="C", color="#0000FF", item_count=1),
        }
    )
    assert weighted_jaccard(Playlists(["A", "C"]), Playlists(["A", "B"])) == pytest.approx(10 / 12)


def test_controller_notify_executed_resets_continuity_for_switch():
    clock = _MutableClock(2000.0)
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=0,
            force_after=0,
            cycle_cooldown=0,
            idle_threshold=0,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        ),
        clock=clock,
    )
    controller.semantic_continuity_score = 0.42

    controller.notify_executed(
        Decision(
            action=Action.SWITCH,
            reason=ActionReason.SWITCH_ALLOWED,
            target=Playlists(["rain"]),
        )
    )

    assert controller.last_action_time == pytest.approx(2000.0)
    assert controller.semantic_continuity_score == pytest.approx(1.0)


def test_controller_notify_executed_preserves_continuity_for_plain_cycle():
    clock = _MutableClock(2000.0)
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=0,
            force_after=0,
            cycle_cooldown=0,
            idle_threshold=0,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        ),
        clock=clock,
    )
    controller.semantic_continuity_score = 0.42

    controller.notify_executed(
        Decision(
            action=Action.CYCLE,
            reason=ActionReason.CYCLE_ALLOWED,
            target=Playlists(["focus"]),
        )
    )

    assert controller.last_action_time == pytest.approx(2000.0)
    assert controller.semantic_continuity_score == pytest.approx(0.42)


def test_controller_notify_executed_resets_continuity_for_manual_cycle():
    clock = _MutableClock(2000.0)
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=0,
            force_after=0,
            cycle_cooldown=0,
            idle_threshold=0,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        ),
        clock=clock,
    )
    controller.semantic_continuity_score = 0.42

    controller.notify_executed(
        Decision(
            action=Action.CYCLE,
            reason=ActionReason.MANUAL_APPLY_REQUESTED,
            target=Playlists(["focus"]),
        )
    )

    assert controller.last_action_time == pytest.approx(2000.0)
    assert controller.semantic_continuity_score == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("match", "active_playlists", "switch_eval", "cycle_eval", "expected"),
    [
        (
            Match(best_playlists=Playlists()),
            Playlists(["focus"]),
            _blocked_gate(),
            _blocked_gate(),
            ActionReason.NO_MATCH,
        ),
        (
            Match(best_playlists=Playlists(["rain"]), playlist_matches=[("rain", 0.8), ("focus", 0.6)]),
            Playlists(["focus"]),
            _allowed_gate(),
            _blocked_gate(),
            ActionReason.SWITCH_ALLOWED,
        ),
        (
            Match(best_playlists=Playlists(["focus"]), playlist_matches=[("focus", 0.8), ("rain", 0.6)]),
            Playlists(["focus"]),
            _blocked_gate(),
            _allowed_gate(),
            ActionReason.CYCLE_ALLOWED,
        ),
        (
            Match(best_playlists=Playlists(["focus"]), playlist_matches=[("focus", 0.8), ("rain", 0.6)]),
            Playlists(["focus"]),
            _blocked_gate(),
            _blocked_gate(Blocker.CPU),
            ActionReason.CYCLE_BLOCKED_CPU,
        ),
    ],
)
def test_controller_decide_reason_code(
    match,
    active_playlists,
    switch_eval,
    cycle_eval,
    expected,
):
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=0,
            force_after=100,
            cycle_cooldown=15,
            idle_threshold=60,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        )
    )
    controller._evaluate_blockers = mock.Mock(side_effect=lambda _context, operation: switch_eval if operation == "switch" else cycle_eval)

    decision = _decide_normal(controller, Context(), match, active_playlists)

    assert decision.reason == expected


def test_controller_recovery_uses_unmanaged_reason_without_gates():
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=30,
            force_after=100,
            cycle_cooldown=15,
            idle_threshold=60,
            cpu_threshold=80,
            pause_on_fullscreen=True,
        )
    )
    controller._evaluate_blockers = mock.Mock()

    plan = ActPlan(mode=DecisionMode.RECOVERY, active_playlists=Playlists())
    decision = controller.decide_action(
        plan,
        Context(),
        Match(best_playlists=Playlists(["rain"]), playlist_matches=[("rain", 0.8)]),
    )

    assert decision.action == Action.SWITCH
    assert decision.reason == ActionReason.RECOVERY_UNMANAGED
    assert decision.evaluation is None
    controller._evaluate_blockers.assert_not_called()


def test_controller_recovery_without_match_does_not_switch():
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=0,
            force_after=100,
            cycle_cooldown=15,
            idle_threshold=60,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        )
    )

    plan = ActPlan(mode=DecisionMode.RECOVERY, active_playlists=Playlists())
    decision = controller.decide_action(
        plan,
        Context(),
        Match(best_playlists=Playlists()),
    )

    assert decision.action == Action.NONE
    assert decision.reason == ActionReason.RECOVERY_NO_MATCH


def test_actuator_switch_returns_executed_outcome():
    executor = mock.Mock()
    actuator = Actuator(executor)
    decision = Decision(
        action=Action.SWITCH,
        reason=ActionReason.SWITCH_ALLOWED,
        target=Playlists(["rain"]),
    )
    outcome = actuator.act(decision)

    assert outcome.executed is True
    assert outcome.target_playlist == "rain"
    executor.open_playlist.assert_called_once_with("rain")


def test_scheduler_history_recorder_logs_switch_event():
    history = mock.Mock()
    recorder = ActionHistoryWriter(history)
    decision = Decision(
        action=Action.SWITCH,
        reason=ActionReason.SWITCH_ALLOWED,
        target=Playlists(["rain"]),
    )
    match = Match(
        best_playlists=Playlists(["rain"]),
        playlist_matches=[("rain", 0.9), ("focus", 0.5)],
        raw_context_vector={"rain": 1.0},
        resolved_context_vector={"rain": 1.0},
        max_policy_magnitude=1.0,
        similarity=0.9,
        similarity_gap=0.4,
    )
    plan = ActPlan(mode=DecisionMode.NORMAL, active_playlists=Playlists(["focus"]))
    think = ThinkResult(match=match, decision=decision, plan=plan)
    action = ActionResult(
        target_playlist="rain",
        executed=True,
    )
    trace = TickTrace(
        tick_id=1,
        ts=123.0,
        paused=False,
        pause_until=0.0,
        context=Context(),
        think=think,
        action=action,
    )

    recorder.on_tick(trace)

    history.write.assert_called_once()
    assert history.write.call_args.args[0] == EventType.PLAYLISTS_SWITCH
    assert history.write.call_args.args[1]["reason_code"] == "switch_allowed"
    assert history.write.call_args.args[1]["playlists_to"] == ["rain"]
    assert history.write.call_args.args[1]["target_playlist"] == "rain"


def test_actuator_switch_preserves_matched_pool_after_execution(monkeypatch):
    monkeypatch.setattr("core.models.playlist.random.choices", lambda names, weights=None, k=1: ["A"])
    executor = mock.Mock()
    matched_pool = Playlists(["A", "B"])
    actuator = Actuator(executor)
    decision = Decision(
        action=Action.SWITCH,
        reason=ActionReason.SWITCH_ALLOWED,
        target=matched_pool,
    )

    outcome = actuator.act(decision)

    assert outcome.executed is True
    assert outcome.target_playlist == "A"
    executor.open_playlist.assert_called_once_with("A")


def test_actuator_cycle_uses_open_playlist_without_next_wallpaper(monkeypatch):
    monkeypatch.setattr("core.models.playlist.random.choices", lambda names, weights=None, k=1: ["A"])
    executor = mock.Mock()
    matched_pool = Playlists(["A", "B"])
    actuator = Actuator(executor)
    decision = Decision(
        action=Action.CYCLE,
        reason=ActionReason.CYCLE_ALLOWED,
        target=matched_pool,
    )

    outcome = actuator.act(decision)

    assert outcome.executed is True
    assert outcome.target_playlist == "A"
    executor.open_playlist.assert_called_once_with("A")
    executor.next_wallpaper.assert_not_called()


def test_actuator_cycle_selects_from_matched_pool(monkeypatch):
    monkeypatch.setattr("core.models.playlist.random.choices", lambda names, weights=None, k=1: [names[0]])
    executor = mock.Mock()
    actuator = Actuator(executor)
    decision = Decision(
        action=Action.CYCLE,
        reason=ActionReason.CYCLE_ALLOWED,
        target=Playlists(["A", "C"]),
    )

    outcome = actuator.act(decision)

    assert outcome.executed is True
    assert outcome.target_playlist == "A"
    executor.open_playlist.assert_called_once_with("A")


def test_actuator_recovery_switch_bypasses_controller_gates():
    executor = mock.Mock()
    actuator = Actuator(executor)
    decision = Decision(
        action=Action.SWITCH,
        reason=ActionReason.RECOVERY_UNMANAGED,
        target=Playlists(["rain"]),
    )

    outcome = actuator.act(decision)

    assert outcome.executed is True
    assert outcome.target_playlist == "rain"
    executor.open_playlist.assert_called_once_with("rain")


def test_scheduler_paused_does_not_ensure_we_alive():
    class DummyHistory:
        def write(self, *_args, **_kwargs):
            return 0

    scheduler = WEScheduler("config", DummyHistory())
    engine = Engine("config")
    engine.context_manager = mock.Mock()
    engine.context_manager.sense.return_value = Context(window=WindowData(title="", process=""), idle=0.0)
    engine.executor = mock.Mock()
    engine.we_config_prober = mock.Mock(probe_playlist=mock.Mock(return_value=FactualPlaylistState(FactualPlaylistStatus.UNKNOWN)))
    engine.ensure_we_alive = mock.Mock()
    scheduler.engine = engine
    scheduler.state.cached_playlists = Playlists(["focus"])
    scheduler.state.paused = True
    engine.actuator = mock.Mock()
    engine.actuator.act.return_value = ActionResult(
        executed=False,
    )

    pause_plan = ActPlan(mode=DecisionMode.PAUSE, active_playlists=Playlists(["focus"]))
    pause_decision = Decision(action=Action.PAUSE, reason=ActionReason.SCHEDULER_PAUSED, target=Playlists())
    engine.think = mock.Mock(return_value=ThinkResult(
        match=Match(best_playlists=Playlists(), playlist_matches=[]),
        decision=pause_decision,
        plan=pause_plan,
    ))

    trace = scheduler._run_tick()

    assert trace.paused is True
    engine.think.assert_called_once()
    engine.actuator.act.assert_called_once()
    assert engine.actuator.act.call_args.args[0] == pause_decision

    scheduler._ensure_we_alive()
    engine.ensure_we_alive.assert_called_once_with(paused=True)


def test_scheduler_recovery_tick_uses_action_without_reason_parameter():
    class DummyHistory:
        def write(self, *_args, **_kwargs):
            return 0

    scheduler = WEScheduler("config", DummyHistory())
    engine = Engine("config")
    engine.context_manager = mock.Mock()
    engine.context_manager.sense.return_value = Context(window=WindowData(title="", process=""), idle=0.0)
    engine.we_config_prober = mock.Mock(probe_playlist=mock.Mock(return_value=FactualPlaylistState(FactualPlaylistStatus.NO_PLAYLIST)))
    scheduler.engine = engine
    scheduler.state.cached_playlists = Playlists(["focus"])
    scheduler.state.paused = False
    engine.actuator = mock.Mock()
    engine.actuator.act.return_value = ActionResult(
        executed=True,
    )

    recovery_decision = Decision(
        action=Action.SWITCH,
        reason=ActionReason.RECOVERY_UNMANAGED,
        target=Playlists(["rain"]),
    )
    recovery_plan = ActPlan(mode=DecisionMode.RECOVERY, active_playlists=Playlists())
    think_result = ThinkResult(
        match=Match(
            best_playlists=Playlists(["rain"]),
            playlist_matches=[("rain", 0.9)],
        ),
        decision=recovery_decision,
        plan=recovery_plan,
    )
    engine.think = mock.Mock(return_value=think_result)
    engine.actuator.act.return_value = ActionResult(
        executed=True,
    )
    engine.controller = mock.Mock()

    def _act(think):
        result = engine.actuator.act(think.decision, think.plan.active_playlists)
        if result.executed:
            engine.controller.notify_executed(think.decision)
        return result

    engine.act = mock.Mock(side_effect=_act)

    scheduler._run_tick()

    engine.actuator.act.assert_called_once()
    assert engine.actuator.act.call_args.args[0] == recovery_decision
    engine.controller.notify_executed.assert_called_once_with(recovery_decision)


def test_scheduler_commit_tick_fans_out_to_listeners():
    class DummyHistory:
        def write(self, *_args, **_kwargs):
            return 0

    scheduler = WEScheduler("config", DummyHistory())
    calls: list[tuple[str, int]] = []
    scheduler.add_tick_listener(lambda trace: calls.append(("first", trace.tick_id)))
    scheduler.add_tick_listener(lambda trace: calls.append(("second", trace.tick_id)))
    think = ThinkResult(
        match=Match(best_playlists=Playlists()),
        decision=Decision(action=Action.HOLD, reason=ActionReason.NO_MATCH, target=Playlists()),
        plan=ActPlan(mode=DecisionMode.NORMAL, active_playlists=Playlists()),
    )
    trace = TickTrace(
        tick_id=42,
        ts=123.0,
        paused=False,
        pause_until=0.0,
        context=Context(),
        think=think,
        action=ActionResult(
            executed=False,
        ),
    )

    scheduler._commit_tick(trace)

    assert calls == [("first", 42), ("second", 42)]


def test_scheduler_persisted_state_excludes_controller_runtime_state():
    state = PersistedState(
        paused=True,
        pause_until=123.0,
        cached_playlists=["focus"],
    )

    dumped = state.model_dump()

    assert "last_action_time" not in dumped
    assert "semantic_continuity_score" not in dumped
    assert "controller" not in dumped


def test_scheduler_persisted_state_ignores_legacy_controller_runtime_state(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        """
        {
            "paused": true,
            "pause_until": 123.0,
            "cached_playlists": ["focus"],
            "last_action_time": 456.0,
            "semantic_continuity_score": 0.25
        }
        """,
        encoding="utf-8",
    )

    state = PersistedState.load(str(state_path))

    assert state.paused is True
    assert state.cached_playlists == ["focus"]
    assert not hasattr(state, "last_action_time")
    assert not hasattr(state, "semantic_continuity_score")


def test_scheduler_persisted_state_missing_file_returns_default_without_warning(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger="WEScheduler.State")

    state = PersistedState.load(str(tmp_path / "missing-state.json"))

    assert state == PersistedState()
    assert not [record for record in caplog.records if record.name == "WEScheduler.State"]


def test_hot_reload_state_import_error_keeps_previous_runtime():
    config_loader = mock.Mock()
    runtime = Engine("config")
    runtime.config_loader = config_loader
    old_executor = object()
    old_context_manager = object()
    old_matcher = mock.Mock()
    old_matcher.export_state.return_value = {"StatefulPolicy": {"state": "old"}}
    old_actuator = mock.Mock()
    old_actuator.export_state.return_value = {"controller": "old"}

    runtime.executor = old_executor
    runtime.context_manager = old_context_manager
    runtime.matcher = old_matcher
    runtime.actuator = old_actuator
    previous_config = mock.Mock()
    runtime.config_loader.config = previous_config
    runtime.config_loader.load_verified_config.return_value = mock.Mock()

    next_matcher = mock.Mock()
    next_matcher.import_state.side_effect = RuntimeError("import failed")
    next_runtime = _BuiltEngine(
        executor=object(),
        context_manager=object(),
        matcher=next_matcher,
        actuator=mock.Mock(),
        controller=mock.Mock(),
        config=mock.Mock(playlists={}, language=None),
        we_config_prober=mock.Mock(),
    )
    runtime._build_components = mock.Mock(return_value=next_runtime)

    fingerprint = (("scheduler.yaml", True, 3),)
    runtime._hot_reload(fingerprint)

    assert runtime.executor is old_executor
    assert runtime.context_manager is old_context_manager
    assert runtime.matcher is old_matcher
    assert runtime.actuator is old_actuator
    assert runtime.config_loader.config is previous_config
    assert runtime.config_fingerprint == fingerprint


def test_hot_reload_preserves_startup_end():
    """After hot reload, the controller's startup_end must be restored from the
    old controller, not reset to ``now + startup_delay`` (which would cause a
    phantom ~30 s cooldown blocker)."""
    clock = _MutableClock(500.0)
    old_controller = SchedulingController(
        SchedulingConfig(
            startup_delay=30,
            force_after=100,
            cycle_cooldown=15,
            idle_threshold=60,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        ),
        clock=clock,
    )
    # Simulate the warmup having long expired (startup_end = 530, now = 900).
    old_controller.startup_end = 530.0
    old_controller.last_action_time = 800.0
    old_controller.semantic_continuity_score = 0.75
    exported = old_controller.export_state()

    # After hot reload, a new controller is created at t=900 with startup_delay=30
    # -> default startup_end = 930.
    clock.now = 900.0
    new_controller = SchedulingController(
        SchedulingConfig(
            startup_delay=30,
            force_after=100,
            cycle_cooldown=15,
            idle_threshold=60,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        ),
        clock=clock,
    )
    assert new_controller.startup_end == pytest.approx(930.0)

    new_controller.import_state(exported)

    # startup_end should be the OLD value (530), not the default 930.
    assert new_controller.startup_end == pytest.approx(530.0)
    assert new_controller.last_action_time == pytest.approx(800.0)
    assert new_controller.semantic_continuity_score == pytest.approx(0.75)


# ── Clustering tests ────────────────────────────────────────────────────────


def test_matcher_cluster_groups_playlists_within_gap_threshold():
    """When top playlists have similar scores (gap < 0.02), they cluster together."""
    stub_policy = mock.Mock()
    stub_policy.evaluate.return_value = ActivityEvaluation(
        policy_id="stub",
        enabled=True,
        active=True,
        weight=1.0,
        salience=1.0,
        intensity=1.0,
        effective_magnitude=1.0,
        direction={"focus": 1.0, "chill": 0.5},
        raw_contribution={"focus": 1.0, "chill": 0.5},
        details=ActivityDetails(),
    )

    # Create playlists with similar tag vectors so scores are close
    matcher = Matcher(
        playlist_configs={
            "A": PlaylistConfig(color="#FF0000", tags={"focus": 1.0}),
            "B": PlaylistConfig(color="#00FF00", tags={"focus": 0.99}),
            "C": PlaylistConfig(color="#0000FF", tags={"chill": 1.0}),
        },
        policies=[stub_policy],
    )

    evaluation = matcher.match(Context())

    # A and B should cluster (similar scores), C should be excluded (different tag)
    assert len(evaluation.best_playlists) >= 1
    assert "A" in evaluation.best_playlists or "B" in evaluation.best_playlists
    score_lookup = dict(evaluation.playlist_matches)
    assert all(name in score_lookup for name in evaluation.best_playlists)


def test_matcher_cluster_breaks_on_large_gap():
    """When there's a large gap between 1st and 2nd, only the top playlist is selected."""
    stub_policy = mock.Mock()
    stub_policy.evaluate.return_value = ActivityEvaluation(
        policy_id="stub",
        enabled=True,
        active=True,
        weight=1.0,
        salience=1.0,
        intensity=1.0,
        effective_magnitude=1.0,
        direction={"focus": 1.0},
        raw_contribution={"focus": 1.0},
        details=ActivityDetails(),
    )

    matcher = Matcher(
        playlist_configs={
            "STRONG": PlaylistConfig(color="#FF0000", tags={"focus": 1.0}),
            "WEAK": PlaylistConfig(color="#00FF00", tags={"chill": 1.0}),
        },
        policies=[stub_policy],
    )

    evaluation = matcher.match(Context())

    assert evaluation.best_playlists == Playlists(["STRONG"])
    assert len(evaluation.best_playlists) == 1


def test_matcher_cluster_empty_when_no_match():
    """When no playlist matches, best_playlists is empty."""
    stub_policy = mock.Mock()
    stub_policy.evaluate.return_value = ActivityEvaluation(
        policy_id="stub",
        enabled=True,
        active=True,
        weight=1.0,
        salience=1.0,
        intensity=1.0,
        effective_magnitude=1.0,
        direction={"nonexistent": 1.0},
        raw_contribution={"nonexistent": 1.0},
        details=ActivityDetails(),
    )

    matcher = Matcher(
        playlist_configs={
            "A": PlaylistConfig(color="#FF0000", tags={"focus": 1.0}),
        },
        policies=[stub_policy],
    )

    evaluation = matcher.match(Context())

    assert evaluation.best_playlists == Playlists()
    assert evaluation.similarity == 0.0


def test_matcher_cluster_respects_max_size():
    """best_playlists never exceeds MAX_CLUSTER_SIZE (4)."""
    stub_policy = mock.Mock()
    stub_policy.evaluate.return_value = ActivityEvaluation(
        policy_id="stub",
        enabled=True,
        active=True,
        weight=1.0,
        salience=1.0,
        intensity=1.0,
        effective_magnitude=1.0,
        direction={"focus": 1.0},
        raw_contribution={"focus": 1.0},
        details=ActivityDetails(),
    )

    playlists = {f"P{i}": PlaylistConfig(color="#FF0000", tags={"focus": 1.0 - i * 0.001}) for i in range(6)}
    matcher = Matcher(playlist_configs=playlists, policies=[stub_policy])

    evaluation = matcher.match(Context())

    assert len(evaluation.best_playlists) <= 4


def test_matcher_similarity_is_field_not_property():
    """similarity and similarity_gap are plain fields filled by Matcher, not computed properties."""
    evaluation = Match(
        best_playlists=Playlists(["A"]),
        playlist_matches=[("A", 0.9)],
    )
    # As plain fields with defaults, they start at 0.0
    assert evaluation.similarity == 0.0
    assert evaluation.similarity_gap == 0.0
    # Can be set like any field
    evaluation.similarity = 0.85
    evaluation.similarity_gap = 0.1
    assert evaluation.similarity == 0.85
    assert evaluation.similarity_gap == 0.1


def test_matcher_fills_similarity_and_similarity_gap():
    """Matcher computes and fills similarity and similarity_gap on evaluate()."""
    stub_policy = mock.Mock()
    stub_policy.evaluate.return_value = ActivityEvaluation(
        policy_id="stub",
        enabled=True,
        active=True,
        weight=1.0,
        salience=1.0,
        intensity=1.0,
        effective_magnitude=1.0,
        direction={"focus": 1.0},
        raw_contribution={"focus": 1.0},
        details=ActivityDetails(),
    )

    matcher = Matcher(
        playlist_configs={
            "A": PlaylistConfig(color="#FF0000", tags={"focus": 1.0}),
            "B": PlaylistConfig(color="#00FF00", tags={"focus": 1.0, "chill": 0.01}),
        },
        policies=[stub_policy],
    )

    evaluation = matcher.match(Context())

    assert evaluation.similarity > 0
    assert evaluation.similarity_gap >= 0
    if len(evaluation.playlist_matches) >= 2:
        expected_gap = evaluation.playlist_matches[0][1] - evaluation.playlist_matches[1][1]
        assert evaluation.similarity_gap == pytest.approx(expected_gap)


def test_matcher_weighted_similarity():
    """Matcher weights similarity by item_count when available."""
    stub_policy = mock.Mock()
    stub_policy.evaluate.return_value = ActivityEvaluation(
        policy_id="stub",
        enabled=True,
        active=True,
        weight=1.0,
        salience=1.0,
        intensity=1.0,
        effective_magnitude=1.0,
        direction={"focus": 1.0},
        raw_contribution={"focus": 1.0},
        details=ActivityDetails(),
    )

    matcher = Matcher(
        playlist_configs={
            "A": PlaylistConfig(color="#FF0000", tags={"focus": 1.0}, item_count=10),
            "B": PlaylistConfig(color="#00FF00", tags={"focus": 1.0, "chill": 0.01}, item_count=40),
        },
        policies=[stub_policy],
    )

    evaluation = matcher.match(Context())

    score_lookup = dict(evaluation.playlist_matches)
    score_a = score_lookup.get("A", 0)
    score_b = score_lookup.get("B", 0)
    if score_a > 0 and score_b > 0 and score_a != pytest.approx(score_b, abs=1e-6):
        expected_weighted = (score_a * 10 + score_b * 40) / 50
        assert evaluation.similarity == pytest.approx(expected_weighted)
