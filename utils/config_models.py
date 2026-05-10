from __future__ import annotations

import re
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError


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


class ActivityMatcherConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["process", "title"]
    match: Literal["exact", "regex", "contains"]
    pattern: str = Field(min_length=1)
    tag: str = Field(min_length=1)
    case_sensitive: bool = False


class _BasePolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    weight: float = Field(1.0, ge=0)


class ActivityPolicyConfig(_BasePolicyConfig):
    smoothing_window: float = Field(60.0, ge=1)
    matchers: list[ActivityMatcherConfig] = Field(default_factory=list)
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
