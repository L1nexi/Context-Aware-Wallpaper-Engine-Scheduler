from __future__ import annotations

import threading
from unittest import mock

import pytest

from core.actuator import Actuator
from core.context import Context, WindowData
from core.controller import SchedulingController
from core.diagnostics import (
    ActivityPolicyDetails,
    ActivityPolicyEvaluation,
    ActionKind,
    ActionReasonCode,
    ActuationOutcome,
    ControllerBlocker,
    ControllerDecision,
    ControllerEvaluation,
    MatchEvaluation,
)
from core.matcher import Matcher
from core.policies import ActivityPolicy, TimePolicy, WeatherPolicy
from core.scheduler import WEScheduler
from ui.dashboard_analysis import DashboardRuntimeMetadata, map_tick_snapshot
from utils.config_errors import ConfigIssue, ConfigLoadError
from utils.runtime_config import (
    ActivityPolicyConfig,
    PlaylistConfig,
    TimePolicyConfig,
    SchedulingConfig,
    TagSpec,
    WeatherPolicyConfig,
)


def test_activity_policy_distinguishes_title_and_process_rules():
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

    title_eval = policy.evaluate(
        Context(window=WindowData(title="YouTube Music", process="chrome.exe"))
    )
    assert title_eval.active is True
    assert title_eval.details.match_source == "title"
    assert title_eval.details.matched_rule == "YouTube"
    assert title_eval.dominant_tag == "chill"

    process_eval = policy.evaluate(
        Context(window=WindowData(title="Docs", process="chrome.exe"))
    )
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


def test_matcher_preserves_raw_resolved_and_fallback_vectors():
    stub_policy = mock.Mock()
    stub_policy.evaluate.return_value = ActivityPolicyEvaluation(
        policy_id="stub",
        enabled=True,
        active=True,
        weight=1.0,
        salience=1.0,
        intensity=1.0,
        effective_magnitude=1.0,
        direction={"stormy": 1.0},
        raw_contribution={"stormy": 1.0},
        details=ActivityPolicyDetails(),
    )

    matcher = Matcher(
        playlists={"focus": PlaylistConfig(color="#F5C518", tags={"focus": 1.0})},
        policies=[stub_policy],
        tag_specs={"stormy": TagSpec(fallback={"focus": 1.0})},
    )

    evaluation = matcher.evaluate(Context())

    assert evaluation.raw_context_vector == {"stormy": 1.0}
    assert evaluation.resolved_context_vector == {"focus": 1.0}
    assert evaluation.best_playlist == "focus"
    assert evaluation.fallback_expansions == {"stormy": {"focus": 1.0}}
    assert evaluation.policy_evaluations[0].resolved_contribution == {"focus": 1.0}


def test_diagnostics_snapshot_uses_playlist_metadata_from_runtime_map():
    trace = mock.Mock()
    trace.tick_id = 1
    trace.ts = 1.0
    trace.paused = False
    trace.context = Context(window=WindowData(title="Docs", process="Code.exe"))
    trace.match = MatchEvaluation(
        best_playlist="focus",
        playlist_matches=[("focus", 0.9)],
        raw_context_vector={"focus": 1.0},
        resolved_context_vector={"focus": 1.0},
        policy_evaluations=[],
    )
    trace.action = ActuationOutcome(
        decision=ControllerDecision(
            kind=ActionKind.HOLD,
            reason_code=ActionReasonCode.HOLD_SAME_PLAYLIST,
            matched_playlist="focus",
            evaluation=None,
        ),
        active_playlist_before="focus",
        active_playlist_after="focus",
        executed=False,
    )

    snapshot = map_tick_snapshot(
        trace,
        DashboardRuntimeMetadata(
            display_of={"focus": "Focus Flow"},
            color_of={"focus": "#F5C518"},
        ),
    ).model_dump(mode="json", by_alias=True)

    assert snapshot["summary"]["matchedPlaylist"] == {
        "name": "focus",
        "display": "Focus Flow",
        "color": "#F5C518",
    }


def test_controller_evaluation_reports_all_blockers(monkeypatch):
    monkeypatch.setattr("core.controller.time.time", lambda: 200.0)
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=0,
            switch_cooldown=10,
            force_after=100,
            cycle_cooldown=15,
            idle_threshold=60,
            cpu_threshold=80,
            cpu_sample_window=1,
            pause_on_fullscreen=True,
        )
    )
    controller.last_playlist_switch_time = 195.0
    controller.last_wallpaper_switch_time = 190.0

    context = Context(idle=10.0, cpu=90.0, fullscreen=True)
    switch_decision = controller.decide_action(
        context,
        MatchEvaluation(best_playlist="rain", playlist_matches=[("rain", 0.8)]),
        "focus",
    )
    cycle_decision = controller.decide_action(
        context,
        MatchEvaluation(best_playlist="focus", playlist_matches=[("focus", 0.8)]),
        "focus",
    )
    switch_eval = switch_decision.evaluation
    cycle_eval = cycle_decision.evaluation

    assert switch_eval.allowed is False
    assert switch_eval.operation == "switch"
    assert switch_eval.cooldown_remaining == pytest.approx(5.0)
    assert switch_eval.force_after_remaining == pytest.approx(95.0)
    assert set(switch_eval.blocked_by) == {
        ControllerBlocker.COOLDOWN,
        ControllerBlocker.CPU,
        ControllerBlocker.FULLSCREEN,
        ControllerBlocker.IDLE,
    }

    assert cycle_eval.allowed is False
    assert cycle_eval.operation == "cycle"
    assert cycle_eval.cooldown_remaining == pytest.approx(5.0)
    assert set(cycle_eval.blocked_by) == {
        ControllerBlocker.COOLDOWN,
        ControllerBlocker.CPU,
        ControllerBlocker.FULLSCREEN,
        ControllerBlocker.IDLE,
    }


def test_controller_switch_force_after_overrides_idle(monkeypatch):
    monkeypatch.setattr("core.controller.time.time", lambda: 500.0)
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=0,
            switch_cooldown=10,
            force_after=100,
            cycle_cooldown=15,
            idle_threshold=60,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        )
    )
    controller.last_playlist_switch_time = 390.0

    decision = controller.decide_action(
        Context(idle=5.0, cpu=1.0),
        MatchEvaluation(best_playlist="rain", playlist_matches=[("rain", 0.8)]),
        "focus",
    )
    evaluation = decision.evaluation

    assert decision.reason_code == ActionReasonCode.SWITCH_ALLOWED
    assert evaluation.allowed is True
    assert evaluation.operation == "switch"
    assert evaluation.blocked_by == []
    assert evaluation.force_after_remaining == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("match", "active_playlist", "switch_eval", "cycle_eval", "expected"),
    [
        (
            MatchEvaluation(best_playlist=None),
            "focus",
            ControllerEvaluation(operation="switch", allowed=False),
            ControllerEvaluation(operation="cycle", allowed=False),
            ActionReasonCode.NO_MATCH,
        ),
        (
            MatchEvaluation(best_playlist="rain", playlist_matches=[("rain", 0.8), ("focus", 0.6)]),
            "focus",
            ControllerEvaluation(operation="switch", allowed=True),
            ControllerEvaluation(operation="cycle", allowed=False),
            ActionReasonCode.SWITCH_ALLOWED,
        ),
        (
            MatchEvaluation(best_playlist="rain", playlist_matches=[("rain", 0.8), ("focus", 0.6)]),
            "focus",
            ControllerEvaluation(
                operation="switch",
                allowed=False,
                blocked_by=[ControllerBlocker.COOLDOWN],
            ),
            ControllerEvaluation(operation="cycle", allowed=False),
            ActionReasonCode.SWITCH_BLOCKED_COOLDOWN,
        ),
        (
            MatchEvaluation(best_playlist="focus", playlist_matches=[("focus", 0.8), ("rain", 0.6)]),
            "focus",
            ControllerEvaluation(operation="switch", allowed=False),
            ControllerEvaluation(operation="cycle", allowed=True),
            ActionReasonCode.CYCLE_ALLOWED,
        ),
        (
            MatchEvaluation(best_playlist="focus", playlist_matches=[("focus", 0.8), ("rain", 0.6)]),
            "focus",
            ControllerEvaluation(operation="switch", allowed=False),
            ControllerEvaluation(
                operation="cycle",
                allowed=False,
                blocked_by=[ControllerBlocker.CPU],
            ),
            ActionReasonCode.CYCLE_BLOCKED_CPU,
        ),
        (
            MatchEvaluation(best_playlist="focus", playlist_matches=[("focus", 0.8), ("rain", 0.6)]),
            "focus",
            ControllerEvaluation(operation="switch", allowed=False),
            ControllerEvaluation(operation="cycle", allowed=False),
            ActionReasonCode.HOLD_SAME_PLAYLIST,
        ),
    ],
)
def test_controller_decide_reason_code(
    match,
    active_playlist,
    switch_eval,
    cycle_eval,
    expected,
):
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=0,
            switch_cooldown=10,
            force_after=100,
            cycle_cooldown=15,
            idle_threshold=60,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        )
    )
    controller._evaluate_operation = mock.Mock(
        side_effect=lambda _context, *, operation: (
            switch_eval if operation == "switch" else cycle_eval
        )
    )

    decision = controller.decide_action(Context(), match, active_playlist)

    assert decision.reason_code == expected


def test_actuator_switch_logs_event():
    executor = mock.Mock()
    history = mock.Mock()
    controller = mock.Mock()
    controller.decide_action.return_value = ControllerDecision(
        kind=ActionKind.SWITCH,
        reason_code=ActionReasonCode.SWITCH_ALLOWED,
        matched_playlist="rain",
        evaluation=ControllerEvaluation(operation="switch", allowed=True),
    )
    actuator = Actuator(executor, controller, history)
    outcome = actuator.act(
        Context(),
        MatchEvaluation(
            best_playlist="rain",
            playlist_matches=[("rain", 0.9), ("focus", 0.5)],
            raw_context_vector={"rain": 1.0},
            resolved_context_vector={"rain": 1.0},
            max_policy_magnitude=1.0,
        ),
        "focus",
    )

    assert outcome.kind == ActionKind.SWITCH
    assert outcome.executed is True
    executor.open_playlist.assert_called_once_with("rain")
    controller.notify_playlist_switch.assert_called_once()
    history.write.assert_called_once()
    assert history.write.call_args.args[1]["reason_code"] == "switch_allowed"


def test_hot_reload_config_error_keeps_previous_runtime_and_notifies():
    class DummyHistory:
        last_event_id = 0

        def write(self, *_args, **_kwargs):
            return None

    scheduler = WEScheduler("config", DummyHistory())
    old_executor = object()
    old_context_manager = object()
    old_matcher = mock.Mock()
    old_matcher.policies = []
    old_actuator = mock.Mock()
    old_actuator.controller.export_state.return_value = {}

    scheduler.executor = old_executor
    scheduler.context_manager = old_context_manager
    scheduler.matcher = old_matcher
    scheduler.actuator = old_actuator
    scheduler.display_of = {"focus": "Focus"}
    scheduler.color_of = {"focus": "#F5C518"}
    scheduler.config_loader = mock.Mock()
    scheduler.config_loader.config = mock.Mock()
    scheduler.config_loader.load.side_effect = ConfigLoadError(
        [
            ConfigIssue(
                source_file="scheduler.yaml",
                field_path=("runtime", "wallpaper_engine_path"),
                message="Wallpaper Engine executable could not be auto-detected",
                code="wallpaper_engine_path_unresolved",
            )
        ]
    )

    captured: list[ConfigLoadError] = []
    scheduler.on_reload_error = captured.append

    fingerprint = (("scheduler.yaml", True, 2),)
    scheduler._hot_reload(fingerprint)

    assert scheduler.executor is old_executor
    assert scheduler.context_manager is old_context_manager
    assert scheduler.matcher is old_matcher
    assert scheduler.actuator is old_actuator
    assert scheduler.last_reload_error is captured[0]
    assert scheduler._config_fingerprint == fingerprint


def test_scheduler_tick_trace_uses_context_snapshot(monkeypatch):
    class DummyHistory:
        last_event_id = 0

        def write(self, *_args, **_kwargs):
            return None

    class FakeContextManager:
        def __init__(self, context):
            self.context = context

        def refresh(self):
            return self.context

    class FakeMatcher:
        def evaluate(self, _context):
            return MatchEvaluation(best_playlist="focus", playlist_matches=[("focus", 0.8), ("rain", 0.6)])

    class FakeActuator:
        def __init__(self):
            self.controller = mock.Mock()

        def act(self, _context, match, current_playlist):
            return ActuationOutcome(
                decision=ControllerDecision(
                    kind=ActionKind.HOLD,
                    reason_code=ActionReasonCode.HOLD_SAME_PLAYLIST,
                    matched_playlist=match.best_playlist,
                    evaluation=ControllerEvaluation(operation="cycle", allowed=False),
                ),
                active_playlist_before=current_playlist,
                active_playlist_after=current_playlist,
            )

    monkeypatch.setattr("core.scheduler.time.sleep", lambda _seconds: None)

    scheduler = WEScheduler("config", DummyHistory())
    live_context = Context(window=WindowData(title="Before", process="before.exe"), idle=5.0)
    scheduler.context_manager = FakeContextManager(live_context)
    scheduler.matcher = FakeMatcher()
    scheduler.actuator = FakeActuator()
    scheduler.current_playlist = "focus"
    scheduler.paused = False
    scheduler.stop_event = threading.Event()
    scheduler._check_hot_reload = lambda: None
    scheduler._update_status = lambda _trace: None

    captured: list = []

    def _capture(trace):
        captured.append(trace)
        scheduler.stop_event.set()

    scheduler.on_tick = _capture

    scheduler._run_loop()
    live_context.window.process = "after.exe"
    live_context.window.title = "After"

    assert scheduler.last_tick_trace is not None
    assert len(captured) == 1
    assert captured[0].context.window.process == "before.exe"
    assert captured[0].context.window.title == "Before"
