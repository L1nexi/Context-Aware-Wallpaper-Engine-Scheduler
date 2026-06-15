from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from core.models.context import WeatherData
from core.models.playlist import Playlists
from core.models.trace import (
    Action,
    ActivityEvaluation,
    Blocker,
    BlockerEvaluation,
    DecisionMode,
    PolicyEvaluation,
    SeasonEvaluation,
    TickTrace,
    TimeEvaluation,
    WeatherEvaluation,
)
from ui.dto.base import ApiDto, format_float

if TYPE_CHECKING:
    from ui.tick_trace_store import TickTraceWindow

class TagWeightDto(ApiDto):
    tag: str
    weight: float


class ResolvedTagWeightDto(ApiDto):
    resolved_tag: str
    weight: float


class PlaylistCatalogItemDto(ApiDto):
    name: str
    display: str
    color: str | None
    item_count: int


class CatalogDto(ApiDto):
    playlists: list[PlaylistCatalogItemDto]

    @classmethod
    def from_managed_playlists(cls) -> CatalogDto:
        managed = Playlists.managed()
        displays = managed.displays()
        colors = managed.colors()
        item_counts = managed.item_counts()
        return cls(
            playlists=[
                PlaylistCatalogItemDto(
                    name=name,
                    display=displays.get(name, name),
                    color=colors.get(name),
                    item_count=item_counts.get(name, 0),
                )
                for name in managed.names()
            ],
        )


class WindowSnapshotDto(ApiDto):
    process: str
    title: str


class IdleSnapshotDto(ApiDto):
    seconds: float


class CpuSnapshotDto(ApiDto):
    average_percent: float


class WeatherSnapshotDto(ApiDto):
    available: bool
    stale: bool
    id: int | None
    main: str | None
    sunrise: int | None
    sunset: int | None


class ClockSnapshotDto(ApiDto):
    local_ts: int
    hour: int
    day_of_year: int


class ActivityDetailsDto(ApiDto):
    match_source: str
    matched_rule: str | None
    matched_tag: str | None
    window_title: str
    process: str
    ema_active: bool


class TimeDetailsDto(ApiDto):
    auto: bool
    hour: float
    virtual_hour: float
    day_start_hour: float
    night_start_hour: float
    peaks: dict[str, float]


class SeasonDetailsDto(ApiDto):
    day_of_year: int
    peaks: dict[str, int]


class WeatherDetailsDto(ApiDto):
    weather_id: int | None
    weather_main: str | None
    available: bool
    mapped: bool


class BaseEvaluationDto(ApiDto):
    policy_id: str
    enabled: bool
    active: bool
    weight: float
    salience: float
    intensity: float
    effective_magnitude: float
    direction: list[TagWeightDto]
    raw_contribution: list[TagWeightDto]
    resolved_contribution: list[TagWeightDto]
    dominant_tag: str | None


class ActivityEvaluationDto(BaseEvaluationDto):
    details: ActivityDetailsDto


class TimeEvaluationDto(BaseEvaluationDto):
    details: TimeDetailsDto


class SeasonEvaluationDto(BaseEvaluationDto):
    details: SeasonDetailsDto


class WeatherEvaluationDto(BaseEvaluationDto):
    details: WeatherDetailsDto


EvaluationDto = ActivityEvaluationDto | TimeEvaluationDto | SeasonEvaluationDto | WeatherEvaluationDto


class BlockerEvaluationDto(ApiDto):
    allowed: bool
    blocked_by: list[Blocker]
    cooldown_remaining: float
    idle_seconds: float
    idle_threshold: float
    cpu_percent: float
    cpu_threshold: float | None
    fullscreen: bool
    force_after_remaining: float | None


class PlaylistMatchDto(ApiDto):
    playlist: str
    score: float


class SenseSnapshotDto(ApiDto):
    window: WindowSnapshotDto
    idle: IdleSnapshotDto
    cpu: CpuSnapshotDto
    fullscreen: bool
    weather: WeatherSnapshotDto
    clock: ClockSnapshotDto


class MatchSnapshotDto(ApiDto):
    best_playlists: list[str]
    playlist_matches: list[PlaylistMatchDto]
    raw_context_vector: list[TagWeightDto]
    resolved_context_vector: list[TagWeightDto]
    fallback_expansions: dict[str, list[ResolvedTagWeightDto]]
    policies: list[EvaluationDto]
    max_policy_magnitude: float
    similarity: float
    similarity_gap: float


class PlanSnapshotDto(ApiDto):
    mode: DecisionMode
    active_playlists: list[str]


class DecideSnapshotDto(ApiDto):
    action: Action
    target_playlists: list[str]
    semantic_continuity: bool
    evaluation: BlockerEvaluationDto | None


class ActSnapshotDto(ApiDto):
    target_playlist: str | None
    executed: bool


class TickSummaryDto(ApiDto):
    tick_id: int
    ts: float
    pause_until: float
    similarity: float
    similarity_gap: float
    active_playlists: list[str]
    matched_playlists: list[str]
    action: Action
    paused: bool
    executed: bool
    has_event: bool


class TickSnapshotDto(ApiDto):
    summary: TickSummaryDto
    sense: SenseSnapshotDto
    match: MatchSnapshotDto
    plan: PlanSnapshotDto
    decide: DecideSnapshotDto
    act: ActSnapshotDto


class TickWindowResponseDto(ApiDto):
    live_tick_id: int | None
    catalog: CatalogDto
    ticks: list[TickSnapshotDto]


def _tag_weights(values: dict[str, float]) -> list[TagWeightDto]:
    sorted_tags = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    return [TagWeightDto(tag=tag, weight=format_float(weight)) for tag, weight in sorted_tags]


def _resolved_tag_weights(values: dict[str, float]) -> list[ResolvedTagWeightDto]:
    sorted_tags = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    return [ResolvedTagWeightDto(resolved_tag=tag, weight=format_float(weight)) for tag, weight in sorted_tags]


def _weather_snapshot(weather: WeatherData | None) -> WeatherSnapshotDto:
    if weather is None:
        return WeatherSnapshotDto(
            available=False,
            stale=False,
            id=None,
            main=None,
            sunrise=None,
            sunset=None,
        )
    return WeatherSnapshotDto(
        available=True,
        stale=weather.stale,
        id=weather.id or None,
        main=weather.main or None,
        sunrise=weather.sunrise or None,
        sunset=weather.sunset or None,
    )


def _clock_snapshot(local_time: time.struct_time) -> ClockSnapshotDto:
    return ClockSnapshotDto(
        local_ts=int(time.mktime(local_time)),
        hour=local_time.tm_hour,
        day_of_year=local_time.tm_yday,
    )


def _policy_base_dto(policy: PolicyEvaluation) -> BaseEvaluationDto:
    return BaseEvaluationDto(
        policy_id=policy.policy_id,
        enabled=policy.enabled,
        active=policy.active,
        weight=format_float(policy.weight),
        salience=format_float(policy.salience),
        intensity=format_float(policy.intensity),
        effective_magnitude=format_float(policy.effective_magnitude),
        direction=_tag_weights(policy.direction),
        raw_contribution=_tag_weights(policy.raw_contribution),
        resolved_contribution=_tag_weights(policy.resolved_contribution),
        dominant_tag=policy.dominant_tag,
    )


def _policy_diagnostic(policy: PolicyEvaluation) -> EvaluationDto:
    base_kwargs = _policy_base_dto(policy).model_dump()
    match policy:
        case ActivityEvaluation():
            return ActivityEvaluationDto(
                **base_kwargs,
                details=ActivityDetailsDto(
                    match_source=policy.details.match_source,
                    matched_rule=policy.details.matched_rule,
                    matched_tag=policy.details.matched_tag,
                    window_title=policy.details.window_title,
                    process=policy.details.process,
                    ema_active=policy.details.ema_active,
                ),
            )
        case TimeEvaluation():
            return TimeEvaluationDto(
                **base_kwargs,
                details=TimeDetailsDto(
                    auto=policy.details.auto,
                    hour=format_float(policy.details.hour),
                    virtual_hour=format_float(policy.details.virtual_hour),
                    day_start_hour=format_float(policy.details.day_start_hour),
                    night_start_hour=format_float(policy.details.night_start_hour),
                    peaks={key: format_float(value) for key, value in sorted(policy.details.peaks.items())},
                ),
            )
        case SeasonEvaluation():
            return SeasonEvaluationDto(
                **base_kwargs,
                details=SeasonDetailsDto(
                    day_of_year=policy.details.day_of_year,
                    peaks=dict(sorted(policy.details.peaks.items())),
                ),
            )
        case WeatherEvaluation():
            return WeatherEvaluationDto(
                **base_kwargs,
                details=WeatherDetailsDto(
                    weather_id=policy.details.weather_id,
                    weather_main=policy.details.weather_main,
                    available=policy.details.available,
                    mapped=policy.details.mapped,
                ),
            )
        case _:
            raise TypeError(f"Unsupported policy evaluation type: {type(policy)!r}")


def _controller_evaluation(
    evaluation: BlockerEvaluation | None,
) -> BlockerEvaluationDto | None:
    if evaluation is None:
        return None
    return BlockerEvaluationDto(
        allowed=evaluation.allowed,
        blocked_by=list(evaluation.blocked_by),
        cooldown_remaining=format_float(evaluation.cooldown_remaining),
        idle_seconds=format_float(evaluation.idle_seconds),
        idle_threshold=format_float(evaluation.idle_threshold),
        cpu_percent=format_float(evaluation.cpu_percent),
        cpu_threshold=format_float(evaluation.cpu_threshold),
        fullscreen=evaluation.fullscreen,
        force_after_remaining=format_float(evaluation.force_after_remaining),
    )


def map_tick_snapshot(trace: TickTrace) -> TickSnapshotDto:
    has_event = trace.decision.action in {Action.SWITCH, Action.CYCLE}

    return TickSnapshotDto(
        summary=TickSummaryDto(
            tick_id=trace.tick_id,
            ts=trace.ts,
            pause_until=trace.pause_until,
            similarity=format_float(trace.match.similarity),
            similarity_gap=format_float(trace.match.similarity_gap),
            active_playlists=trace.target.names(),
            matched_playlists=trace.match.best_playlists.names(),
            action=trace.decision.action,
            paused=trace.paused,
            executed=trace.action.executed,
            has_event=has_event,
        ),
        sense=SenseSnapshotDto(
            window=WindowSnapshotDto(
                process=trace.context.window.process or "",
                title=trace.context.window.title or "",
            ),
            idle=IdleSnapshotDto(seconds=format_float(trace.context.idle)),
            cpu=CpuSnapshotDto(average_percent=format_float(trace.context.cpu)),
            fullscreen=trace.context.fullscreen,
            weather=_weather_snapshot(trace.context.weather),
            clock=_clock_snapshot(trace.context.time),
        ),
        match=MatchSnapshotDto(
            best_playlists=trace.match.best_playlists.names(),
            playlist_matches=[
                PlaylistMatchDto(
                    playlist=playlist,
                    score=format_float(score),
                )
                for playlist, score in trace.match.playlist_matches
                if playlist
            ],
            raw_context_vector=_tag_weights(trace.match.raw_context_vector),
            resolved_context_vector=_tag_weights(trace.match.resolved_context_vector),
            fallback_expansions={
                source_tag: _resolved_tag_weights(expansions) for source_tag, expansions in sorted(trace.match.fallback_expansions.items())
            },
            policies=[_policy_diagnostic(policy) for policy in trace.match.policy_evaluations],
            max_policy_magnitude=format_float(trace.match.max_policy_magnitude),
            similarity=format_float(trace.match.similarity),
            similarity_gap=format_float(trace.match.similarity_gap),
        ),
        plan=PlanSnapshotDto(
            mode=trace.plan.mode,
            active_playlists=trace.plan.active_playlists.names(),
        ),
        decide=DecideSnapshotDto(
            action=trace.decision.action,
            target_playlists=trace.decision.target.names(),
            semantic_continuity=trace.decision.semantic_continuity,
            evaluation=_controller_evaluation(trace.decision.evaluation),
        ),
        act=ActSnapshotDto(
            target_playlist=trace.action.target_playlist,
            executed=trace.action.executed,
        ),
    )


def build_tick_snapshot(trace: TickTrace) -> dict[str, Any]:
    snapshot = map_tick_snapshot(trace)
    return snapshot.model_dump(mode="json", by_alias=True)


def build_tick_window_response(window: TickTraceWindow) -> dict[str, Any]:
    response = TickWindowResponseDto(
        live_tick_id=window.live_tick_id,
        catalog=CatalogDto.from_managed_playlists(),
        ticks=[map_tick_snapshot(trace) for trace in window.traces],
    )
    return response.model_dump(mode="json", by_alias=True)
