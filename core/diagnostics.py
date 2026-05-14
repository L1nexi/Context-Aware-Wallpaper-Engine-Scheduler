from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Literal, Optional, TypeAlias

if TYPE_CHECKING:
    from core.context import Context


class ActionKind(str, Enum):
    NONE = "none"
    SWITCH = "switch"
    CYCLE = "cycle"
    HOLD = "hold"
    PAUSE = "pause"


class ActionReasonCode(str, Enum):
    """Primary decision summary for one tick.

    Exactly one reason is chosen for a decision. When multiple blockers are
    active, this enum stores only the controller-prioritized primary cause.
    """

    NO_MATCH = "no_match"
    HOLD_SAME_PLAYLIST = "hold_same_playlist"
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


class ControllerBlocker(str, Enum):
    COOLDOWN = "cooldown"
    FULLSCREEN = "fullscreen"
    CPU = "cpu"
    IDLE = "idle"


@dataclass
class ActivityPolicyDetails:
    match_source: Literal["title", "process", "none"] = "none"
    matched_rule: Optional[str] = None
    matched_tag: Optional[str] = None
    window_title: str = ""
    process: str = ""
    ema_active: bool = False


@dataclass
class TimePolicyDetails:
    auto: bool = False
    hour: float = 0.0
    virtual_hour: float = 0.0
    day_start_hour: float = 0.0
    night_start_hour: float = 0.0
    peaks: dict[str, float] = field(default_factory=dict)


@dataclass
class SeasonPolicyDetails:
    day_of_year: int = 0
    peaks: dict[str, int] = field(default_factory=dict)


@dataclass
class WeatherPolicyDetails:
    weather_id: Optional[int] = None
    weather_main: Optional[str] = None
    available: bool = False
    mapped: bool = False


@dataclass
class BasePolicyEvaluation:
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
    dominant_tag: Optional[str] = None


@dataclass
class ActivityPolicyEvaluation(BasePolicyEvaluation):
    details: ActivityPolicyDetails = field(default_factory=ActivityPolicyDetails)


@dataclass
class TimePolicyEvaluation(BasePolicyEvaluation):
    details: TimePolicyDetails = field(default_factory=TimePolicyDetails)


@dataclass
class SeasonPolicyEvaluation(BasePolicyEvaluation):
    details: SeasonPolicyDetails = field(default_factory=SeasonPolicyDetails)


@dataclass
class WeatherPolicyEvaluation(BasePolicyEvaluation):
    details: WeatherPolicyDetails = field(default_factory=WeatherPolicyDetails)


PolicyEvaluation: TypeAlias = (
    ActivityPolicyEvaluation
    | TimePolicyEvaluation
    | SeasonPolicyEvaluation
    | WeatherPolicyEvaluation
)


@dataclass
class MatchEvaluation:
    best_playlist: Optional[str]
    playlist_matches: list[tuple[str, float]] = field(default_factory=list)
    raw_context_vector: dict[str, float] = field(default_factory=dict)
    resolved_context_vector: dict[str, float] = field(default_factory=dict)
    fallback_expansions: dict[str, dict[str, float]] = field(default_factory=dict)
    policy_evaluations: list[PolicyEvaluation] = field(default_factory=list)
    max_policy_magnitude: float = 0.0

    @property
    def similarity(self) -> float:
        return self.playlist_matches[0][1] if self.playlist_matches else 0.0

    @property
    def similarity_gap(self) -> float:
        if not self.playlist_matches:
            return 0.0
        if len(self.playlist_matches) == 1:
            return self.playlist_matches[0][1]
        return self.playlist_matches[0][1] - self.playlist_matches[1][1]


ControllerOperation: TypeAlias = Literal["switch", "cycle"]


@dataclass
class ControllerEvaluation:
    """Full controller evaluation for the chosen operation.

    `blocked_by` keeps the complete set of active blockers on this path, not
    just the primary reason surfaced in `ControllerDecision.reason_code`.
    """

    operation: ControllerOperation
    allowed: bool
    blocked_by: list[ControllerBlocker] = field(default_factory=list)
    cooldown_remaining: float = 0.0
    idle_seconds: float = 0.0
    idle_threshold: float = 0.0
    cpu_percent: float = 0.0
    cpu_threshold: Optional[float] = None
    fullscreen: bool = False
    force_after_remaining: Optional[float] = None


@dataclass
class ControllerDecision:
    """Final controller decision for one tick.

    `reason_code` is the prioritized single-cause summary for UI/status use,
    while the paired evaluation retains the complete blocker facts.
    """

    kind: ActionKind
    reason_code: ActionReasonCode
    matched_playlist: Optional[str]
    evaluation: Optional[ControllerEvaluation] = None


@dataclass
class ActuationOutcome:
    decision: ControllerDecision
    active_playlist_before: str
    active_playlist_after: str
    executed: bool = False

    @property
    def kind(self) -> ActionKind:
        return self.decision.kind

    @property
    def reason_code(self) -> ActionReasonCode:
        return self.decision.reason_code

    @property
    def matched_playlist(self) -> Optional[str]:
        return self.decision.matched_playlist

    @property
    def evaluation(self) -> Optional[ControllerEvaluation]:
        return self.decision.evaluation


@dataclass
class SchedulerTickTrace:
    tick_id: int
    ts: float
    paused: bool
    pause_until: float
    active_playlist_before: str
    active_playlist_after: str
    context: Context
    match: MatchEvaluation
    action: ActuationOutcome
