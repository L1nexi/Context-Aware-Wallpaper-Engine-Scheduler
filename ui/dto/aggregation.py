from __future__ import annotations

from typing import Any

from ui.aggregation import (
    ActivityBucket,
    SeasonBucket,
    TimeBucket,
    TraceBucket,
    TraceBucketWindow,
    WeatherBucket,
)
from ui.dto.base import ApiDto, format_float


class WeatherBucketDto(ApiDto):
    dominant_weather_id: int | None = None
    effective_magnitude: float = 0.0


class ActivityBucketDto(ApiDto):
    distribution: dict[str, float] = {}


class TimeBucketDto(ApiDto):
    effective_magnitude: float = 0.0
    dominant_tag: str | None = None


class SeasonBucketDto(ApiDto):
    effective_magnitude: float = 0.0
    dominant_tag: str | None = None


class MatchBucketDto(ApiDto):
    scores: dict[str, float] = {}


class DecideBucketDto(ApiDto):
    active_pool: list[str] = []
    has_cycle: bool = False
    blockers: dict[str, int] = {}


class PolicyBucketDto(ApiDto):
    weather: WeatherBucketDto
    activity: ActivityBucketDto
    time: TimeBucketDto
    season: SeasonBucketDto


class TraceBucketDto(ApiDto):
    match: MatchBucketDto
    decide: DecideBucketDto
    policy: PolicyBucketDto


class TickBucketDto(ApiDto):
    index: int
    tick_start: int
    tick_end: int
    ts_start: float
    ts_end: float
    trace: TraceBucketDto


class TraceBucketWindowResponseDto(ApiDto):
    live_tick_id: int | None
    buckets: list[TickBucketDto]


def _map_weather(bucket: WeatherBucket) -> WeatherBucketDto:
    return WeatherBucketDto(
        dominant_weather_id=bucket.dominant_weather_id,
        effective_magnitude=format_float(bucket.effective_magnitude),
    )


def _map_activity(bucket: ActivityBucket) -> ActivityBucketDto:
    return ActivityBucketDto(
        distribution={tag: format_float(w) for tag, w in bucket.distribution.items()},
    )


def _map_time(bucket: TimeBucket) -> TimeBucketDto:
    return TimeBucketDto(
        effective_magnitude=format_float(bucket.effective_magnitude),
        dominant_tag=bucket.dominant_tag,
    )


def _map_season(bucket: SeasonBucket) -> SeasonBucketDto:
    return SeasonBucketDto(
        effective_magnitude=format_float(bucket.effective_magnitude),
        dominant_tag=bucket.dominant_tag,
    )


def _map_trace(bucket: TraceBucket) -> TraceBucketDto:
    return TraceBucketDto(
        match=MatchBucketDto(
            scores={tag: format_float(s) for tag, s in bucket.match.scores.items()},
        ),
        decide=DecideBucketDto(
            active_pool=list(bucket.decide.active_pool),
            has_cycle=bucket.decide.has_cycle,
            blockers=dict(bucket.decide.blockers),
        ),
        policy=PolicyBucketDto(
            weather=_map_weather(bucket.policy.weather),
            activity=_map_activity(bucket.policy.activity),
            time=_map_time(bucket.policy.time),
            season=_map_season(bucket.policy.season),
        ),
    )


def build_trace_bucket_response(window: TraceBucketWindow) -> dict[str, Any]:
    response = TraceBucketWindowResponseDto(
        live_tick_id=window.live_tick_id,
        buckets=[
            TickBucketDto(
                index=b.index,
                tick_start=b.tick_start,
                tick_end=b.tick_end,
                ts_start=format_float(b.ts_start),
                ts_end=format_float(b.ts_end),
                trace=_map_trace(b.trace),
            )
            for b in window.buckets
        ],
    )
    return response.model_dump(mode="json", by_alias=True)
