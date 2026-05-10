from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode
from yaml.tokens import AliasToken, AnchorToken

logger = logging.getLogger("WEScheduler.Config")

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

PLAYLIST_AUTO_COLOR_PALETTE = (
    "#2563EB",  # blue
    "#0891B2",  # cyan
    "#059669",  # emerald
    "#16A34A",  # green
    "#65A30D",  # lime
    "#CA8A04",  # amber
    "#D97706",  # orange
    "#EA580C",  # deep orange
    "#DC2626",  # red
    "#E11D48",  # rose
    "#C026D3",  # fuchsia
    "#7C3AED",  # violet
)

CONFIG_FILE_NAMES = (
    "scheduler.yaml",
    "playlists.yaml",
    "tags.yaml",
    "activity.yaml",
    "context.yaml",
    "scheduling.yaml",
)

POLICY_FIXED_TAGS = {
    "time": {"dawn", "day", "sunset", "night"},
    "season": {"spring", "summer", "autumn", "winter"},
    "weather": {"clear", "cloudy", "rain", "storm", "snow", "fog"},
}


def _assign_missing_playlist_colors(playlists: dict[str, Any]) -> dict[str, Any]:
    fallback_index = 0
    palette_size = len(PLAYLIST_AUTO_COLOR_PALETTE)
    normalized_playlists: dict[str, Any] = {}

    for playlist_name, playlist in playlists.items():
        if not isinstance(playlist, dict):
            normalized_playlists[playlist_name] = playlist
            continue

        normalized_playlist = dict(playlist)
        if normalized_playlist.get("color") is None:
            normalized_playlist["color"] = PLAYLIST_AUTO_COLOR_PALETTE[
                fallback_index % palette_size
            ]
            fallback_index += 1

        normalized_playlists[playlist_name] = normalized_playlist

    return normalized_playlists


def _format_field_path(path: tuple[str | int, ...]) -> str:
    if not path:
        return ""

    rendered: list[str] = []
    for part in path:
        if isinstance(part, int):
            if rendered:
                rendered[-1] = f"{rendered[-1]}[{part}]"
            else:
                rendered.append(f"[{part}]")
            continue

        if not rendered:
            rendered.append(part)
            continue

        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part):
            rendered.append(part)
        else:
            rendered[-1] = f"{rendered[-1]}['{part}']"
    return ".".join(rendered)


@dataclass(frozen=True)
class ConfigIssue:
    source_file: str
    field_path: tuple[str | int, ...]
    message: str
    code: str = "config_error"

    def render(self) -> str:
        field_path = _format_field_path(self.field_path)
        if field_path:
            return f"{self.source_file} > {field_path}: {self.message}"
        return f"{self.source_file}: {self.message}"


class ConfigLoadError(ValueError):
    def __init__(self, issues: list[ConfigIssue]):
        self.issues = issues
        super().__init__(self.__str__())

    def __str__(self) -> str:
        return "\n".join(issue.render() for issue in self.issues)


def _raise_config_error(source_file: str, message: str, field_path: tuple[str | int, ...] = ()) -> None:
    raise ConfigLoadError([ConfigIssue(source_file=source_file, field_path=field_path, message=message)])


# ── Runtime config models ───────────────────────────────────────────────────

class TagSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fallback: Dict[str, float] = Field(default_factory=dict)


class PlaylistConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display: str = ""
    color: str
    tags: Dict[str, float] = Field(min_length=1)

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str) -> str:
        if not HEX_COLOR_RE.fullmatch(value):
            raise ValueError("color must be a 6-digit hex string like #RRGGBB")
        return value


class _BasePolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    weight_scale: float = Field(1.0, ge=0)


class ActivityPolicyConfig(_BasePolicyConfig):
    smoothing_window: float = Field(60.0, ge=1)
    process_rules: Dict[str, str] = Field(default_factory=dict)
    title_rules: Dict[str, str] = Field(default_factory=dict)


class TimePolicyConfig(_BasePolicyConfig):
    auto: bool = True
    day_start_hour: float = Field(8.0, ge=0, lt=24)
    night_start_hour: float = Field(20.0, ge=0, lt=24)


class SeasonPolicyConfig(_BasePolicyConfig):
    spring_peak: int = 80
    summer_peak: int = 172
    autumn_peak: int = 265
    winter_peak: int = 355


class WeatherPolicyConfig(_BasePolicyConfig):
    api_key: str = ""
    lat: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    lon: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    fetch_interval: float = Field(600.0, ge=60)
    request_timeout: float = Field(10.0, ge=1)
    warmup_timeout: float = Field(3.0, ge=0)

    @field_validator("lat", "lon", mode="before")
    @classmethod
    def validate_coordinate_input(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, bool) or isinstance(value, str):
            raise PydanticCustomError("float_type", "Input should be a valid number")
        return value


class PoliciesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity: ActivityPolicyConfig = Field(default_factory=ActivityPolicyConfig)
    time: TimePolicyConfig = Field(default_factory=TimePolicyConfig)
    season: SeasonPolicyConfig = Field(default_factory=SeasonPolicyConfig)
    weather: WeatherPolicyConfig = Field(default_factory=WeatherPolicyConfig)


class SchedulingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    startup_delay: float = Field(30.0, ge=0)
    idle_threshold: float = Field(60.0, ge=0)
    switch_cooldown: float = Field(1800.0, ge=0)
    force_after: float = Field(14400.0, ge=0)
    cycle_cooldown: float = Field(600.0, ge=0)
    cpu_threshold: float = Field(85.0, ge=0, le=100)
    cpu_sample_window: int = Field(10, ge=1)
    pause_on_fullscreen: bool = True


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wallpaper_engine_path: str = ""
    language: Optional[str] = None
    tags: Dict[str, TagSpec] = Field(default_factory=dict)
    playlists: Dict[str, PlaylistConfig] = Field(default_factory=dict)
    policies: PoliciesConfig = Field(default_factory=PoliciesConfig)
    scheduling: SchedulingConfig = Field(default_factory=SchedulingConfig)

    @model_validator(mode="before")
    @classmethod
    def normalize_playlist_colors(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        playlists = normalized.get("playlists")
        if isinstance(playlists, dict):
            normalized["playlists"] = _assign_missing_playlist_colors(playlists)
        return normalized


# ── YAML file models ────────────────────────────────────────────────────────

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
    tags: Dict[str, float] = Field(min_length=1)

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not HEX_COLOR_RE.fullmatch(value):
            raise ValueError("color must be a 6-digit hex string like #RRGGBB")
        return value


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


class TagsFileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tags: Dict[str, TagSpec] = Field(default_factory=dict)


class _BasePolicyFileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    weight: float = Field(1.0, ge=0)


class ActivityPolicyFileConfig(_BasePolicyFileConfig):
    smoothing_window: float = Field(60.0, ge=1)
    process_rules: Dict[str, str] = Field(default_factory=dict)
    title_rules: Dict[str, str] = Field(default_factory=dict)


class TimePolicyFileConfig(_BasePolicyFileConfig):
    auto: bool = True
    day_start_hour: float = Field(8.0, ge=0, lt=24)
    night_start_hour: float = Field(20.0, ge=0, lt=24)


class SeasonPolicyFileConfig(_BasePolicyFileConfig):
    spring_peak: int = 80
    summer_peak: int = 172
    autumn_peak: int = 265
    winter_peak: int = 355


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
        if value is None:
            return None
        if isinstance(value, bool) or isinstance(value, str):
            raise PydanticCustomError("float_type", "Input should be a valid number")
        return value


class ActivityFileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity: ActivityPolicyFileConfig = Field(default_factory=ActivityPolicyFileConfig)


class ContextFileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    time: TimePolicyFileConfig = Field(default_factory=TimePolicyFileConfig)
    season: SeasonPolicyFileConfig = Field(default_factory=SeasonPolicyFileConfig)
    weather: WeatherPolicyFileConfig = Field(default_factory=WeatherPolicyFileConfig)


class SchedulingFileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scheduling: SchedulingConfig = Field(default_factory=SchedulingConfig)


def _node_child_path(path: tuple[str | int, ...], key_node: Node) -> tuple[str | int, ...]:
    if isinstance(key_node, ScalarNode):
        return path + (str(key_node.value),)
    return path + ("<key>",)


def _reject_merge_keys(node: Node | None, source_file: str, path: tuple[str | int, ...] = ()) -> None:
    if node is None:
        return
    if isinstance(node, MappingNode):
        for key_node, value_node in node.value:
            if isinstance(key_node, ScalarNode) and key_node.tag == "tag:yaml.org,2002:merge":
                _raise_config_error(
                    source_file,
                    "YAML merge keys are not supported",
                    path + (str(key_node.value),),
                )
            child_path = _node_child_path(path, key_node)
            _reject_merge_keys(value_node, source_file, child_path)
        return
    if isinstance(node, SequenceNode):
        for index, child in enumerate(node.value):
            _reject_merge_keys(child, source_file, path + (index,))


def _load_yaml_mapping(path: str) -> dict[str, Any]:
    source_file = os.path.basename(path)

    if not os.path.exists(path):
        _raise_config_error(source_file, "missing required file")

    with open(path, "r", encoding="utf-8") as file:
        text = file.read()

    try:
        for token in yaml.scan(text):
            if isinstance(token, AnchorToken):
                _raise_config_error(source_file, "YAML anchors are not supported")
            if isinstance(token, AliasToken):
                _raise_config_error(source_file, "YAML aliases are not supported")
    except yaml.YAMLError as exc:
        _raise_config_error(source_file, f"invalid YAML: {exc}")

    try:
        node = yaml.compose(text)
        _reject_merge_keys(node, source_file)
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        _raise_config_error(source_file, f"invalid YAML: {exc}")

    if data is None:
        data = {}

    if not isinstance(data, dict):
        _raise_config_error(source_file, "top-level YAML document must be a mapping")

    return data


def _model_validate_document(model: type[BaseModel], data: dict[str, Any], source_file: str) -> BaseModel:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        issues = [
            ConfigIssue(
                source_file=source_file,
                field_path=tuple(err.get("loc", ())),
                message=err["msg"],
                code=err.get("type", "validation_error"),
            )
            for err in exc.errors()
        ]
        raise ConfigLoadError(issues) from exc


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


def _validate_plain_tag(tag: str, source_file: str, field_path: tuple[str | int, ...], issues: list[ConfigIssue]) -> None:
    if tag.startswith("#"):
        issues.append(
            ConfigIssue(
                source_file=source_file,
                field_path=field_path,
                message="tag ids must not use a '#' prefix",
                code="tag_prefix_forbidden",
            )
        )


def _validate_declared_tag(
    tag: str,
    declared_tags: set[str],
    source_file: str,
    field_path: tuple[str | int, ...],
    issues: list[ConfigIssue],
) -> None:
    _validate_plain_tag(tag, source_file, field_path, issues)
    if tag not in declared_tags:
        issues.append(
            ConfigIssue(
                source_file=source_file,
                field_path=field_path,
                message=f"tag '{tag}' must be declared in tags.yaml",
                code="unknown_tag",
            )
        )


def _validate_tag_references(
    tags_file: TagsFileConfig,
    playlists_file: PlaylistsFileConfig,
    activity_file: ActivityFileConfig,
    context_file: ContextFileConfig,
) -> None:
    issues: list[ConfigIssue] = []
    declared_tags = set(tags_file.tags.keys())

    for tag_name, tag_spec in tags_file.tags.items():
        _validate_plain_tag(tag_name, "tags.yaml", ("tags", tag_name), issues)
        for fallback_tag in tag_spec.fallback:
            _validate_declared_tag(
                fallback_tag,
                declared_tags,
                "tags.yaml",
                ("tags", tag_name, "fallback", fallback_tag),
                issues,
            )

    for playlist_name, playlist in playlists_file.playlists.items():
        for tag_name in playlist.tags:
            _validate_declared_tag(
                tag_name,
                declared_tags,
                "playlists.yaml",
                ("playlists", playlist_name, "tags", tag_name),
                issues,
            )

    for rule_name, tag_name in activity_file.activity.process_rules.items():
        _validate_declared_tag(
            tag_name,
            declared_tags,
            "activity.yaml",
            ("activity", "process_rules", rule_name),
            issues,
        )

    for rule_name, tag_name in activity_file.activity.title_rules.items():
        _validate_declared_tag(
            tag_name,
            declared_tags,
            "activity.yaml",
            ("activity", "title_rules", rule_name),
            issues,
        )

    if context_file.time.enabled:
        for tag_name in sorted(POLICY_FIXED_TAGS["time"]):
            _validate_declared_tag(tag_name, declared_tags, "context.yaml", ("time", tag_name), issues)
    if context_file.season.enabled:
        for tag_name in sorted(POLICY_FIXED_TAGS["season"]):
            _validate_declared_tag(tag_name, declared_tags, "context.yaml", ("season", tag_name), issues)
    if context_file.weather.enabled:
        for tag_name in sorted(POLICY_FIXED_TAGS["weather"]):
            _validate_declared_tag(tag_name, declared_tags, "context.yaml", ("weather", tag_name), issues)

    if issues:
        raise ConfigLoadError(issues)


def _activity_runtime_dict(config: ActivityPolicyFileConfig) -> dict[str, Any]:
    return {
        "enabled": config.enabled,
        "weight_scale": config.weight,
        "smoothing_window": config.smoothing_window,
        "process_rules": dict(config.process_rules),
        "title_rules": dict(config.title_rules),
    }


def _time_runtime_dict(config: TimePolicyFileConfig) -> dict[str, Any]:
    return {
        "enabled": config.enabled,
        "weight_scale": config.weight,
        "auto": config.auto,
        "day_start_hour": config.day_start_hour,
        "night_start_hour": config.night_start_hour,
    }


def _season_runtime_dict(config: SeasonPolicyFileConfig) -> dict[str, Any]:
    return {
        "enabled": config.enabled,
        "weight_scale": config.weight,
        "spring_peak": config.spring_peak,
        "summer_peak": config.summer_peak,
        "autumn_peak": config.autumn_peak,
        "winter_peak": config.winter_peak,
    }


def _weather_runtime_dict(config: WeatherPolicyFileConfig) -> dict[str, Any]:
    return {
        "enabled": config.enabled,
        "weight_scale": config.weight,
        "api_key": config.api_key,
        "lat": config.lat,
        "lon": config.lon,
        "fetch_interval": config.fetch_interval,
        "request_timeout": config.request_timeout,
        "warmup_timeout": config.warmup_timeout,
    }


class ConfigLoader:
    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.config: Optional[AppConfig] = None

    def _path_for(self, file_name: str) -> str:
        return os.path.join(self.config_dir, file_name)

    def required_paths(self) -> dict[str, str]:
        return {file_name: self._path_for(file_name) for file_name in CONFIG_FILE_NAMES}

    def fingerprint(self) -> tuple[tuple[str, bool, int], ...]:
        fingerprint: list[tuple[str, bool, int]] = []
        for file_name, file_path in self.required_paths().items():
            try:
                stat = os.stat(file_path)
            except FileNotFoundError:
                fingerprint.append((file_name, False, 0))
            else:
                fingerprint.append((file_name, True, stat.st_mtime_ns))
        return tuple(fingerprint)

    @classmethod
    def load_runtime_settings(cls, config_dir: str) -> SchedulerRuntimeConfig:
        loader = cls(config_dir)
        scheduler_path = loader._path_for("scheduler.yaml")
        scheduler_data = _load_yaml_mapping(scheduler_path)
        scheduler_file = _model_validate_document(
            SchedulerFileConfig,
            scheduler_data,
            "scheduler.yaml",
        )
        return scheduler_file.runtime

    def load(self) -> AppConfig:
        if not os.path.isdir(self.config_dir):
            raise FileNotFoundError(f"Config directory not found at: {self.config_dir}")

        scheduler_file = _model_validate_document(
            SchedulerFileConfig,
            _load_yaml_mapping(self._path_for("scheduler.yaml")),
            "scheduler.yaml",
        )
        playlists_file = _model_validate_document(
            PlaylistsFileConfig,
            _load_yaml_mapping(self._path_for("playlists.yaml")),
            "playlists.yaml",
        )
        tags_file = _model_validate_document(
            TagsFileConfig,
            _load_yaml_mapping(self._path_for("tags.yaml")),
            "tags.yaml",
        )
        activity_file = _model_validate_document(
            ActivityFileConfig,
            _load_yaml_mapping(self._path_for("activity.yaml")),
            "activity.yaml",
        )
        context_file = _model_validate_document(
            ContextFileConfig,
            _load_yaml_mapping(self._path_for("context.yaml")),
            "context.yaml",
        )
        scheduling_file = _model_validate_document(
            SchedulingFileConfig,
            _load_yaml_mapping(self._path_for("scheduling.yaml")),
            "scheduling.yaml",
        )

        _validate_tag_references(
            tags_file=tags_file,
            playlists_file=playlists_file,
            activity_file=activity_file,
            context_file=context_file,
        )

        raw_runtime = {
            "wallpaper_engine_path": scheduler_file.runtime.wallpaper_engine_path or "",
            "language": scheduler_file.runtime.language,
            "tags": {
                tag_name: tag_spec.model_dump(mode="python")
                for tag_name, tag_spec in tags_file.tags.items()
            },
            "playlists": {
                playlist_name: playlist.model_dump(mode="python")
                for playlist_name, playlist in playlists_file.playlists.items()
            },
            "policies": {
                "activity": _activity_runtime_dict(activity_file.activity),
                "time": _time_runtime_dict(context_file.time),
                "season": _season_runtime_dict(context_file.season),
                "weather": _weather_runtime_dict(context_file.weather),
            },
            "scheduling": scheduling_file.scheduling.model_dump(mode="python"),
        }

        try:
            self.config = AppConfig.model_validate(raw_runtime)
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

        logger.info("Config loaded from directory: %s", self.config_dir)
        return self.config
