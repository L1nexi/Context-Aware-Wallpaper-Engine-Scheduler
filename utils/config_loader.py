import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError

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


def _assign_missing_playlist_colors(playlists: list[Any]) -> list[Any]:
    fallback_index = 0
    palette_size = len(PLAYLIST_AUTO_COLOR_PALETTE)
    normalized_playlists: list[Any] = []

    for playlist in playlists:
        if not isinstance(playlist, dict):
            normalized_playlists.append(playlist)
            continue

        normalized_playlist = dict(playlist)
        if normalized_playlist.get("color") is None:
            normalized_playlist["color"] = PLAYLIST_AUTO_COLOR_PALETTE[
                fallback_index % palette_size
            ]
            fallback_index += 1

        normalized_playlists.append(normalized_playlist)

    return normalized_playlists


# ── Config models ────────────────────────────────────────────────────────────

class TagSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fallback: Dict[str, float] = Field(default_factory=dict)


class PlaylistConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
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
    # Peak day-of-year overrides (Northern Hemisphere defaults)
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
    playlists: List[PlaylistConfig] = Field(default_factory=list)
    policies: PoliciesConfig = Field(default_factory=PoliciesConfig)
    scheduling: SchedulingConfig = Field(default_factory=SchedulingConfig)

    @model_validator(mode="before")
    @classmethod
    def normalize_playlist_colors(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        playlists = normalized.get("playlists")
        if isinstance(playlists, list):
            normalized["playlists"] = _assign_missing_playlist_colors(playlists)
        return normalized


# ── ConfigLoader ─────────────────────────────────────────────────────────────

class ConfigLoader:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config: Optional[AppConfig] = None

    def load(self) -> AppConfig:
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found at: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        try:
            self.config = AppConfig.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

        logger.info(f"Config loaded from: {self.config_path}")
        return self.config

