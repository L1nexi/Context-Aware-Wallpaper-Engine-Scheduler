from __future__ import annotations

from unittest import mock

import pytest

from core.actuator import Actuator
from core.context import Context, WindowData
from core.controller import SchedulingController
from core.diagnostics import (
    ActionKind,
    ActionReasonCode,
    ActivityPolicyDetails,
    ActivityPolicyEvaluation,
    ActuationOutcome,
    ControllerBlocker,
    ControllerDecision,
    ControllerEvaluation,
    MatchEvaluation,
)
from core.matcher import Matcher
from core.playlist_state import PlaylistRecoveryReason, resolve_playlist_state
from core.policies import ActivityPolicy, TimePolicy, WeatherPolicy
from core.scheduler import WEScheduler, _RuntimeComponents
from ui.dashboard_analysis import DashboardRuntimeMetadata, map_tick_snapshot
from utils.config_errors import ConfigIssue, ConfigLoadError
from utils.runtime_config import (
    ActivityPolicyConfig,
    PlaylistConfig,
    SchedulingConfig,
    TagSpec,
    TimePolicyConfig,
    WeatherPolicyConfig,
)
from utils.we_config import FactualPlaylistState, FactualPlaylistStatus


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
        effective_playlist_before="focus",
        effective_playlist_after="focus",
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
    assert switch_eval.cooldown_remaining == pytest.approx(0.0)
    assert switch_eval.force_after_remaining == pytest.approx(95.0)
    assert set(switch_eval.blocked_by) == {
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


def test_controller_warmup_blocks_all_operations(monkeypatch):
    """During startup warmup, both switch and cycle are blocked by COOLDOWN,
    and context gates (CPU, fullscreen) are still collected."""
    monkeypatch.setattr("core.controller.time.time", lambda: 100.0)
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=30,
            force_after=100,
            cycle_cooldown=15,
            idle_threshold=60,
            cpu_threshold=80,
            cpu_sample_window=1,
            pause_on_fullscreen=True,
        )
    )
    # t=105: 5s into 30s warmup
    monkeypatch.setattr("core.controller.time.time", lambda: 105.0)

    context = Context(idle=120.0, cpu=90.0, fullscreen=True)

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

    # Both blocked despite user being idle (idle=120 >= threshold=60)
    assert switch_eval.allowed is False
    assert ControllerBlocker.COOLDOWN in switch_eval.blocked_by
    assert ControllerBlocker.IDLE not in switch_eval.blocked_by
    assert switch_eval.cooldown_remaining == pytest.approx(25.0)

    assert cycle_eval.allowed is False
    assert ControllerBlocker.COOLDOWN in cycle_eval.blocked_by
    assert ControllerBlocker.IDLE not in cycle_eval.blocked_by
    assert cycle_eval.cooldown_remaining == pytest.approx(25.0)

    # Context gates still collected
    assert ControllerBlocker.CPU in switch_eval.blocked_by
    assert ControllerBlocker.FULLSCREEN in switch_eval.blocked_by


def test_controller_warmup_switch_reason_code(monkeypatch):
    """During warmup, a switch decision should report SWITCH_BLOCKED_COOLDOWN."""
    monkeypatch.setattr("core.controller.time.time", lambda: 100.0)
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=30,
            force_after=100,
            cycle_cooldown=15,
            idle_threshold=60,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        )
    )
    monkeypatch.setattr("core.controller.time.time", lambda: 105.0)

    decision = controller.decide_action(
        Context(idle=120.0, cpu=1.0),
        MatchEvaluation(best_playlist="rain", playlist_matches=[("rain", 0.8)]),
        "focus",
    )

    assert decision.reason_code == ActionReasonCode.SWITCH_BLOCKED_COOLDOWN
    assert decision.evaluation.cooldown_remaining == pytest.approx(25.0)


def test_controller_warmup_expires_normal_behavior(monkeypatch):
    """After warmup expires, switches proceed with normal idle/force_after logic."""
    monkeypatch.setattr("core.controller.time.time", lambda: 100.0)
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=10,
            force_after=100,
            cycle_cooldown=15,
            idle_threshold=60,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        )
    )
    # t=120: well past 10s warmup, user idle for 80s
    monkeypatch.setattr("core.controller.time.time", lambda: 120.0)

    decision = controller.decide_action(
        Context(idle=80.0, cpu=1.0),
        MatchEvaluation(best_playlist="rain", playlist_matches=[("rain", 0.8)]),
        "focus",
    )

    assert decision.kind == ActionKind.SWITCH
    assert decision.reason_code == ActionReasonCode.SWITCH_ALLOWED
    assert ControllerBlocker.COOLDOWN not in decision.evaluation.blocked_by
    assert decision.evaluation.cooldown_remaining == pytest.approx(0.0)


def test_controller_switch_has_no_cooldown_gate(monkeypatch):
    """Two consecutive switches are not blocked by a cooldown gate."""
    monkeypatch.setattr("core.controller.time.time", lambda: 100.0)
    controller = SchedulingController(
        SchedulingConfig(
            startup_delay=0,
            force_after=3600,
            cycle_cooldown=900,
            idle_threshold=10,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        )
    )
    # First switch at t=100
    controller.last_playlist_switch_time = 100.0

    # Second switch at t=101 — should NOT be blocked by cooldown
    monkeypatch.setattr("core.controller.time.time", lambda: 101.0)
    evaluation = controller._evaluate_operation(
        Context(idle=20.0, cpu=1.0),
        operation="switch",
    )

    assert ControllerBlocker.COOLDOWN not in evaluation.blocked_by
    assert evaluation.cooldown_remaining == pytest.approx(0.0)
    assert evaluation.allowed is True


def test_controller_switch_force_after_overrides_idle(monkeypatch):
    monkeypatch.setattr("core.controller.time.time", lambda: 500.0)
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
            force_after=100,
            cycle_cooldown=15,
            idle_threshold=60,
            cpu_threshold=0,
            pause_on_fullscreen=False,
        )
    )
    controller._evaluate_operation = mock.Mock(side_effect=lambda _context, *, operation: switch_eval if operation == "switch" else cycle_eval)

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


def test_actuator_recovery_switch_bypasses_controller_gates():
    executor = mock.Mock()
    history = mock.Mock()
    controller = mock.Mock()
    actuator = Actuator(executor, controller, history)

    outcome = actuator.act_recovery(
        MatchEvaluation(
            best_playlist="rain",
            playlist_matches=[("rain", 0.9), ("focus", 0.5)],
            raw_context_vector={"rain": 1.0},
        ),
        "",
        PlaylistRecoveryReason.NO_PLAYLIST,
    )

    assert outcome.kind == ActionKind.SWITCH
    assert outcome.reason_code == ActionReasonCode.RECOVERY_NO_PLAYLIST
    assert outcome.executed is True
    executor.open_playlist.assert_called_once_with("rain")
    controller.decide_action.assert_not_called()
    controller.notify_playlist_switch.assert_called_once()
    history.write.assert_called_once()
    assert history.write.call_args.args[1]["reason_code"] == "recovery_no_playlist"


def test_playlist_state_uses_managed_factual_playlist():
    resolution = resolve_playlist_state(
        FactualPlaylistState(FactualPlaylistStatus.PLAYLIST, playlist="rain"),
        cached_playlist="focus",
        managed_playlists={"focus", "rain"},
        paused=False,
    )

    assert resolution.effective_playlist == "rain"
    assert resolution.recovery_needed is False
    assert resolution.recovery_reason is None


@pytest.mark.parametrize(
    ("factual", "expected_reason"),
    [
        (
            FactualPlaylistState(FactualPlaylistStatus.PLAYLIST, playlist="other"),
            PlaylistRecoveryReason.UNMANAGED_PLAYLIST,
        ),
        (
            FactualPlaylistState(FactualPlaylistStatus.NO_PLAYLIST),
            PlaylistRecoveryReason.NO_PLAYLIST,
        ),
    ],
)
def test_playlist_state_requests_recovery_for_running_broken_state(
    factual,
    expected_reason,
):
    resolution = resolve_playlist_state(
        factual,
        cached_playlist="focus",
        managed_playlists={"focus", "rain"},
        paused=False,
    )

    assert resolution.effective_playlist == ""
    assert resolution.recovery_needed is True
    assert resolution.recovery_reason == expected_reason


def test_playlist_state_suppresses_recovery_while_paused():
    resolution = resolve_playlist_state(
        FactualPlaylistState(FactualPlaylistStatus.NO_PLAYLIST),
        cached_playlist="focus",
        managed_playlists={"focus"},
        paused=True,
    )

    assert resolution.effective_playlist == ""
    assert resolution.recovery_needed is False
    assert resolution.recovery_reason == PlaylistRecoveryReason.NO_PLAYLIST


@pytest.mark.parametrize(
    "status",
    [FactualPlaylistStatus.UNKNOWN, FactualPlaylistStatus.AMBIGUOUS],
)
def test_playlist_state_falls_back_to_cached_playlist_when_factual_unknown(status):
    resolution = resolve_playlist_state(
        FactualPlaylistState(status),
        cached_playlist="focus",
        managed_playlists={"focus"},
        paused=False,
    )

    assert resolution.effective_playlist == "focus"
    assert resolution.recovery_needed is False


def test_scheduler_factual_probe_does_not_start_wallpaper_engine():
    class DummyHistory:
        last_event_id = 0

        def write(self, *_args, **_kwargs):
            return None

    scheduler = WEScheduler("config", DummyHistory())
    scheduler.context_manager = mock.Mock(refresh=mock.Mock(return_value=Context(window=WindowData(title="", process=""), idle=0.0)))
    scheduler.matcher = mock.Mock(evaluate=mock.Mock(return_value=MatchEvaluation(best_playlist=None, playlist_matches=[])))
    scheduler.executor = mock.Mock()
    scheduler.executor.is_we_running = mock.Mock(return_value=False)
    scheduler.executor.request_we_start = mock.Mock(return_value=True)
    scheduler.we_config_prober = mock.Mock(probe_playlist=mock.Mock(return_value=FactualPlaylistState(FactualPlaylistStatus.UNKNOWN)))
    scheduler.managed_playlists = {"focus"}
    scheduler.cached_playlist = "focus"
    scheduler.paused = True

    trace = scheduler._run_tick()

    assert trace.paused is True
    scheduler.we_config_prober.probe_playlist.assert_called_once()
    scheduler.executor.is_we_running.assert_not_called()
    scheduler.executor.request_we_start.assert_not_called()


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
    scheduler.config_loader.load_verified_config.side_effect = ConfigLoadError(
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


def test_hot_reload_state_import_error_keeps_previous_runtime():
    class DummyHistory:
        last_event_id = 0

        def write(self, *_args: object, **_kwargs: object) -> None:
            return None

    class StatefulPolicy:
        def __init__(self, raise_on_import: bool = False):
            self.raise_on_import = raise_on_import

        def export_state(self) -> dict[str, str]:
            return {"state": "old"}

        def import_state(self, _state: object) -> None:
            if self.raise_on_import:
                raise RuntimeError("import failed")

    scheduler = WEScheduler("config", DummyHistory())
    old_executor = object()
    old_context_manager = object()
    old_matcher = mock.Mock()
    old_matcher.policies = [StatefulPolicy()]
    old_actuator = mock.Mock()
    old_actuator.controller.export_state.return_value = {"controller": "old"}

    scheduler.executor = old_executor
    scheduler.context_manager = old_context_manager
    scheduler.matcher = old_matcher
    scheduler.actuator = old_actuator
    scheduler.display_of = {"focus": "Focus"}
    scheduler.color_of = {"focus": "#F5C518"}
    scheduler.config_loader = mock.Mock()
    previous_config = mock.Mock()
    scheduler.config_loader.config = previous_config
    scheduler.config_loader.load_verified_config.return_value = mock.Mock()

    next_runtime = _RuntimeComponents(
        executor=object(),
        context_manager=object(),
        matcher=mock.Mock(policies=[StatefulPolicy(raise_on_import=True)]),
        actuator=mock.Mock(),
        display_of={"rain": "Rain"},
        color_of={"rain": "#2563EB"},
        we_config_prober=mock.Mock(),
        managed_playlists={"rain"},
    )
    scheduler._build_runtime_components = mock.Mock(return_value=next_runtime)

    fingerprint = (("scheduler.yaml", True, 3),)
    scheduler._hot_reload(fingerprint)

    assert scheduler.executor is old_executor
    assert scheduler.context_manager is old_context_manager
    assert scheduler.matcher is old_matcher
    assert scheduler.actuator is old_actuator
    assert scheduler.display_of == {"focus": "Focus"}
    assert scheduler.color_of == {"focus": "#F5C518"}
    assert scheduler.config_loader.config is previous_config
    assert scheduler._config_fingerprint == fingerprint
