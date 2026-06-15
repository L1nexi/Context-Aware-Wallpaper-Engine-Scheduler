from __future__ import annotations

import json
import logging
import threading
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.context import get_data_dir
from core.models.trace import (
    Action,
    ActivityEvaluation,
    SeasonEvaluation,
    TickTrace,
    TimeEvaluation,
    WeatherEvaluation,
)

logger = logging.getLogger("WEScheduler.Aggregation")

BUCKET_SIZE = 60


@dataclass(frozen=True)
class WeatherBucket:
    dominant_weather_id: int | None = None
    effective_magnitude: float = 0.0


@dataclass(frozen=True)
class ActivityBucket:
    distribution: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class TimeBucket:
    effective_magnitude: float = 0.0
    dominant_tag: str | None = None


@dataclass(frozen=True)
class SeasonBucket:
    effective_magnitude: float = 0.0
    dominant_tag: str | None = None


@dataclass(frozen=True)
class MatchBucket:
    scores: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DecideBucket:
    active_pool: list[str] = field(default_factory=list)
    has_cycle: bool = False
    blockers: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyBucket:
    weather: WeatherBucket = field(default_factory=WeatherBucket)
    activity: ActivityBucket = field(default_factory=ActivityBucket)
    time: TimeBucket = field(default_factory=TimeBucket)
    season: SeasonBucket = field(default_factory=SeasonBucket)


@dataclass(frozen=True)
class TraceBucket:
    match: MatchBucket = field(default_factory=MatchBucket)
    decide: DecideBucket = field(default_factory=DecideBucket)
    policy: PolicyBucket = field(default_factory=PolicyBucket)


@dataclass(frozen=True)
class TickBucket:
    index: int
    tick_start: int
    tick_end: int
    ts_start: float
    ts_end: float
    trace: TraceBucket = field(default_factory=TraceBucket)


@dataclass(frozen=True)
class TraceBucketWindow:
    live_tick_id: int | None
    buckets: list[TickBucket]


def map_match(ticks: list[TickTrace]) -> MatchBucket:
    score_sums: dict[str, float] = {}
    n = len(ticks)
    for tick in ticks:
        for playlist_name, score in tick.match.playlist_matches:
            score_sums[playlist_name] = score_sums.get(playlist_name, 0.0) + score
    scores = {name: score_sum / n for name, score_sum in score_sums.items()}
    return MatchBucket(scores=scores)


def map_decide(ticks: list[TickTrace]) -> DecideBucket:
    last_tick = ticks[-1]
    active_pool = last_tick.active_playlists.names()
    has_cycle = any(tick.decision.action == Action.CYCLE for tick in ticks)

    blocker_counts: dict[str, int] = {}
    for tick in ticks:
        eval = tick.decision.evaluation
        if eval is not None and eval.blocked_by:
            for blocker in eval.blocked_by:
                blocker_counts[blocker.value] = blocker_counts.get(blocker.value, 0) + 1

    return DecideBucket(
        active_pool=active_pool,
        has_cycle=has_cycle,
        blockers=blocker_counts,
    )


def map_policy(ticks: list[TickTrace]) -> PolicyBucket:
    weather_evals: list[WeatherEvaluation] = []
    activity_evals: list[ActivityEvaluation] = []
    time_evals: list[TimeEvaluation] = []
    season_evals: list[SeasonEvaluation] = []

    for tick in ticks:
        for pe in tick.match.policy_evaluations:
            match pe:
                case WeatherEvaluation():
                    weather_evals.append(pe)
                case ActivityEvaluation():
                    activity_evals.append(pe)
                case TimeEvaluation():
                    time_evals.append(pe)
                case SeasonEvaluation():
                    season_evals.append(pe)

    return PolicyBucket(
        weather=_aggregate_weather(weather_evals),
        activity=_aggregate_activity(activity_evals),
        time=_aggregate_time(time_evals),
        season=_aggregate_season(season_evals),
    )


def _aggregate_weather(evals: list[WeatherEvaluation]) -> WeatherBucket:
    id_counts: Counter[int] = Counter()
    for e in evals:
        if e.details.weather_id is not None:
            id_counts[e.details.weather_id] += 1
    mode_id = id_counts.most_common(1)[0][0] if id_counts else None
    magnitudes = [e.effective_magnitude for e in evals]
    mean_mag = sum(magnitudes) / len(magnitudes) if magnitudes else 0.0

    return WeatherBucket(dominant_weather_id=mode_id, effective_magnitude=mean_mag)


def _aggregate_activity(evals: list[ActivityEvaluation]) -> ActivityBucket:
    if not evals:
        return ActivityBucket()

    direction_sums: dict[str, float] = {}
    magnitude_sum = 0.0

    for e in evals:
        magnitude_sum += e.effective_magnitude
        for tag, value in e.direction.items():
            direction_sums[tag] = direction_sums.get(tag, 0.0) + value

    n = len(evals)
    avg_magnitude = magnitude_sum / n

    distribution: dict[str, float] = {}
    for tag in direction_sums:
        avg_dir = direction_sums[tag] / n
        distribution[tag] = avg_dir * avg_magnitude

    return ActivityBucket(distribution=distribution)


def _aggregate_time(evals: list[TimeEvaluation]) -> TimeBucket:
    if not evals:
        return TimeBucket()

    best = max(evals, key=lambda e: e.effective_magnitude)
    return TimeBucket(
        effective_magnitude=best.effective_magnitude,
        dominant_tag=best.dominant_tag,
    )


def _aggregate_season(evals: list[SeasonEvaluation]) -> SeasonBucket:
    if not evals:
        return SeasonBucket()

    best = max(evals, key=lambda e: e.effective_magnitude)
    return SeasonBucket(
        effective_magnitude=best.effective_magnitude,
        dominant_tag=best.dominant_tag,
    )


class Aggregator:
    @staticmethod
    def aggregate(ticks: list[TickTrace]) -> TraceBucket:
        return TraceBucket(
            match=map_match(ticks),
            decide=map_decide(ticks),
            policy=map_policy(ticks),
        )


_AGGREGATED_TICKS_FILENAME = "aggregated_ticks.jsonl"


class TraceBucketStore:
    def __init__(
        self,
        max_buckets: int = 180,
        persist: bool = False,
    ) -> None:
        self.lock = threading.Lock()
        self.buffer: list[TickTrace] = []
        self.next_index: int = 0
        self.buckets: deque[TickBucket] = deque(maxlen=max_buckets)
        self.live_tick_id: int | None = None

        self.persist = persist
        self.persist_path: Path | None = None
        if persist:
            data_dir = get_data_dir()
            self.persist_path = Path(data_dir) / _AGGREGATED_TICKS_FILENAME

    def update(self, trace: TickTrace) -> None:
        with self.lock:
            self.live_tick_id = trace.tick_id
            self.buffer.append(trace)
            if len(self.buffer) >= BUCKET_SIZE:
                ticks = self.buffer
                self.buffer = []

                trace_bucket = Aggregator.aggregate(ticks)
                tick_bucket = TickBucket(
                    index=self.next_index,
                    tick_start=ticks[0].tick_id,
                    tick_end=ticks[-1].tick_id,
                    ts_start=ticks[0].ts,
                    ts_end=ticks[-1].ts,
                    trace=trace_bucket,
                )
                self.next_index += 1
                self.buckets.append(tick_bucket)
                if self.persist:
                    self.append_jsonl(tick_bucket)

    def read_window(self, count: int | None = None) -> TraceBucketWindow:
        with self.lock:
            items = list(self.buckets)
            live_tick_id = self.live_tick_id
            if count is not None:
                items = items[-count:]
        return TraceBucketWindow(live_tick_id=live_tick_id, buckets=items)

    def append_jsonl(self, bucket: TickBucket) -> None:
        assert self.persist_path is not None
        try:
            with self.persist_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(bucket), ensure_ascii=False) + "\n")
        except OSError:
            logger.warning(
                "Failed to persist bucket %d to %s",
                bucket.index,
                self.persist_path,
            )
