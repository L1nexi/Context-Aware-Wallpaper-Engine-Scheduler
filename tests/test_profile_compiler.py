from __future__ import annotations

import pytest
from pydantic import ValidationError

from configurations.profile import (
    ActivityProfile,
    Profile,
    SceneId,
    WeatherLocationProfile,
    WeatherProfile,
)
from configurations.profile_compiler import ProfileCompiler

EXPECTED_SCENE_TAGS = {
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


def _profile(**overrides) -> Profile:
    values = {
        "wallpaper_engine_path": r"C:\Wallpaper Engine\wallpaper64.exe",
        "language": "zh",
        "weather": WeatherProfile(
            api_key="test-key",
            location=WeatherLocationProfile(
                name="上海",
                latitude=31.2304,
                longitude=121.4737,
            ),
        ),
        "scenes": {
            SceneId.DAY_WORK: "WORK",
            SceneId.NIGHT_LEISURE: "CHILL",
            SceneId.RAIN: "RAIN",
        },
        "disturbance": {
            "startup_grace_seconds": 12,
            "idle_before_switch_seconds": 30,
            "maximum_deferral_minutes": 90,
            "cycle_interval_minutes": 20,
        },
        "activity": ActivityProfile(
            work_processes=["Obsidian", "Code"],
            leisure_processes=["steam"],
            work_title_keywords=["GitHub"],
            leisure_title_keywords=["YouTube"],
        ),
    }
    values.update(overrides)
    return Profile.model_validate(values)


def test_profile_rejects_activity_target_assigned_to_both_modes():
    with pytest.raises(ValidationError, match="Code"):
        _profile(
            activity=ActivityProfile(
                work_processes=["Code"],
                leisure_processes=["code.exe"],
            )
        )


def test_profile_rejects_internal_scheduler_fields():
    values = _profile().model_dump(mode="json")
    values["policies"] = {"weather": {"weight": 99}}

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Profile.model_validate(values)


def test_profile_defaults_to_balanced_response_style():
    assert _profile().matching.response_style == "balanced"


@pytest.mark.parametrize(
    "response_style",
    [
        "background",
        "background_leaning",
        "balanced",
        "current_leaning",
        "current",
    ],
)
def test_profile_accepts_supported_response_styles(response_style: str):
    profile = _profile(matching={"response_style": response_style})

    assert profile.matching.response_style == response_style


@pytest.mark.parametrize("field", ["avoid_fullscreen", "high_load_threshold_percent"])
def test_profile_rejects_hidden_disturbance_fields(field: str):
    values = _profile().model_dump(mode="json")
    values["disturbance"][field] = False if field == "avoid_fullscreen" else 50

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Profile.model_validate(values)


@pytest.mark.parametrize("field", ["preset", "overrides"])
def test_profile_rejects_disturbance_presentation_fields(field: str):
    values = _profile().model_dump(mode="json")
    values["disturbance"][field] = "balanced" if field == "preset" else {}

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Profile.model_validate(values)


def test_profile_requires_at_least_one_scene_assignment():
    with pytest.raises(ValidationError, match="Dictionary should have at least 1 item"):
        _profile(scenes={})


@pytest.mark.parametrize(("scene", "expected_tags"), EXPECTED_SCENE_TAGS.items())
def test_compiler_expands_each_builtin_scene(scene: SceneId, expected_tags: dict[str, float]):
    runtime = ProfileCompiler.compile(_profile(scenes={scene: "TARGET"}))

    assert runtime.scenes[scene].playlist == "TARGET"
    assert runtime.scenes[scene].tags == expected_tags


def test_compiler_expands_user_intent_into_complete_runtime_config():
    runtime = ProfileCompiler.compile(
        _profile(),
        playlist_item_counts={"WORK": 7, "CHILL": 4, "RAIN": 2},
    )

    assert runtime.wallpaper_engine_path == r"C:\Wallpaper Engine\wallpaper64.exe"
    assert runtime.language == "zh"
    assert runtime.scenes[SceneId.DAY_WORK].playlist == "WORK"
    assert runtime.scenes[SceneId.DAY_WORK].tags == {
        "focus": 1.0,
        "day": 0.9,
        "dawn": 0.3,
        "clear": 0.3,
    }
    assert runtime.scenes[SceneId.DAY_WORK].item_count == 7
    assert runtime.scenes[SceneId.NIGHT_LEISURE].playlist == "CHILL"
    assert runtime.scenes[SceneId.NIGHT_LEISURE].tags == {
        "chill": 1.0,
        "night": 0.9,
        "clear": 0.2,
    }
    assert runtime.scenes[SceneId.RAIN].playlist == "RAIN"
    assert runtime.scenes[SceneId.RAIN].tags == {
        "rain": 1.2,
        "storm": 0.4,
        "day": 0.3,
        "night": 0.3,
        "chill": 0.3,
    }

    assert runtime.scheduling.startup_delay == 12
    assert runtime.scheduling.idle_threshold == 30
    assert runtime.scheduling.force_after == 5400
    assert runtime.scheduling.cycle_cooldown == 1200
    assert runtime.scheduling.pause_on_fullscreen is True
    assert runtime.scheduling.cpu_threshold == 85
    assert runtime.scheduling.cpu_sample_window == 10

    assert runtime.policies.activity.enabled is True
    assert runtime.policies.activity.smoothing_window == 120
    assert [matcher.model_dump() for matcher in runtime.policies.activity.matchers] == [
        {
            "source": "process",
            "match": "exact",
            "pattern": "Code",
            "tag": "focus",
            "case_sensitive": False,
        },
        {
            "source": "process",
            "match": "exact",
            "pattern": "Obsidian",
            "tag": "focus",
            "case_sensitive": False,
        },
        {
            "source": "process",
            "match": "exact",
            "pattern": "steam",
            "tag": "chill",
            "case_sensitive": False,
        },
        {
            "source": "title",
            "match": "contains",
            "pattern": "GitHub",
            "tag": "focus",
            "case_sensitive": False,
        },
        {
            "source": "title",
            "match": "contains",
            "pattern": "YouTube",
            "tag": "chill",
            "case_sensitive": False,
        },
    ]

    assert runtime.policies.time.enabled is True
    assert runtime.policies.time.auto is True
    assert runtime.policies.time.day_start_hour == 8
    assert runtime.policies.time.night_start_hour == 20
    assert runtime.policies.season.enabled is True
    assert runtime.policies.season.spring_peak == 80
    assert runtime.policies.season.summer_peak == 172
    assert runtime.policies.season.autumn_peak == 265
    assert runtime.policies.season.winter_peak == 355
    assert runtime.policies.weather.enabled is True
    assert runtime.policies.weather.api_key == "test-key"
    assert runtime.policies.weather.lat == pytest.approx(31.2304)
    assert runtime.policies.weather.lon == pytest.approx(121.4737)
    assert runtime.policies.weather.fetch_interval == 600
    assert runtime.policies.weather.request_timeout == 10
    assert runtime.policies.weather.warmup_timeout == 3
    assert runtime.tags["storm"].fallback == {"rain": 1.0}
    assert runtime.tags["snow"].fallback == {"winter": 0.6, "rain": 0.6}


def test_compiler_uses_resolved_disturbance_values():
    runtime = ProfileCompiler.compile(
        _profile(
            disturbance={
                "startup_grace_seconds": 30,
                "idle_before_switch_seconds": 60,
                "maximum_deferral_minutes": 180,
                "cycle_interval_minutes": 7,
            }
        )
    )

    assert runtime.scheduling.startup_delay == 30
    assert runtime.scheduling.idle_threshold == 60
    assert runtime.scheduling.force_after == 10800
    assert runtime.scheduling.cycle_cooldown == 420
    assert runtime.scheduling.pause_on_fullscreen is True
    assert runtime.scheduling.cpu_threshold == 85


def test_compiler_preserves_scenes_assigned_to_the_same_playlist():
    runtime = ProfileCompiler.compile(
        _profile(
            scenes={
                SceneId.DAY_WORK: "MIXED",
                SceneId.NIGHT_WORK: "MIXED",
            }
        )
    )

    assert runtime.scenes[SceneId.DAY_WORK].playlist == "MIXED"
    assert runtime.scenes[SceneId.DAY_WORK].tags == {
        "focus": 1.0,
        "day": 0.9,
        "dawn": 0.3,
        "clear": 0.3,
    }
    assert runtime.scenes[SceneId.NIGHT_WORK].playlist == "MIXED"
    assert runtime.scenes[SceneId.NIGHT_WORK].tags == {
        "focus": 1.0,
        "night": 0.9,
        "clear": 0.2,
    }


def test_compiler_output_is_deterministic_for_equivalent_profile_ordering():
    first = _profile(
        scenes={
            SceneId.RAIN: "RAIN",
            SceneId.DAY_WORK: "WORK",
        },
        activity=ActivityProfile(work_processes=["Obsidian", "Code"]),
    )
    second = _profile(
        scenes={
            SceneId.DAY_WORK: "WORK",
            SceneId.RAIN: "RAIN",
        },
        activity=ActivityProfile(work_processes=["Code", "Obsidian"]),
    )

    first_runtime = ProfileCompiler.compile(first)
    second_runtime = ProfileCompiler.compile(second)

    assert first_runtime.model_dump(mode="json") == second_runtime.model_dump(mode="json")
