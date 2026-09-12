from __future__ import annotations

from pathlib import Path

import pytest

from configurations.runtime_models import (
    ActivityPolicyConfig,
    PlaylistConfig,
    SchedulingConfig,
    TagSpec,
    WeatherPolicyConfig,
)
from core.models.context import Context, WindowData
from core.models.playlist import Playlists
from core.models.trace import Action, ActPlan, Blocker, Decision, DecisionMode, Match
from core.policies import ActivityPolicy, WeatherPolicy
from core.runtime.controller import Controller
from core.runtime.matcher import Matcher
from core.state.persisted import PersistedState


@pytest.fixture(autouse=True)
def _configure_playlists():
    Playlists.configure(
        {
            "focus": PlaylistConfig(display="Focus Flow", color="#F5C518", item_count=10),
            "rain": PlaylistConfig(display="Rain", color="#2563EB", item_count=5),
            "A": PlaylistConfig(display="A", color="#FF0000", item_count=10),
            "B": PlaylistConfig(display="B", color="#00FF00", item_count=40),
            "C": PlaylistConfig(display="C", color="#0000FF", item_count=0),
        }
    )
    yield
    Playlists.configure({})


class MutableClock:
    def __init__(self, now: float):
        self.now = now

    def __call__(self) -> float:
        return self.now


def _controller(clock: MutableClock, **overrides) -> Controller:
    values = {
        "startup_delay": 0,
        "force_after": 100,
        "cycle_cooldown": 15,
        "idle_threshold": 60,
        "cpu_threshold": 80,
        "cpu_sample_window": 1,
        "pause_on_fullscreen": True,
    }
    values.update(overrides)
    return Controller(SchedulingConfig(**values), clock=clock)


def _decide_normal(
    controller: Controller,
    context: Context,
    matched: list[str],
    active: list[str],
):
    return controller.decide_action(
        ActPlan(mode=DecisionMode.NORMAL, active_playlists=Playlists(active)),
        context,
        Match(
            best_playlists=Playlists(matched),
            playlist_matches=[(name, 0.9 - index * 0.1) for index, name in enumerate(matched)],
        ),
    )


def _activity_policy(tag: str = "focus") -> ActivityPolicy:
    return ActivityPolicy(
        ActivityPolicyConfig(
            smoothing_window=1,
            matchers=[
                {
                    "source": "title",
                    "match": "contains",
                    "pattern": "Work",
                    "tag": tag,
                }
            ],
        )
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

    title_match = policy.evaluate(Context(window=WindowData(title="YouTube Music", process="chrome.exe")))
    process_match = policy.evaluate(Context(window=WindowData(title="Docs", process="chrome.exe")))

    assert title_match.dominant_tag == "chill"
    assert title_match.details.match_source == "title"
    assert process_match.dominant_tag == "focus"
    assert process_match.details.match_source == "process"


def test_activity_policy_uses_unicode_case_insensitive_matching():
    policy = ActivityPolicy(
        ActivityPolicyConfig(
            smoothing_window=1,
            matchers=[
                {
                    "source": "title",
                    "match": "contains",
                    "pattern": "STRASSE",
                    "tag": "focus",
                }
            ],
        )
    )

    evaluation = policy.evaluate(Context(window=WindowData(title="Straße", process="browser.exe")))

    assert evaluation.dominant_tag == "focus"


def test_weather_policy_without_weather_is_inactive():
    evaluation = WeatherPolicy(WeatherPolicyConfig(api_key="abc")).evaluate(Context(weather=None))

    assert evaluation.enabled is True
    assert evaluation.active is False
    assert evaluation.details.available is False


def test_matcher_exposes_raw_and_fallback_resolved_vectors():
    matcher = Matcher(
        playlist_configs={"focus": PlaylistConfig(color="#F5C518", tags={"focus": 1.0})},
        policies=[_activity_policy("stormy")],
        tag_specs={"stormy": TagSpec(fallback={"focus": 1.0})},
    )

    match = matcher.match(Context(window=WindowData(title="Work", process="editor.exe")))

    assert match.raw_context_vector == {"stormy": 1.0}
    assert match.resolved_context_vector == {"focus": 1.0}
    assert match.best_playlists == Playlists(["focus"])
    assert match.fallback_expansions == {"stormy": {"focus": 1.0}}


def test_controller_reports_every_reason_that_blocks_an_action():
    clock = MutableClock(195.0)
    controller = _controller(clock)
    controller.notify_executed(Decision(action=Action.CYCLE, target=Playlists(["focus"])))
    clock.now = 200.0

    switch = _decide_normal(
        controller,
        Context(idle=10.0, cpu=90.0, fullscreen=True),
        ["rain"],
        ["focus"],
    )
    cycle = _decide_normal(
        controller,
        Context(idle=10.0, cpu=90.0, fullscreen=True),
        ["focus"],
        ["focus"],
    )

    assert set(switch.evaluation.blocked_by) == {Blocker.CPU, Blocker.FULLSCREEN, Blocker.IDLE}
    assert set(cycle.evaluation.blocked_by) == {
        Blocker.COOLDOWN,
        Blocker.CPU,
        Blocker.FULLSCREEN,
        Blocker.IDLE,
    }


def test_controller_blocks_switch_and_cycle_during_startup_grace():
    clock = MutableClock(100.0)
    controller = _controller(clock, startup_delay=30)
    clock.now = 105.0
    context = Context(idle=120.0, cpu=90.0, fullscreen=True)

    switch = _decide_normal(controller, context, ["rain"], ["focus"])
    cycle = _decide_normal(controller, context, ["focus"], ["focus"])

    assert switch.action == Action.HOLD
    assert Blocker.COOLDOWN in switch.evaluation.blocked_by
    assert cycle.action == Action.HOLD
    assert Blocker.COOLDOWN in cycle.evaluation.blocked_by


def test_controller_allows_switch_after_startup_grace():
    clock = MutableClock(100.0)
    controller = _controller(
        clock,
        startup_delay=10,
        cpu_threshold=0,
        pause_on_fullscreen=False,
    )
    clock.now = 120.0

    decision = _decide_normal(controller, Context(idle=80.0, cpu=1.0), ["rain"], ["focus"])

    assert decision.action == Action.SWITCH


def test_controller_does_not_apply_cycle_cooldown_to_switches():
    clock = MutableClock(100.0)
    controller = _controller(
        clock,
        force_after=3600,
        cycle_cooldown=900,
        idle_threshold=10,
        cpu_threshold=0,
        pause_on_fullscreen=False,
    )
    controller.notify_executed(Decision(action=Action.SWITCH, target=Playlists(["focus"])))
    clock.now = 101.0

    decision = _decide_normal(controller, Context(idle=20.0, cpu=1.0), ["rain"], ["focus"])

    assert decision.action == Action.SWITCH
    assert Blocker.COOLDOWN not in decision.evaluation.blocked_by


def test_controller_forces_a_deferred_switch_after_the_limit():
    clock = MutableClock(390.0)
    controller = _controller(clock, cpu_threshold=0, pause_on_fullscreen=False)
    controller.notify_executed(Decision(action=Action.SWITCH, target=Playlists(["focus"])))
    clock.now = 500.0

    decision = _decide_normal(controller, Context(idle=5.0, cpu=1.0), ["rain"], ["focus"])

    assert decision.action == Action.SWITCH
    assert decision.evaluation.blocked_by == []


def test_controller_eventually_switches_when_active_and_matched_pools_only_overlap_partially():
    clock = MutableClock(1_000.0)
    controller = _controller(
        clock,
        force_after=0,
        cycle_cooldown=0,
        idle_threshold=0,
        cpu_threshold=0,
        pause_on_fullscreen=False,
    )

    decisions = [_decide_normal(controller, Context(idle=999.0), ["A", "C"], ["A", "B"]) for _ in range(120)]

    assert all(decision.action != Action.SWITCH for decision in decisions[:-1])
    assert decisions[-1].action == Action.SWITCH


def test_controller_recovery_switches_to_a_match_without_context_gates():
    controller = _controller(MutableClock(100.0), startup_delay=30)

    decision = controller.decide_action(
        ActPlan(mode=DecisionMode.RECOVERY, active_playlists=Playlists()),
        Context(idle=0.0, cpu=100.0, fullscreen=True),
        Match(best_playlists=Playlists(["rain"]), playlist_matches=[("rain", 0.8)]),
    )

    assert decision.action == Action.SWITCH
    assert decision.evaluation is None


def test_controller_recovery_without_a_match_does_nothing():
    controller = _controller(MutableClock(100.0))

    decision = controller.decide_action(
        ActPlan(mode=DecisionMode.RECOVERY, active_playlists=Playlists()),
        Context(),
        Match(best_playlists=Playlists()),
    )

    assert decision.action == Action.NONE


def test_matcher_groups_nearly_equivalent_playlists():
    matcher = Matcher(
        playlist_configs={
            "A": PlaylistConfig(color="#FF0000", tags={"focus": 1.0}),
            "B": PlaylistConfig(color="#00FF00", tags={"focus": 0.99}),
            "C": PlaylistConfig(color="#0000FF", tags={"chill": 1.0}),
        },
        policies=[_activity_policy()],
    )

    match = matcher.match(Context(window=WindowData(title="Work", process="editor.exe")))

    assert match.best_playlists == Playlists(["A", "B"])


def test_matcher_returns_only_the_clear_winner():
    matcher = Matcher(
        playlist_configs={
            "A": PlaylistConfig(color="#FF0000", tags={"focus": 1.0}),
            "B": PlaylistConfig(color="#00FF00", tags={"chill": 1.0}),
        },
        policies=[_activity_policy()],
    )

    match = matcher.match(Context(window=WindowData(title="Work", process="editor.exe")))

    assert match.best_playlists == Playlists(["A"])


def test_matcher_returns_no_playlist_when_every_similarity_is_zero():
    matcher = Matcher(
        playlist_configs={"A": PlaylistConfig(color="#FF0000", tags={"chill": 1.0})},
        policies=[_activity_policy()],
    )

    match = matcher.match(Context(window=WindowData(title="Work", process="editor.exe")))

    assert match.best_playlists == Playlists()
    assert match.similarity == 0.0


def test_missing_persisted_state_loads_as_default_without_warning(tmp_path: Path, caplog):
    state = PersistedState.load(str(tmp_path / "missing-state.json"))

    assert state == PersistedState()
    assert not [record for record in caplog.records if record.name == "WEScheduler.State"]
