import json
import logging
import os
from typing import Dict, List, Any, Optional, Union

from pydantic import BaseModel, Field, ConfigDict, ValidationError

logger = logging.getLogger("WEScheduler.Config")


# ── Config models ────────────────────────────────────────────────────────────

class PlaylistConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    tags: Dict[str, float] = Field(min_length=1)


class _BasePolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    weight_scale: float = Field(1.0, ge=0)


class ActivityPolicyConfig(_BasePolicyConfig):
    smoothing_window: float = Field(60.0, ge=1)
    rules: Dict[str, str] = Field(default_factory=dict)
    title_rules: Dict[str, str] = Field(default_factory=dict)


class TimePolicyConfig(_BasePolicyConfig):
    auto: bool = True
    default_day_start: float = Field(8.0, ge=0, lt=24)
    default_night_start: float = Field(20.0, ge=0, lt=24)


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
    interval: float = Field(600.0, ge=60)
    request_timeout: float = Field(10.0, ge=1)
    warmup_timeout: float = Field(3.0, ge=0)


class PoliciesConfig(BaseModel):
    # extra='allow' so that unknown / experimental policy names are passed
    # through as-is rather than being rejected; they are silently ignored
    # at runtime since they're absent from _POLICY_REGISTRY.
    model_config = ConfigDict(extra="allow")
    activity: Optional[ActivityPolicyConfig] = None
    time: Optional[TimePolicyConfig] = None
    season: Optional[SeasonPolicyConfig] = None
    weather: Optional[WeatherPolicyConfig] = None


class DisturbanceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    startup_delay: float = Field(30.0, ge=0)
    idle_threshold: float = Field(60.0, ge=0)
    min_interval: float = Field(1800.0, ge=0)
    force_interval: float = Field(14400.0, ge=0)
    wallpaper_interval: float = Field(600.0, ge=0)
    cpu_threshold: float = Field(85.0, ge=0, le=100)
    cpu_window: int = Field(10, ge=1)
    fullscreen_defer: bool = True


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    we_path: str = Field(min_length=1)
    language: Optional[str] = None
    playlists: List[PlaylistConfig] = Field(min_length=1)
    policies: PoliciesConfig = Field(default_factory=PoliciesConfig)
    disturbance: DisturbanceConfig = Field(default_factory=DisturbanceConfig)


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

