import json
import logging
import os
import re
from typing import Dict, List, Any, Optional, Union

from pydantic import BaseModel, Field, ConfigDict, ValidationError, field_validator

logger = logging.getLogger("WEScheduler.Config")

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

PLAYLIST_COLOR_PRESETS = {
    "BRIGHT_FLOW": "#F5C518",
    "CASUAL_ANIME": "#5BB8D4",
    "SUNSET_GLOW": "#FF8C00",
    "NIGHT_CHILL": "#7B68EE",
    "NIGHT_FOCUS": "#2E5F8A",
    "RAINY_MOOD": "#4A90D9",
    "WINTER_VIBES": "#ADC8E0",
    "SPRING_BLOOM": "#5CBE5C",
    "SUMMER_GLOW": "#D83820",
    "AUTUMN_DRIFT": "#C07830",
}


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
    lat: Union[str, float] = "0"
    lon: Union[str, float] = "0"
    fetch_interval: float = Field(600.0, ge=60)
    request_timeout: float = Field(10.0, ge=1)
    warmup_timeout: float = Field(3.0, ge=0)


class PoliciesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity: Optional[ActivityPolicyConfig] = None
    time: Optional[TimePolicyConfig] = None
    season: Optional[SeasonPolicyConfig] = None
    weather: Optional[WeatherPolicyConfig] = None


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
    wallpaper_engine_path: str = Field(min_length=1)
    language: Optional[str] = None
    tags: Dict[str, TagSpec] = Field(default_factory=dict)
    playlists: List[PlaylistConfig] = Field(min_length=1)
    policies: PoliciesConfig = Field(default_factory=PoliciesConfig)
    scheduling: SchedulingConfig = Field(default_factory=SchedulingConfig)


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

