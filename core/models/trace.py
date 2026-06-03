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


class ActionReason(StrEnum):
    """Primary decision summary for one tick.

    Exactly one reason is chosen for a decision. When multiple blockers are
    active, this enum stores only the controller-prioritized primary cause.
    """

    NO_MATCH = "no_match"
    HOLD_SAME_PLAYLIST = "hold_same_playlist"
    HOLD_SEMANTIC_CONTINUITY = "hold_semantic_continuity"
    SWITCH_ALLOWED = "switch_allowed"
    SWITCH_BLOCKED_COOLDOWN = "switch_blocked_cooldown"
    SWITCH_BLOCKED_FULLSCREEN = "switch_blocked_fullscreen"
    SWITCH_BLOCKED_CPU = "switch_blocked_cpu"
    SWITCH_BLOCKED_NOT_IDLE = "switch_blocked_not_idle"
    CYCLE_ALLOWED = "cycle_allowed"
    CYCLE_BLOCKED_COOLDOWN = "cycle_blocked_cooldown"
    CYCLE_BLOCKED_FULLSCREEN = "cycle_blocked_fullscreen"
    CYCLE_BLOCKED_CPU = "cycle_blocked_cpu"
    CYCLE_BLOCKED_NOT_IDLE = "cycle_blocked_not_idle"
    SCHEDULER_PAUSED = "scheduler_paused"
    MANUAL_APPLY_REQUESTED = "manual_apply_requested"
    RECOVERY_UNMANAGED = "recovery_unmanaged"
    RECOVERY_NO_MATCH = "recovery_no_match"


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
    """Final controller decision for one tick.

    `reason` is the prioritized single-cause summary for UI/status use,
    while the paired evaluation retains the complete blocker facts.
    """

    action: Action
    reason: ActionReason
    matched: Playlists
    evaluation: BlockerEvaluation | None = None


@dataclass
class ActionResult:
    decision: Decision
    active_playlists_before: Playlists
    active_playlists_after: Playlists
    target_playlist: str | None = None
    executed: bool = False

    @property
    def action(self) -> Action:
        return self.decision.action

    @property
    def reason(self) -> ActionReason:
        return self.decision.reason

    @property
    def evaluation(self) -> BlockerEvaluation | None:
        return self.decision.evaluation

    @property
    def cache_update(self) -> Playlists | None:
        if self.executed and self.action == Action.SWITCH:
            return self.active_playlists_after
        return None


@dataclass
class TickTrace:
    tick_id: int
    ts: float
    paused: bool
    pause_until: float
    context: Context
    match: Match
    action: ActionResult
