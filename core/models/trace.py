from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

from core.models.playlist import Playlists

if TYPE_CHECKING:
    from core.models.context import Context


class Action(StrEnum):
    NONE = "none"
    SWITCH = "switch"
    CYCLE = "cycle"
    HOLD = "hold"
    PAUSE = "pause"


class Blocker(StrEnum):
    COOLDOWN = "cooldown"
    FULLSCREEN = "fullscreen"
    CPU = "cpu"
    IDLE = "idle"


@dataclass
class ActivityDetails:
    match_source: Literal["title", "process", "none"] = "none"
    matched_rule: str | None = None
    matched_tag: str | None = None
    window_title: str = ""
    process: str = ""
    ema_active: bool = False


@dataclass
class TimeDetails:
    auto: bool = False
    hour: float = 0.0
    virtual_hour: float = 0.0
    day_start_hour: float = 0.0
    night_start_hour: float = 0.0
    peaks: dict[str, float] = field(default_factory=dict)


@dataclass
class SeasonDetails:
    day_of_year: int = 0
    peaks: dict[str, int] = field(default_factory=dict)


@dataclass
class WeatherDetails:
    weather_id: int | None = None
    weather_main: str | None = None
    available: bool = False
    mapped: bool = False


@dataclass
class BaseEvaluation:
    policy_id: str
    enabled: bool
    active: bool
    weight: float
    salience: float
    intensity: float
    effective_magnitude: float
    direction: dict[str, float] = field(default_factory=dict)
    raw_contribution: dict[str, float] = field(default_factory=dict)
    resolved_contribution: dict[str, float] = field(default_factory=dict)
    dominant_tag: str | None = None


@dataclass
class ActivityEvaluation(BaseEvaluation):
    details: ActivityDetails = field(default_factory=ActivityDetails)


@dataclass
class TimeEvaluation(BaseEvaluation):
    details: TimeDetails = field(default_factory=TimeDetails)


@dataclass
class SeasonEvaluation(BaseEvaluation):
    details: SeasonDetails = field(default_factory=SeasonDetails)


@dataclass
class WeatherEvaluation(BaseEvaluation):
    details: WeatherDetails = field(default_factory=WeatherDetails)


type PolicyEvaluation = ActivityEvaluation | TimeEvaluation | SeasonEvaluation | WeatherEvaluation


class DecisionMode(StrEnum):
    NORMAL = "normal"
    MANUAL = "manual"
    RECOVERY = "recovery"
    PAUSE = "pause"


@dataclass(frozen=True)
class ActPlan:
    mode: DecisionMode
    active_playlists: Playlists


@dataclass
class ThinkResult:
    match: Match
    decision: Decision
    plan: ActPlan


@dataclass
class Match:
    best_playlists: Playlists
    playlist_matches: list[tuple[str, float]] = field(default_factory=list)
    # Direct policy outputs keyed by tag name, before fallback expansion.
    # Used by action_history for user-facing log entries.
    raw_context_vector: dict[str, float] = field(default_factory=dict)
    # Same data after fallback expansion — fed into cosine-similarity scoring.
    resolved_context_vector: dict[str, float] = field(default_factory=dict)
    fallback_expansions: dict[str, dict[str, float]] = field(default_factory=dict)
    policy_evaluations: list[PolicyEvaluation] = field(default_factory=list)
    max_policy_magnitude: float = 0.0
    similarity: float = 0.0
    similarity_gap: float = 0.0


@dataclass
class BlockerEvaluation:
    blocked_by: list[Blocker] = field(default_factory=list)
    cooldown_remaining: float = 0.0
    idle_seconds: float = 0.0
    idle_threshold: float = 0.0
    cpu_percent: float = 0.0
    cpu_threshold: float | None = None
    fullscreen: bool = False
    force_after_remaining: float | None = None

    @property
    def allowed(self) -> bool:
        return len(self.blocked_by) == 0


@dataclass
class Decision:
    """Final controller decision for one tick."""

    action: Action
    target: Playlists
    evaluation: BlockerEvaluation | None = None


@dataclass
class ActionResult:
    target_playlist: str | None = None
    executed: bool = False


@dataclass
class TickTrace:
    tick_id: int
    ts: float
    paused: bool
    pause_until: float
    context: Context
    think: ThinkResult
    action: ActionResult

    @property
    def match(self) -> Match:
        return self.think.match

    @property
    def decision(self) -> Decision:
        return self.think.decision

    @property
    def active_playlists(self) -> Playlists:
        return self.think.plan.active_playlists

    @property
    def target(self) -> Playlists:
        if self.action.executed and self.think.decision.action == Action.SWITCH:
            return self.think.decision.target
        return self.think.plan.active_playlists

    @property
    def cache_update(self) -> Playlists | None:
        if self.action.executed and self.think.decision.action == Action.SWITCH:
            return self.target
        return None
