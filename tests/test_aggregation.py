from __future__ import annotations

import time

import pytest

from configurations.runtime_models import PlaylistConfig
from core.models.context import Context, WindowData
from core.models.playlist import Playlists
from core.models.trace import (
    Action,
    ActionResult,
    ActivityDetails,
    ActivityEvaluation,
    ActPlan,
    Blocker,
    BlockerEvaluation,
    Decision,
    DecisionMode,
    Match,
    ScheduleTrace,
    SeasonEvaluation,
    TickTrace,
    TimeEvaluation,
    WeatherDetails,
    WeatherEvaluation,
)
from ui.aggregation import (
    BUCKET_SIZE,
    Aggregator,
    TraceBucketStore,
    map_decide,
    map_match,
    map_policy,
)


@pytest.fixture(autouse=True)
def _configure_playlists():
    Playlists.configure(
        {
            "focus": PlaylistConfig(display="Focus Flow", color="#F5C518", item_count=10),
            "rainy": PlaylistConfig(display="Rainy Mood", color="#4A90D9", item_count=5),
            "idle": PlaylistConfig(display="", color="#2E5F8A", item_count=3),
        }
    )
    yield
    Playlists.configure({})


def _make_trace(
    *,
    tick_id: int = 1,
    playlist_matches: list[tuple[str, float]] | None = None,
    active_playlist: str = "",
    action_kind: Action = Action.HOLD,
    evaluation: BlockerEvaluation | None = None,
    policy_evaluations: list | None = None,
) -> TickTrace:
    matches = playlist_matches if playlist_matches is not None else [("focus", 0.9), ("rainy", 0.6)]
    best = Playlists([active_playlist]) if active_playlist else Playlists()
    return TickTrace(
        tick_id=tick_id,
        ts=1714800000.0 + tick_id,
        paused=False,
        pause_until=0.0,
        schedule=ScheduleTrace(
            context=Context(
                window=WindowData(process="test.exe", title="Test"),
                idle=0.0,
                cpu=0.0,
                fullscreen=False,
                weather=None,
                time=time.localtime(1714800000),
            ),
            match=Match(
                best_playlists=best,
                playlist_matches=matches,
                policy_evaluations=policy_evaluations or [],
            ),
            plan=ActPlan(mode=DecisionMode.NORMAL, active_playlists=best),
            decision=Decision(
                action=action_kind,
                target=best,
                evaluation=evaluation,
            ),
            action=ActionResult(),
        ),
    )


class TestMapMatch:
    def test_averages_scores_across_ticks(self):
        ticks = [
            _make_trace(tick_id=1, playlist_matches=[("focus", 0.8), ("rainy", 0.4)]),
            _make_trace(tick_id=2, playlist_matches=[("focus", 0.6), ("rainy", 0.8)]),
        ]
        bucket = map_match(ticks)
        assert bucket.scores["focus"] == pytest.approx(0.7)
        assert bucket.scores["rainy"] == pytest.approx(0.6)

    def test_missing_playlist_in_some_ticks_uses_actual_count(self):
        ticks = [
            _make_trace(tick_id=1, playlist_matches=[("focus", 0.9)]),
            _make_trace(tick_id=2, playlist_matches=[("focus", 0.7), ("rainy", 0.5)]),
        ]
        bucket = map_match(ticks)
        assert bucket.scores["focus"] == pytest.approx(0.8)
        assert bucket.scores["rainy"] == pytest.approx(0.25)


class TestMapDecide:
    def test_active_pool_from_last_tick(self):
        ticks = [
            _make_trace(tick_id=1, active_playlist="focus"),
            _make_trace(tick_id=2, active_playlist="rainy"),
        ]
        bucket = map_decide(ticks)
        assert bucket.active_pool == ["rainy"]

    def test_has_cycle_true(self):
        ticks = [
            _make_trace(tick_id=1, action_kind=Action.HOLD),
            _make_trace(tick_id=2, action_kind=Action.CYCLE),
        ]
        bucket = map_decide(ticks)
        assert bucket.has_cycle is True

    def test_has_cycle_false(self):
        ticks = [
            _make_trace(tick_id=1, action_kind=Action.HOLD),
            _make_trace(tick_id=2, action_kind=Action.SWITCH),
        ]
        bucket = map_decide(ticks)
        assert bucket.has_cycle is False

    def test_blockers_counted(self):
        eval1 = BlockerEvaluation(blocked_by=[Blocker.IDLE])
        eval2 = BlockerEvaluation(blocked_by=[Blocker.IDLE, Blocker.COOLDOWN])
        ticks = [
            _make_trace(tick_id=1, evaluation=eval1),
            _make_trace(tick_id=2, evaluation=eval2),
        ]
        bucket = map_decide(ticks)
        assert bucket.blockers == {"idle": 2, "cooldown": 1}


class TestMapPolicy:
    def test_weather_mode_and_mean_magnitude(self):
        evals = [
            WeatherEvaluation(
                policy_id="weather",
                enabled=True,
                active=True,
                weight=1.0,
                salience=1.0,
                intensity=0.5,
                effective_magnitude=0.4,
                details=WeatherDetails(weather_id=500, available=True, mapped=True),
            ),
            WeatherEvaluation(
                policy_id="weather",
                enabled=True,
                active=True,
                weight=1.0,
                salience=1.0,
                intensity=0.5,
                effective_magnitude=0.6,
                details=WeatherDetails(weather_id=500, available=True, mapped=True),
            ),
            WeatherEvaluation(
                policy_id="weather",
                enabled=True,
                active=True,
                weight=1.0,
                salience=1.0,
                intensity=0.5,
                effective_magnitude=0.2,
                details=WeatherDetails(weather_id=800, available=True, mapped=True),
            ),
        ]
        ticks = [_make_trace(tick_id=i, policy_evaluations=[e]) for i, e in enumerate(evals, 1)]
        bucket = map_policy(ticks)
        assert bucket.weather.dominant_weather_id == 500
        assert bucket.weather.effective_magnitude == pytest.approx(0.4)

    def test_activity_distribution(self):
        evals = [
            ActivityEvaluation(
                policy_id="activity",
                enabled=True,
                active=True,
                weight=1.0,
                salience=1.0,
                intensity=0.5,
                effective_magnitude=0.4,
                direction={"focus": 1.0, "rain": 0.0},
                details=ActivityDetails(),
            ),
            ActivityEvaluation(
                policy_id="activity",
                enabled=True,
                active=True,
                weight=1.0,
                salience=1.0,
                intensity=0.5,
                effective_magnitude=0.6,
                direction={"focus": 0.5, "rain": 0.5},
                details=ActivityDetails(),
            ),
        ]
        ticks = [_make_trace(tick_id=i, policy_evaluations=[e]) for i, e in enumerate(evals, 1)]
        bucket = map_policy(ticks)
        # avg_magnitude = (0.4 + 0.6) / 2 = 0.5
        # focus: avg_dir = (1.0 + 0.5) / 2 = 0.75, distribution = 0.75 * 0.5 = 0.375
        # rain: avg_dir = (0.0 + 0.5) / 2 = 0.25, distribution = 0.25 * 0.5 = 0.125
        assert bucket.activity.distribution["focus"] == pytest.approx(0.375)
        assert bucket.activity.distribution["rain"] == pytest.approx(0.125)

    def test_time_max_magnitude(self):
        evals = [
            TimeEvaluation(
                policy_id="time",
                enabled=True,
                active=True,
                weight=1.0,
                salience=1.0,
                intensity=0.5,
                effective_magnitude=0.3,
                dominant_tag="day",
            ),
            TimeEvaluation(
                policy_id="time",
                enabled=True,
                active=True,
                weight=1.0,
                salience=1.0,
                intensity=0.5,
                effective_magnitude=0.8,
                dominant_tag="night",
            ),
        ]
        ticks = [_make_trace(tick_id=i, policy_evaluations=[e]) for i, e in enumerate(evals, 1)]
        bucket = map_policy(ticks)
        assert bucket.time.effective_magnitude == pytest.approx(0.8)
        assert bucket.time.dominant_tag == "night"

    def test_season_max_magnitude(self):
        evals = [
            SeasonEvaluation(
                policy_id="season",
                enabled=True,
                active=True,
                weight=1.0,
                salience=1.0,
                intensity=0.5,
                effective_magnitude=0.6,
                dominant_tag="summer",
            ),
            SeasonEvaluation(
                policy_id="season",
                enabled=True,
                active=True,
                weight=1.0,
                salience=1.0,
                intensity=0.5,
                effective_magnitude=0.2,
                dominant_tag="winter",
            ),
        ]
        ticks = [_make_trace(tick_id=i, policy_evaluations=[e]) for i, e in enumerate(evals, 1)]
        bucket = map_policy(ticks)
        assert bucket.season.effective_magnitude == pytest.approx(0.6)
        assert bucket.season.dominant_tag == "summer"


class TestAggregatorAggregate:
    def test_returns_trace_bucket(self):
        ticks = [_make_trace(tick_id=i) for i in range(1, 4)]
        result = Aggregator.aggregate(ticks)
        assert result.match.scores
        assert result.decide is not None
        assert result.policy is not None


class TestTraceBucketStore:
    def test_empty_read_window(self):
        store = TraceBucketStore()
        window = store.read_window()
        assert window.live_tick_id is None
        assert window.buckets == []

    def test_flush_at_bucket_size(self):
        store = TraceBucketStore()
        for i in range(BUCKET_SIZE):
            store.update(_make_trace(tick_id=i))
        window = store.read_window()
        assert len(window.buckets) == 1
        bucket = window.buckets[0]
        assert bucket.index == 0
        assert bucket.tick_start == 0
        assert bucket.tick_end == BUCKET_SIZE - 1

    def test_multiple_buckets_index_sequencing(self):
        store = TraceBucketStore()
        for i in range(BUCKET_SIZE * 3):
            store.update(_make_trace(tick_id=i))
        window = store.read_window()
        assert len(window.buckets) == 3
        assert [b.index for b in window.buckets] == [0, 1, 2]

    def test_read_window_count_slicing(self):
        store = TraceBucketStore()
        for i in range(BUCKET_SIZE * 5):
            store.update(_make_trace(tick_id=i))
        window = store.read_window(count=2)
        assert len(window.buckets) == 2
        assert window.buckets[0].index == 3
        assert window.buckets[1].index == 4

    def test_ring_buffer_eviction(self):
        store = TraceBucketStore(max_buckets=2)
        for i in range(BUCKET_SIZE * 4):
            store.update(_make_trace(tick_id=i))
        window = store.read_window()
        assert len(window.buckets) == 2
        assert window.buckets[0].index == 2
        assert window.buckets[1].index == 3

    def test_ts_start_end_from_buffer(self):
        store = TraceBucketStore()
        for i in range(BUCKET_SIZE):
            store.update(_make_trace(tick_id=i + 100))
        bucket = store.read_window().buckets[0]
        assert bucket.ts_start == 1714800000.0 + 100
        assert bucket.ts_end == 1714800000.0 + 100 + BUCKET_SIZE - 1

    def test_live_tick_id_tracks_latest(self):
        store = TraceBucketStore()
        store.update(_make_trace(tick_id=42))
        assert store.live_tick_id == 42
        store.update(_make_trace(tick_id=99))
        assert store.live_tick_id == 99
