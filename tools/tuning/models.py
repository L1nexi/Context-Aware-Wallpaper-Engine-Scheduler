from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import product
from types import MappingProxyType

from core.context import Context, WeatherData
from core.diagnostics import ActivityPolicyDetails, ActivityPolicyEvaluation, MatchEvaluation
from core.matcher import Matcher
from core.policies import Policy, SeasonPolicy, TimePolicy, WeatherPolicy
from utils.runtime_config import ActivityPolicyConfig, SchedulerConfig

_EVAL_YEAR = 2025
_EPSILON = 1e-6


@dataclass(frozen=True)
class ActivitySignal:
    direction: Mapping[str, float]
    intensity: float = 1.0
    salience: float = 1.0

    def __post_init__(self) -> None:
        _validate_vector(self.direction, "activity direction")
        _validate_non_negative(self.intensity, "activity intensity")
        _validate_non_negative(self.salience, "activity salience")
        object.__setattr__(self, "direction", MappingProxyType(dict(self.direction)))


@dataclass(frozen=True)
class WeatherInput:
    weather_id: int
    main: str


@dataclass(frozen=True)
class Scenario:
    name: str
    hour: float
    day_of_year: int
    weather: WeatherInput | None = None
    activity: ActivitySignal | None = None
    expected: str | None = None
    category: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("scenario name must not be empty")
        if not 0 <= self.hour < 24:
            raise ValueError("scenario hour must be in [0, 24)")
        if not 1 <= self.day_of_year <= 365:
            raise ValueError("scenario day_of_year must be in [1, 365]")
        category = self.category.strip()
        if not category:
            category = "observed" if self.expected is None else "core"
        object.__setattr__(self, "category", category)


@dataclass(frozen=True)
class MatchProfile:
    name: str
    gamma_playlist: float = 1.0
    gamma_context: float = 1.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("profile name must not be empty")
        if self.gamma_playlist <= 0:
            raise ValueError("gamma_playlist must be positive")
        if self.gamma_context <= 0:
            raise ValueError("gamma_context must be positive")


@dataclass(frozen=True)
class RankingRow:
    scenario: str
    profile: str
    rank: int
    playlist: str
    score: float


@dataclass(frozen=True)
class ScenarioProfileResult:
    scenario: Scenario
    profile: MatchProfile
    match: MatchEvaluation
    rankings: list[RankingRow]

    @property
    def winner(self) -> str | None:
        return self.match.best_playlist

    @property
    def score(self) -> float:
        return self.rankings[0].score if self.rankings else 0.0

    @property
    def gap(self) -> float:
        if not self.rankings:
            return 0.0
        if len(self.rankings) == 1:
            return self.rankings[0].score
        return self.rankings[0].score - self.rankings[1].score

    @property
    def expected_status(self) -> str:
        if self.scenario.expected is None:
            return "observed"
        if self.winner == self.scenario.expected:
            return "pass"
        return "fail"


def focus(intensity: float = 1.0, *, salience: float = 1.0) -> ActivitySignal:
    return ActivitySignal({"focus": 1.0}, intensity=intensity, salience=salience)


def chill(intensity: float = 1.0, *, salience: float = 1.0) -> ActivitySignal:
    return ActivitySignal({"chill": 1.0}, intensity=intensity, salience=salience)


def activity_signal(
    direction: dict[str, float],
    *,
    intensity: float = 1.0,
    salience: float = 1.0,
) -> ActivitySignal:
    return ActivitySignal(direction, intensity=intensity, salience=salience)


def matrix(
    prefix: str,
    *,
    hours: list[float],
    days: list[int],
    weathers: list[str | None] | None = None,
    activities: list[ActivitySignal | None] | None = None,
    category: str = "observed",
    note: str = "matrix trial",
) -> list[Scenario]:
    """Build observed scenarios from a small Cartesian matrix.

    Raises:
        ValueError: If `prefix`, `hours`, or `days` is empty, or if an axis
            value fails the underlying `Scenario` or weather preset validation.
    """
    if not prefix.strip():
        raise ValueError("matrix prefix must not be empty")
    if not hours:
        raise ValueError("matrix hours must not be empty")
    if not days:
        raise ValueError("matrix days must not be empty")

    weather_axis = weathers or [None]
    activity_axis = activities or [None]
    if not weather_axis:
        raise ValueError("matrix weathers must not be empty")
    if not activity_axis:
        raise ValueError("matrix activities must not be empty")

    scenarios: list[Scenario] = []
    for day, hour, activity, weather_name in product(days, hours, activity_axis, weather_axis):
        scenarios.append(
            Scenario(
                " ".join(
                    (
                        prefix,
                        f"doy{day}",
                        f"h{hour:g}",
                        _activity_name(activity),
                        weather_name or "none",
                    )
                ),
                hour=hour,
                day_of_year=day,
                weather=weather(weather_name),
                activity=activity,
                category=category,
                note=note,
            )
        )
    return scenarios


def _activity_name(activity: ActivitySignal | None) -> str:
    if activity is None:
        return "idle"
    tags = "-".join(f"{tag}{activity.direction[tag]:g}" for tag in sorted(activity.direction))
    return f"{tags}-i{activity.intensity:g}"


WEATHER_PRESETS: dict[str, WeatherInput] = {
    "clear": WeatherInput(800, "Clear"),
    "few_clouds": WeatherInput(801, "Clouds"),
    "overcast": WeatherInput(804, "Clouds"),
    "light_drizzle": WeatherInput(300, "Drizzle"),
    "drizzle": WeatherInput(301, "Drizzle"),
    "light_rain": WeatherInput(500, "Rain"),
    "mod_rain": WeatherInput(501, "Rain"),
    "heavy_rain": WeatherInput(502, "Rain"),
    "light_snow": WeatherInput(600, "Snow"),
    "heavy_snow": WeatherInput(602, "Snow"),
    "storm": WeatherInput(211, "Thunderstorm"),
    "storm_rain": WeatherInput(201, "Thunderstorm"),
    "heavy_storm": WeatherInput(212, "Thunderstorm"),
    "fog": WeatherInput(741, "Fog"),
}


def weather(name: str | None) -> WeatherInput | None:
    if name is None or name == "none":
        return None
    try:
        return WEATHER_PRESETS[name]
    except KeyError as exc:
        raise ValueError(f"unknown weather preset: {name}") from exc


class DirectActivityPolicy(Policy):
    config_key = "activity"
    evaluation_cls = ActivityPolicyEvaluation

    def __init__(self, config: ActivityPolicyConfig, signal: ActivitySignal | None):
        super().__init__(config)
        self.signal = signal

    def evaluate(self, context: Context) -> ActivityPolicyEvaluation:
        signal = self.signal
        if signal is None:
            return self._make_evaluation(
                details=ActivityPolicyDetails(ema_active=False),
                raw_direction=None,
                salience=0.0,
                intensity=0.0,
            )

        return self._make_evaluation(
            details=ActivityPolicyDetails(ema_active=signal.intensity > 0),
            raw_direction=dict(signal.direction),
            salience=signal.salience,
            intensity=signal.intensity,
        )


def evaluate_scenario(
    config: SchedulerConfig,
    scenario: Scenario,
    profile: MatchProfile,
) -> ScenarioProfileResult:
    context = build_context(scenario)
    policies: list[Policy] = [
        DirectActivityPolicy(config.policies.activity, scenario.activity),
        TimePolicy(config.policies.time),
        SeasonPolicy(config.policies.season),
        WeatherPolicy(config.policies.weather),
    ]
    match = Matcher(config.playlists, policies, config.tags).evaluate(context)
    playlist_matches = rank_for_profile(config, match.resolved_context_vector, profile)
    match.playlist_matches = playlist_matches
    match.best_playlist = playlist_matches[0][0] if playlist_matches and playlist_matches[0][1] > 0.001 else None
    rankings = [
        RankingRow(
            scenario=scenario.name,
            profile=profile.name,
            rank=index + 1,
            playlist=playlist,
            score=score,
        )
        for index, (playlist, score) in enumerate(playlist_matches)
    ]
    return ScenarioProfileResult(
        scenario=scenario,
        profile=profile,
        match=match,
        rankings=rankings,
    )


def build_context(scenario: Scenario) -> Context:
    date = datetime(_EVAL_YEAR, 1, 1) + timedelta(
        days=scenario.day_of_year - 1,
        minutes=round(scenario.hour * 60),
    )

    weather_data = None
    if scenario.weather is not None:
        weather_data = WeatherData(
            id=scenario.weather.weather_id,
            main=scenario.weather.main,
            fetched_at=0.0,
            stale=False,
        )

    return Context(time=date.timetuple(), weather=weather_data)


def rank_for_profile(
    config: SchedulerConfig,
    resolved_context_vector: dict[str, float],
    profile: MatchProfile,
) -> list[tuple[str, float]]:
    context_dir = _normalize_pow(resolved_context_vector, profile.gamma_context)
    if not context_dir:
        return []

    scores: list[tuple[float, str]] = []
    for playlist_name, playlist in config.playlists.items():
        playlist_dir = _normalize_pow(playlist.tags, profile.gamma_playlist)
        if not playlist_dir:
            continue
        score = _dot(context_dir, playlist_dir)
        scores.append((score, playlist_name))

    scores.sort(reverse=True)
    return [(playlist_name, score) for score, playlist_name in scores]


def _normalize_pow(vector: dict[str, float], gamma: float) -> dict[str, float]:
    powered: dict[str, float] = {}
    for tag, value in vector.items():
        if value <= 0:
            continue
        powered[tag] = value**gamma
    norm = math.sqrt(sum(value * value for value in powered.values()))
    if norm < _EPSILON:
        return {}
    return {tag: value / norm for tag, value in powered.items()}


def _dot(left: dict[str, float], right: dict[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(tag, 0.0) for tag, value in left.items())


def _validate_vector(vector: Mapping[str, float], label: str) -> None:
    if not vector:
        raise ValueError(f"{label} must not be empty")
    for tag, value in vector.items():
        if not tag:
            raise ValueError(f"{label} contains an empty tag")
        _validate_non_negative(value, f"{label} weight for {tag}")


def _validate_non_negative(value: float, label: str) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{label} must be a finite non-negative number")
