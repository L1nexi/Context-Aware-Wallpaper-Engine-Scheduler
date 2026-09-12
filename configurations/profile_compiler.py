from __future__ import annotations

from collections.abc import Mapping

from configurations.profile import Profile, SceneId
from configurations.runtime_models import (
    PLAYLIST_AUTO_COLOR_PALETTE,
    ActivityMatcherConfig,
    ActivityPolicyConfig,
    PlaylistConfig,
    PoliciesConfig,
    SchedulerConfig,
    SchedulingConfig,
    SeasonPolicyConfig,
    TagSpec,
    TimePolicyConfig,
    WeatherPolicyConfig,
)

_SCENE_PRESETS: dict[SceneId, dict[str, float]] = {
    SceneId.DAY_WORK: {"focus": 1.0, "day": 0.9, "dawn": 0.3, "clear": 0.3},
    SceneId.DAY_LEISURE: {"chill": 1.0, "day": 0.9, "clear": 0.3},
    SceneId.NIGHT_WORK: {"focus": 1.0, "night": 0.9, "clear": 0.2},
    SceneId.NIGHT_LEISURE: {"chill": 1.0, "night": 0.9, "clear": 0.2},
    SceneId.SPRING: {"spring": 1.0, "day": 0.5, "clear": 0.3, "chill": 0.2},
    SceneId.SUMMER: {"summer": 1.0, "day": 0.5, "clear": 0.4, "chill": 0.3},
    SceneId.AUTUMN: {"autumn": 1.0, "sunset": 0.5, "day": 0.3, "chill": 0.3, "clear": 0.2},
    SceneId.WINTER: {"winter": 1.0, "sunset": 0.7, "snow": 0.5, "chill": 0.3, "clear": 0.3},
    SceneId.SUNSET: {"sunset": 1.0, "chill": 0.5, "clear": 0.3},
    SceneId.RAIN: {"rain": 1.2, "storm": 0.4, "day": 0.3, "night": 0.3, "chill": 0.3},
}

_TAG_FALLBACKS: dict[str, dict[str, float]] = {
    "focus": {},
    "chill": {},
    "dawn": {"day": 0.7, "chill": 0.3},
    "day": {},
    "sunset": {"chill": 0.3, "night": 0.7},
    "night": {},
    "spring": {"day": 0.5, "chill": 0.5},
    "summer": {"day": 0.7, "clear": 0.3},
    "autumn": {"sunset": 0.6, "chill": 0.4},
    "winter": {"night": 0.5, "chill": 0.5},
    "clear": {},
    "cloudy": {"clear": 0.5, "chill": 0.3},
    "rain": {},
    "storm": {"rain": 1.0},
    "snow": {"winter": 0.6, "rain": 0.6},
    "fog": {"rain": 0.4, "chill": 0.4},
}


_CPU_THRESHOLD_PERCENT: int = 85
_CPU_SAMPLE_WINDOW_SIZE: int = 10


class ProfileCompiler:
    @classmethod
    def compile(
        cls,
        profile: Profile,
        *,
        playlist_item_counts: Mapping[str, int] | None = None,
    ) -> SchedulerConfig:
        """Compile one validated user profile into a complete runtime config."""

        item_counts = playlist_item_counts or {}
        return SchedulerConfig(
            wallpaper_engine_path=profile.wallpaper_engine_path,
            language=profile.language,
            tags={tag: TagSpec(fallback=dict(fallback)) for tag, fallback in _TAG_FALLBACKS.items()},
            playlists=cls._compile_playlists(profile, item_counts),
            policies=cls._compile_policies(profile),
            scheduling=cls._compile_scheduling(profile),
        )

    @staticmethod
    def _compile_playlists(
        profile: Profile,
        item_counts: Mapping[str, int],
    ) -> dict[str, PlaylistConfig]:
        tags_by_playlist: dict[str, dict[str, float]] = {}
        for scene, playlist_name in profile.scenes.items():
            merged_tags = tags_by_playlist.setdefault(playlist_name, {})
            for tag, weight in _SCENE_PRESETS[scene].items():
                merged_tags[tag] = max(merged_tags.get(tag, 0.0), weight)

        playlists: dict[str, PlaylistConfig] = {}
        for color_index, playlist_name in enumerate(sorted(tags_by_playlist, key=lambda name: (name.casefold(), name))):
            playlists[playlist_name] = PlaylistConfig(
                display=playlist_name,
                color=PLAYLIST_AUTO_COLOR_PALETTE[color_index % len(PLAYLIST_AUTO_COLOR_PALETTE)],
                tags=tags_by_playlist[playlist_name],
                item_count=item_counts.get(playlist_name, 0),
            )
        return playlists

    @classmethod
    def _compile_policies(cls, profile: Profile) -> PoliciesConfig:
        location = profile.weather.location
        return PoliciesConfig(
            activity=ActivityPolicyConfig(
                enabled=True,
                weight=1.2,
                smoothing_window=120,
                matchers=cls._compile_activity_matchers(profile),
            ),
            time=TimePolicyConfig(
                enabled=True,
                weight=0.8,
                auto=True,
                day_start_hour=8,
                night_start_hour=20,
            ),
            season=SeasonPolicyConfig(
                enabled=True,
                weight=0.65,
                spring_peak=80,
                summer_peak=172,
                autumn_peak=265,
                winter_peak=355,
            ),
            weather=WeatherPolicyConfig(
                enabled=True,
                weight=1.5,
                api_key=profile.weather.api_key,
                lat=location.latitude,
                lon=location.longitude,
                fetch_interval=600,
                request_timeout=10,
                warmup_timeout=3,
            ),
        )

    @staticmethod
    def _compile_activity_matchers(profile: Profile) -> list[ActivityMatcherConfig]:
        activity = profile.activity
        matcher_specs = (
            (("process", "exact", pattern, "focus") for pattern in activity.work_processes),
            (("process", "exact", pattern, "chill") for pattern in activity.leisure_processes),
            (("title", "contains", pattern, "focus") for pattern in activity.work_title_keywords),
            (("title", "contains", pattern, "chill") for pattern in activity.leisure_title_keywords),
        )
        flattened = [spec for group in matcher_specs for spec in group]
        source_order = {"process": 0, "title": 1}
        tag_order = {"focus": 0, "chill": 1}
        flattened.sort(key=lambda item: (source_order[item[0]], tag_order[item[3]], item[2].casefold(), item[2]))
        return [
            ActivityMatcherConfig(
                source=source,
                match=match,
                pattern=pattern,
                tag=tag,
                case_sensitive=False,
            )
            for source, match, pattern, tag in flattened
        ]

    @staticmethod
    def _compile_scheduling(profile: Profile) -> SchedulingConfig:
        disturbance = profile.disturbance

        return SchedulingConfig(
            startup_delay=disturbance.startup_grace_seconds,
            idle_threshold=disturbance.idle_before_switch_seconds,
            force_after=disturbance.maximum_deferral_minutes * 60,
            cycle_cooldown=disturbance.cycle_interval_minutes * 60,
            cpu_threshold=_CPU_THRESHOLD_PERCENT,
            cpu_sample_window=_CPU_SAMPLE_WINDOW_SIZE,
            pause_on_fullscreen=True,
        )
