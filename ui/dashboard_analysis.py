from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from core.context import WeatherData
from core.diagnostics import (
    ActionKind,
    ActionReasonCode,
    ActivityPolicyEvaluation,
    ControllerBlocker,
    ControllerEvaluation,
    PolicyEvaluation,
    SchedulerTickTrace,
    SeasonPolicyEvaluation,
    TimePolicyEvaluation,
    WeatherPolicyEvaluation,
)
from core.playlist import Playlists


def _round_float(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _playlist_or_none(playlist: str | None) -> str | None:
    """Scheduler internals use empty string for "no playlist"; API uses null."""
    if not playlist:
        return None
    return playlist


def _sorted_tag_items(items: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(items.items(), key=lambda item: (-item[1], item[0]))


class ApiDto(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class TagWeightDto(ApiDto):
    tag: str
    weight: float


class ResolvedTagWeightDto(ApiDto):
    resolved_tag: str
    weight: float


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


class ActivityPolicyDetailsDto(ApiDto):
    match_source: str
    matched_rule: str | None
    matched_tag: str | None
    window_title: str
    process: str
    ema_active: bool


class TimePolicyDetailsDto(ApiDto):
    auto: bool
    hour: float
    virtual_hour: float
    day_start_hour: float
    night_start_hour: float
    peaks: dict[str, float]


class SeasonPolicyDetailsDto(ApiDto):
    day_of_year: int
    peaks: dict[str, int]


class WeatherPolicyDetailsDto(ApiDto):
    weather_id: int | None
    weather_main: str | None
    available: bool
    mapped: bool


class BasePolicyDiagnosticDto(ApiDto):
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


class ActivityPolicyDiagnosticDto(BasePolicyDiagnosticDto):
    details: ActivityPolicyDetailsDto


class TimePolicyDiagnosticDto(BasePolicyDiagnosticDto):
    details: TimePolicyDetailsDto


class SeasonPolicyDiagnosticDto(BasePolicyDiagnosticDto):
    details: SeasonPolicyDetailsDto


class WeatherPolicyDiagnosticDto(BasePolicyDiagnosticDto):
    details: WeatherPolicyDetailsDto


PolicyDiagnosticDto = ActivityPolicyDiagnosticDto | TimePolicyDiagnosticDto | SeasonPolicyDiagnosticDto | WeatherPolicyDiagnosticDto


class ControllerEvaluationDto(ApiDto):
    operation: str
    allowed: bool
    blocked_by: list[ControllerBlocker]
    cooldown_remaining: float
    idle_seconds: float
    idle_threshold: float
    cpu_percent: float
    cpu_threshold: float | None
    fullscreen: bool
    force_after_remaining: float | None


class ControllerDiagnosticDto(ApiDto):
    evaluation: ControllerEvaluationDto | None


class PlaylistRefDto(ApiDto):
    name: str
    display: str  # fallback from name if no display
    color: str | None  # canonical config playlists have a color; unknown historical refs may not


class ActionDecisionDto(ApiDto):
    kind: ActionKind
    reason_code: ActionReasonCode
    executed: bool
    active_playlists_before: list[PlaylistRefDto]
    active_playlists_after: list[PlaylistRefDto]
    matched_playlists: list[PlaylistRefDto]


class TopMatchDto(ApiDto):
    playlist: PlaylistRefDto
    score: float


class SenseSnapshotDto(ApiDto):
    window: WindowSnapshotDto
    idle: IdleSnapshotDto
    cpu: CpuSnapshotDto
    fullscreen: bool
    weather: WeatherSnapshotDto
    clock: ClockSnapshotDto


class ThinkSnapshotDto(ApiDto):
    raw_context_vector: list[TagWeightDto]
    resolved_context_vector: list[TagWeightDto]
    fallback_expansions: dict[str, list[ResolvedTagWeightDto]]
    policies: list[PolicyDiagnosticDto]


class ActSnapshotDto(ApiDto):
    top_matches: list[TopMatchDto]
    controller: ControllerDiagnosticDto
    decision: ActionDecisionDto


class TickSummaryDto(ApiDto):
    tick_id: int
    ts: float
    similarity: float
    similarity_gap: float
    active_playlists: list[PlaylistRefDto]
    matched_playlists: list[PlaylistRefDto]
    action_kind: ActionKind
    reason_code: ActionReasonCode
    paused: bool
    executed: bool
    has_event: bool


class TickSnapshotDto(ApiDto):
    summary: TickSummaryDto
    sense: SenseSnapshotDto
    think: ThinkSnapshotDto
    act: ActSnapshotDto


class TickWindowResponseDto(ApiDto):
    live_tick_id: int | None
    ticks: list[TickSnapshotDto]


@dataclass(frozen=True)
class AnalysisTraceWindow:
    live_tick_id: int | None
    traces: list[SchedulerTickTrace]


def _playlist_ref_from_name(playlist: str) -> PlaylistRefDto:
    managed = Playlists.managed()
    displays = managed.displays()
    colors = managed.colors()
    return PlaylistRefDto(
        name=playlist,
        display=displays.get(playlist, playlist),
        color=colors.get(playlist),
    )


def _playlist_refs(playlists: Playlists) -> list[PlaylistRefDto]:
    return [_playlist_ref_from_name(name) for name in playlists.names() if name]


def _playlist_ref(playlist: str | None) -> PlaylistRefDto | None:
    normalized_playlist = _playlist_or_none(playlist)
    if normalized_playlist is None:
        return None
    return _playlist_ref_from_name(normalized_playlist)


class AnalysisStore:
    def __init__(self, tick_history: int = 1200):
        self._lock = threading.Lock()
        self._ticks: deque[SchedulerTickTrace] = deque(maxlen=tick_history)
        self._live_tick_id: int | None = None

    def update(self, trace: SchedulerTickTrace) -> None:
        with self._lock:
            self._ticks.append(trace)
            self._live_tick_id = trace.tick_id

    def read_window(self, count: int | None = None) -> AnalysisTraceWindow:
        with self._lock:
            items = list(self._ticks)
            live_tick_id = self._live_tick_id
            if count is not None:
                items = items[-count:]
        return AnalysisTraceWindow(live_tick_id=live_tick_id, traces=items)


def _tag_weights(values: dict[str, float]) -> list[TagWeightDto]:
    return [TagWeightDto(tag=tag, weight=_round_float(weight)) for tag, weight in _sorted_tag_items(values)]


def _resolved_tag_weights(values: dict[str, float]) -> list[ResolvedTagWeightDto]:
    return [ResolvedTagWeightDto(resolved_tag=tag, weight=_round_float(weight)) for tag, weight in _sorted_tag_items(values)]


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


def _policy_base_dto(policy: PolicyEvaluation) -> BasePolicyDiagnosticDto:
    return BasePolicyDiagnosticDto(
        policy_id=policy.policy_id,
        enabled=policy.enabled,
        active=policy.active,
        weight=_round_float(policy.weight),
        salience=_round_float(policy.salience),
        intensity=_round_float(policy.intensity),
        effective_magnitude=_round_float(policy.effective_magnitude),
        direction=_tag_weights(policy.direction),
        raw_contribution=_tag_weights(policy.raw_contribution),
        resolved_contribution=_tag_weights(policy.resolved_contribution),
        dominant_tag=policy.dominant_tag,
    )


def _policy_diagnostic(policy: PolicyEvaluation) -> PolicyDiagnosticDto:
    base_dto = _policy_base_dto(policy)
    base_kwargs = base_dto.model_dump()
    if isinstance(policy, ActivityPolicyEvaluation):
        return ActivityPolicyDiagnosticDto(
            **base_kwargs,
            details=ActivityPolicyDetailsDto(
                match_source=policy.details.match_source,
                matched_rule=policy.details.matched_rule,
                matched_tag=policy.details.matched_tag,
                window_title=policy.details.window_title,
                process=policy.details.process,
                ema_active=policy.details.ema_active,
            ),
        )
    if isinstance(policy, TimePolicyEvaluation):
        return TimePolicyDiagnosticDto(
            **base_kwargs,
            details=TimePolicyDetailsDto(
                auto=policy.details.auto,
                hour=_round_float(policy.details.hour),
                virtual_hour=_round_float(policy.details.virtual_hour),
                day_start_hour=_round_float(policy.details.day_start_hour),
                night_start_hour=_round_float(policy.details.night_start_hour),
                peaks={key: _round_float(value) for key, value in sorted(policy.details.peaks.items())},
            ),
        )
    if isinstance(policy, SeasonPolicyEvaluation):
        return SeasonPolicyDiagnosticDto(
            **base_kwargs,
            details=SeasonPolicyDetailsDto(
                day_of_year=policy.details.day_of_year,
                peaks=dict(sorted(policy.details.peaks.items())),
            ),
        )
    if isinstance(policy, WeatherPolicyEvaluation):
        return WeatherPolicyDiagnosticDto(
            **base_kwargs,
            details=WeatherPolicyDetailsDto(
                weather_id=policy.details.weather_id,
                weather_main=policy.details.weather_main,
                available=policy.details.available,
                mapped=policy.details.mapped,
            ),
        )
    raise TypeError(f"Unsupported policy evaluation type: {type(policy)!r}")


def _controller_evaluation(
    evaluation: ControllerEvaluation | None,
) -> ControllerEvaluationDto | None:
    if evaluation is None:
        return None
    return ControllerEvaluationDto(
        operation=evaluation.operation,
        allowed=evaluation.allowed,
        blocked_by=list(evaluation.blocked_by),
        cooldown_remaining=_round_float(evaluation.cooldown_remaining),
        idle_seconds=_round_float(evaluation.idle_seconds),
        idle_threshold=_round_float(evaluation.idle_threshold),
        cpu_percent=_round_float(evaluation.cpu_percent),
        cpu_threshold=_round_float(evaluation.cpu_threshold),
        fullscreen=evaluation.fullscreen,
        force_after_remaining=_round_float(evaluation.force_after_remaining),
    )


def map_tick_snapshot(trace: SchedulerTickTrace) -> TickSnapshotDto:
    matched_playlist_refs = _playlist_refs(trace.match.best_playlists)
    action_matched_playlist_refs = _playlist_refs(trace.action.decision.matched_playlists)
    active_playlists_after_refs = _playlist_refs(trace.action.effective_playlists_after)
    active_playlists_before_refs = _playlist_refs(trace.action.effective_playlists_before)
    has_event = trace.action.kind in {ActionKind.SWITCH, ActionKind.CYCLE}

    return TickSnapshotDto(
        summary=TickSummaryDto(
            tick_id=trace.tick_id,
            ts=trace.ts,
            similarity=_round_float(trace.match.similarity),
            similarity_gap=_round_float(trace.match.similarity_gap),
            active_playlists=active_playlists_after_refs,
            matched_playlists=matched_playlist_refs,
            action_kind=trace.action.kind,
            reason_code=trace.action.reason_code,
            paused=trace.paused,
            executed=trace.action.executed,
            has_event=has_event,
        ),
        sense=SenseSnapshotDto(
            window=WindowSnapshotDto(
                process=trace.context.window.process or "",
                title=trace.context.window.title or "",
            ),
            idle=IdleSnapshotDto(seconds=_round_float(trace.context.idle)),
            cpu=CpuSnapshotDto(average_percent=_round_float(trace.context.cpu)),
            fullscreen=trace.context.fullscreen,
            weather=_weather_snapshot(trace.context.weather),
            clock=_clock_snapshot(trace.context.time),
        ),
        think=ThinkSnapshotDto(
            raw_context_vector=_tag_weights(trace.match.raw_context_vector),
            resolved_context_vector=_tag_weights(trace.match.resolved_context_vector),
            fallback_expansions={
                source_tag: _resolved_tag_weights(expansions) for source_tag, expansions in sorted(trace.match.fallback_expansions.items())
            },
            policies=[_policy_diagnostic(policy) for policy in trace.match.policy_evaluations],
        ),
        act=ActSnapshotDto(
            top_matches=[
                TopMatchDto(
                    playlist=_playlist_ref_from_name(playlist),
                    score=_round_float(score),
                )
                for playlist, score in trace.match.playlist_matches[:5]
            ],
            controller=ControllerDiagnosticDto(evaluation=_controller_evaluation(trace.action.evaluation)),
            decision=ActionDecisionDto(
                kind=trace.action.kind,
                reason_code=trace.action.reason_code,
                executed=trace.action.executed,
                active_playlists_before=active_playlists_before_refs,
                active_playlists_after=active_playlists_after_refs,
                matched_playlists=action_matched_playlist_refs,
            ),
        ),
    )


def build_tick_snapshot(trace: SchedulerTickTrace) -> dict[str, Any]:
    snapshot = map_tick_snapshot(trace)
    return snapshot.model_dump(mode="json", by_alias=True)


def build_tick_window_response(window: AnalysisTraceWindow) -> dict[str, Any]:
    response = TickWindowResponseDto(
        live_tick_id=window.live_tick_id,
        ticks=[map_tick_snapshot(trace) for trace in window.traces],
    )
    return response.model_dump(mode="json", by_alias=True)
