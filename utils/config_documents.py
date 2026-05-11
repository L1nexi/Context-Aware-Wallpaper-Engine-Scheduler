from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic_core import PydanticCustomError

from core.policies import get_policy_fixed_output_tags
from utils.we_path import resolve_wallpaper_engine_path
from utils.config_errors import ConfigIssue, ConfigLoadError
from utils.runtime_config import (
    ActivityMatcherConfig,
    ActivityPolicyConfig,
    HEX_COLOR_RE,
    PLAYLIST_AUTO_COLOR_PALETTE,
    PlaylistConfig,
    PoliciesConfig,
    SchedulerConfig,
    SchedulingConfig,
    SeasonPolicyConfig,
    TagSpec,
    TimePolicyConfig,
    WeatherPolicyConfig,
)

logger = logging.getLogger("WEScheduler.ConfigDocuments")

HEX_COLOR_WITHOUT_HASH_RE = re.compile(r"^[0-9A-Fa-f]{6}$")

PLAYLIST_NAMED_COLORS = {
    "blue": "#2563EB",
    "cyan": "#0891B2",
    "emerald": "#059669",
    "green": "#16A34A",
    "lime": "#65A30D",
    "amber": "#CA8A04",
    "orange": "#D97706",
    "red": "#DC2626",
    "rose": "#E11D48",
    "fuchsia": "#C026D3",
    "violet": "#7C3AED",
    "slate": "#475569",
    "gray": "#4B5563",
}

def _normalize_playlist_color(value: str) -> str | None:
    stripped = value.strip()
    if not stripped:
        return None

    named = PLAYLIST_NAMED_COLORS.get(stripped.lower())
    if named:
        return named

    if HEX_COLOR_RE.fullmatch(stripped):
        return stripped.upper()

    if HEX_COLOR_WITHOUT_HASH_RE.fullmatch(stripped):
        return f"#{stripped.upper()}"

    return None


def _validate_coordinate_input(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, str):
        raise PydanticCustomError("float_type", "Input should be a valid number")
    return value


class SchedulerRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wallpaper_engine_path: str | None = None
    language: str | None = None


class SchedulerFileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int
    runtime: SchedulerRuntimeConfig = Field(default_factory=SchedulerRuntimeConfig)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        if value != 2:
            raise ValueError("config version must be 2")
        return value


class PlaylistFileEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display: str = ""
    color: str | None = None
    tags: Dict[str, float] = Field(default_factory=dict)


class PlaylistsFileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    playlists: Dict[str, PlaylistFileEntry] = Field(default_factory=dict)

    @field_validator("playlists")
    @classmethod
    def validate_playlist_keys(cls, value: Dict[str, PlaylistFileEntry]) -> Dict[str, PlaylistFileEntry]:
        for playlist_name in value:
            if not playlist_name.strip():
                raise ValueError("playlist name must not be empty")
        return value

    def collect_issues(self) -> list[ConfigIssue]:
        issues: list[ConfigIssue] = []
        for playlist_name, playlist in self.playlists.items():
            if playlist.color is not None and _normalize_playlist_color(playlist.color) is None:
                issues.append(
                    ConfigIssue(
                        source_file="playlists.yaml",
                        field_path=("playlists", playlist_name, "color"),
                        message="color must be a named color, 6-digit hex, or #RRGGBB",
                        code="invalid_playlist_color",
                    )
                )
        return issues

    def to_runtime_config(self) -> dict[str, PlaylistConfig]:
        runtime_playlists: dict[str, PlaylistConfig] = {}
        fallback_index = 0
        palette_size = len(PLAYLIST_AUTO_COLOR_PALETTE)

        for playlist_name, playlist in self.playlists.items():
            if playlist.color is None:
                color = PLAYLIST_AUTO_COLOR_PALETTE[fallback_index % palette_size]
                fallback_index += 1
            else:
                color = _normalize_playlist_color(playlist.color)

            runtime_playlists[playlist_name] = PlaylistConfig(
                display=playlist.display,
                color=color,
                tags=dict(playlist.tags),
            )

        return runtime_playlists


class TagFileEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fallback: Dict[str, float] = Field(default_factory=dict)


class TagsFileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tags: Dict[str, TagFileEntry] = Field(default_factory=dict)

    def to_runtime_config(self) -> dict[str, TagSpec]:
        return {
            tag_name: TagSpec(fallback=dict(tag_spec.fallback))
            for tag_name, tag_spec in self.tags.items()
        }


class _BasePolicyFileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    weight: float = Field(1.0, ge=0)


class ActivityMatcherFileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["process", "title"]
    match: Literal["exact", "regex", "contains"]
    pattern: str = Field(min_length=1)
    tag: str = Field(min_length=1)
    case_sensitive: bool = False

    def to_runtime_config(self) -> ActivityMatcherConfig:
        return ActivityMatcherConfig(
            source=self.source,
            match=self.match,
            pattern=self.pattern,
            tag=self.tag,
            case_sensitive=self.case_sensitive,
        )


class ActivityPolicyFileConfig(_BasePolicyFileConfig):
    smoothing_window: float = Field(60.0, ge=1)
    process: Dict[str, str] = Field(default_factory=dict)
    title: Dict[str, str] = Field(default_factory=dict)
    matchers: list[ActivityMatcherFileConfig] = Field(default_factory=list)

    def to_runtime_config(self) -> ActivityPolicyConfig:
        runtime_matchers = [
            {
                "source": "process",
                "match": "exact",
                "pattern": pattern,
                "tag": tag,
                "case_sensitive": False,
            }
            for pattern, tag in self.process.items()
        ]
        runtime_matchers.extend(
            {
                "source": "title",
                "match": "contains",
                "pattern": pattern,
                "tag": tag,
                "case_sensitive": False,
            }
            for pattern, tag in self.title.items()
        )
        runtime_matchers.extend(matcher.model_dump(mode="python") for matcher in self.matchers)

        return ActivityPolicyConfig(
            enabled=self.enabled,
            weight=self.weight,
            smoothing_window=self.smoothing_window,
            matchers=runtime_matchers,
        )


class TimePolicyFileConfig(_BasePolicyFileConfig):
    auto: bool = True
    day_start_hour: float = Field(8.0, ge=0, lt=24)
    night_start_hour: float = Field(20.0, ge=0, lt=24)

    def to_runtime_config(self) -> TimePolicyConfig:
        return TimePolicyConfig(
            enabled=self.enabled,
            weight=self.weight,
            auto=self.auto,
            day_start_hour=self.day_start_hour,
            night_start_hour=self.night_start_hour,
        )


class SeasonPolicyFileConfig(_BasePolicyFileConfig):
    spring_peak: int = 80
    summer_peak: int = 172
    autumn_peak: int = 265
    winter_peak: int = 355

    def to_runtime_config(self) -> SeasonPolicyConfig:
        return SeasonPolicyConfig(
            enabled=self.enabled,
            weight=self.weight,
            spring_peak=self.spring_peak,
            summer_peak=self.summer_peak,
            autumn_peak=self.autumn_peak,
            winter_peak=self.winter_peak,
        )


class WeatherPolicyFileConfig(_BasePolicyFileConfig):
    api_key: str = ""
    lat: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    lon: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    fetch_interval: float = Field(600.0, ge=60)
    request_timeout: float = Field(10.0, ge=1)
    warmup_timeout: float = Field(3.0, ge=0)

    @field_validator("lat", "lon", mode="before")
    @classmethod
    def validate_coordinate_input(cls, value: Any) -> Any:
        return _validate_coordinate_input(value)

    def to_runtime_config(self) -> WeatherPolicyConfig:
        return WeatherPolicyConfig(
            enabled=self.enabled,
            weight=self.weight,
            api_key=self.api_key,
            lat=self.lat,
            lon=self.lon,
            fetch_interval=self.fetch_interval,
            request_timeout=self.request_timeout,
            warmup_timeout=self.warmup_timeout,
        )


class ActivityFileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity: ActivityPolicyFileConfig = Field(default_factory=ActivityPolicyFileConfig)


class ContextFileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    time: TimePolicyFileConfig = Field(default_factory=TimePolicyFileConfig)
    season: SeasonPolicyFileConfig = Field(default_factory=SeasonPolicyFileConfig)
    weather: WeatherPolicyFileConfig = Field(default_factory=WeatherPolicyFileConfig)


class SchedulingFileEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    startup_delay: float = Field(30.0, ge=0)
    idle_threshold: float = Field(60.0, ge=0)
    switch_cooldown: float = Field(1800.0, ge=0)
    force_after: float = Field(14400.0, ge=0)
    cycle_cooldown: float = Field(600.0, ge=0)
    cpu_threshold: float = Field(85.0, ge=0, le=100)
    cpu_sample_window: int = Field(10, ge=1)
    pause_on_fullscreen: bool = True

    def to_runtime_config(self) -> SchedulingConfig:
        return SchedulingConfig(
            startup_delay=self.startup_delay,
            idle_threshold=self.idle_threshold,
            switch_cooldown=self.switch_cooldown,
            force_after=self.force_after,
            cycle_cooldown=self.cycle_cooldown,
            cpu_threshold=self.cpu_threshold,
            cpu_sample_window=self.cpu_sample_window,
            pause_on_fullscreen=self.pause_on_fullscreen,
        )


class SchedulingFileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scheduling: SchedulingFileEntry = Field(default_factory=SchedulingFileEntry)


def _validate_declared_tag(
    tag: str,
    declared_tags: set[str],
    source_file: str,
    field_path: tuple[str | int, ...],
    issues: list[ConfigIssue],
) -> None:
    if tag not in declared_tags:
        issues.append(
            ConfigIssue(
                source_file=source_file,
                field_path=field_path,
                message=f"tag '{tag}' must be declared in tags.yaml",
                code="unknown_tag",
            )
        )


def _runtime_issue_for_loc(loc: tuple[str | int, ...], message: str, code: str) -> ConfigIssue:
    if not loc:
        return ConfigIssue("scheduler.yaml", (), message, code)

    root = loc[0]
    if root == "wallpaper_engine_path":
        return ConfigIssue("scheduler.yaml", ("runtime", "wallpaper_engine_path"), message, code)
    if root == "language":
        return ConfigIssue("scheduler.yaml", ("runtime", "language"), message, code)
    if root == "tags":
        return ConfigIssue("tags.yaml", ("tags",) + loc[1:], message, code)
    if root == "playlists":
        return ConfigIssue("playlists.yaml", ("playlists",) + loc[1:], message, code)
    if root == "policies" and len(loc) >= 2:
        policy_name = loc[1]
        if policy_name == "activity":
            return ConfigIssue("activity.yaml", ("activity",) + loc[2:], message, code)
        return ConfigIssue("context.yaml", (str(policy_name),) + loc[2:], message, code)
    if root == "scheduling":
        return ConfigIssue("scheduling.yaml", ("scheduling",) + loc[1:], message, code)
    return ConfigIssue("scheduler.yaml", loc, message, code)


@dataclass(frozen=True)
class ConfigFiles:
    scheduler: SchedulerFileConfig
    playlists: PlaylistsFileConfig
    tags: TagsFileConfig
    activity: ActivityFileConfig
    context: ContextFileConfig
    scheduling: SchedulingFileConfig

    def collect_issues(self) -> list[ConfigIssue]:
        issues: list[ConfigIssue] = []
        issues.extend(self.playlists.collect_issues())
        issues.extend(self._collect_runtime_we_path_issues())
        issues.extend(self._collect_tag_reference_issues())
        return issues

    def _collect_runtime_we_path_issues(self) -> list[ConfigIssue]:
        configured_path = self.scheduler.runtime.wallpaper_engine_path

        resolved_path = resolve_wallpaper_engine_path(configured_path)
        if resolved_path is not None:
            if configured_path != resolved_path:
                logger.info("Auto-detected Wallpaper Engine at: %s", resolved_path)
            return []

        if configured_path:
            return [
                ConfigIssue(
                    source_file="scheduler.yaml",
                    field_path=("runtime", "wallpaper_engine_path"),
                    message="wallpaper_engine_path must point to an existing executable file",
                    code="invalid_wallpaper_engine_path",
                )]
        else:
            return [
                ConfigIssue(
                    source_file="scheduler.yaml",
                    field_path=("runtime", "wallpaper_engine_path"),
                    message=(
                        "Wallpaper Engine executable could not be auto-detected on this machine; "
                        "set runtime.wallpaper_engine_path explicitly"
                    ),
                    code="wallpaper_engine_path_unresolved",
                )]

    def _collect_tag_reference_issues(self) -> list[ConfigIssue]:
        issues: list[ConfigIssue] = []
        declared_tags = set(self.tags.tags.keys())

        for tag_name, tag_spec in self.tags.tags.items():
            for fallback_tag in tag_spec.fallback:
                _validate_declared_tag(
                    fallback_tag,
                    declared_tags,
                    "tags.yaml",
                    ("tags", tag_name, "fallback", fallback_tag),
                    issues,
                )

        for playlist_name, playlist in self.playlists.playlists.items():
            for tag_name in playlist.tags:
                _validate_declared_tag(
                    tag_name,
                    declared_tags,
                    "playlists.yaml",
                    ("playlists", playlist_name, "tags", tag_name),
                    issues,
                )

        for rule_name, tag_name in self.activity.activity.process.items():
            _validate_declared_tag(
                tag_name,
                declared_tags,
                "activity.yaml",
                ("activity", "process", rule_name),
                issues,
            )

        for rule_name, tag_name in self.activity.activity.title.items():
            _validate_declared_tag(
                tag_name,
                declared_tags,
                "activity.yaml",
                ("activity", "title", rule_name),
                issues,
            )

        for index, matcher in enumerate(self.activity.activity.matchers):
            _validate_declared_tag(
                matcher.tag,
                declared_tags,
                "activity.yaml",
                ("activity", "matchers", index, "tag"),
                issues,
            )

        fixed_output_tags = get_policy_fixed_output_tags()
        for policy_name, tags in fixed_output_tags.items():
            if policy_name == "activity":
                policy_config = self.activity.activity
                source_file = "activity.yaml"
            else:
                policy_config = getattr(self.context, policy_name, None)
                source_file = "context.yaml"
            if policy_config is None or not policy_config.enabled:
                continue
            for tag_name in tags:
                _validate_declared_tag(tag_name, declared_tags, source_file, (policy_name, tag_name), issues)

        return issues

    def to_verified_scheduler_config(self) -> SchedulerConfig:
        issues = self.collect_issues()
        if issues:
            raise ConfigLoadError(issues)

        try:
            return SchedulerConfig.model_validate(
                {
                    "wallpaper_engine_path": resolve_wallpaper_engine_path(self.scheduler.runtime.wallpaper_engine_path),
                    "language": self.scheduler.runtime.language,
                    "tags": self.tags.to_runtime_config(),
                    "playlists": self.playlists.to_runtime_config(),
                    "policies": PoliciesConfig.model_validate(
                        {
                            "activity": self.activity.activity.to_runtime_config(),
                            "time": self.context.time.to_runtime_config(),
                            "season": self.context.season.to_runtime_config(),
                            "weather": self.context.weather.to_runtime_config(),
                        }
                    ),
                    "scheduling": self.scheduling.scheduling.to_runtime_config(),
                }
            )
        except ValidationError as exc:
            issues = [
                _runtime_issue_for_loc(
                    tuple(err.get("loc", ())),
                    err["msg"],
                    err.get("type", "validation_error"),
                )
                for err in exc.errors()
            ]
            raise ConfigLoadError(issues) from exc
