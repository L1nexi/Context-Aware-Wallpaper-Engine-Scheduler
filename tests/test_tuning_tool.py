from __future__ import annotations

import csv
from pathlib import Path

import pytest
import yaml

from core.matcher import Matcher
from core.policies import SeasonPolicy, TimePolicy, WeatherPolicy
from tools.tuning.models import (
    ActivitySignal,
    DirectActivityPolicy,
    MatchProfile,
    Scenario,
    build_context,
    evaluate_scenario,
    focus,
    matrix,
    weather,
)
from tools.tuning.tune import run_tuning
from utils.config_loader import ConfigLoader
from utils.runtime_config import ActivityPolicyConfig


TAG_NAMES = [
    "focus",
    "chill",
    "dawn",
    "day",
    "sunset",
    "night",
    "spring",
    "summer",
    "autumn",
    "winter",
    "clear",
    "cloudy",
    "rain",
    "storm",
    "snow",
    "fog",
]


def _write_config_dir(tmp_path: Path) -> Path:
    fake_exe = tmp_path / "wallpaper64.exe"
    fake_exe.write_text("fake", encoding="utf-8")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    documents = {
        "scheduler.yaml": {
            "version": 2,
            "runtime": {
                "wallpaper_engine_path": str(fake_exe),
                "language": None,
            },
        },
        "playlists.yaml": {
            "playlists": {
                "FOCUS": {
                    "display": "Focus",
                    "color": "#F5C518",
                    "tags": {"focus": 1.0, "day": 0.8, "clear": 0.4},
                },
                "CHILL": {
                    "display": "Chill",
                    "color": "#4A90D9",
                    "tags": {"chill": 1.0, "night": 0.7, "rain": 0.3},
                },
            }
        },
        "tags.yaml": {"tags": {name: {"fallback": {}} for name in TAG_NAMES}},
        "activity.yaml": {
            "activity": {
                "enabled": True,
                "weight": 1.2,
                "smoothing_window": 120,
                "process": {},
                "title": {},
                "matchers": [],
            }
        },
        "context.yaml": {
            "time": {
                "enabled": True,
                "weight": 0.8,
                "auto": True,
                "day_start_hour": 8,
                "night_start_hour": 20,
            },
            "season": {
                "enabled": True,
                "weight": 0.65,
                "spring_peak": 80,
                "summer_peak": 172,
                "autumn_peak": 265,
                "winter_peak": 355,
            },
            "weather": {
                "enabled": True,
                "weight": 1.5,
                "api_key": "",
                "lat": 0.0,
                "lon": 0.0,
                "fetch_interval": 600,
                "request_timeout": 10,
                "warmup_timeout": 3,
            },
        },
        "scheduling.yaml": {
            "scheduling": {
                "startup_delay": 15,
                "idle_threshold": 20,
                "switch_cooldown": 150,
                "cycle_cooldown": 900,
                "force_after": 3600,
                "cpu_threshold": 85,
                "cpu_sample_window": 10,
                "pause_on_fullscreen": True,
            }
        },
    }
    for file_name, document in documents.items():
        (config_dir / file_name).write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    return config_dir


def test_direct_activity_policy_preserves_direction_and_intensity() -> None:
    direction = {"focus": 0.7, "chill": 0.3}
    policy = DirectActivityPolicy(
        ActivityPolicyConfig(enabled=True, weight=1.2),
        ActivitySignal(direction, intensity=0.5),
    )
    direction["focus"] = 0.1

    evaluation = policy.evaluate(build_context(Scenario("base", hour=12, day_of_year=100)))

    assert evaluation.active is True
    assert evaluation.effective_magnitude == pytest.approx(0.6)
    assert evaluation.direction["focus"] == pytest.approx(0.7 / (0.7**2 + 0.3**2) ** 0.5)
    assert evaluation.direction["chill"] == pytest.approx(0.3 / (0.7**2 + 0.3**2) ** 0.5)
    assert evaluation.raw_contribution["focus"] == pytest.approx(evaluation.direction["focus"] * 0.6)
    assert evaluation.raw_contribution["chill"] == pytest.approx(evaluation.direction["chill"] * 0.6)


def test_build_context_rounds_fractional_hour_through_midnight() -> None:
    context = build_context(Scenario("late", hour=23.999, day_of_year=100))

    assert context.time.tm_yday == 101
    assert context.time.tm_hour == 0
    assert context.time.tm_min == 0


def test_matrix_builds_observed_cartesian_scenarios() -> None:
    scenarios = matrix(
        "trial",
        hours=[14, 23],
        days=[95],
        weathers=[None, "clear"],
        activities=[None, focus(0.4)],
    )

    assert len(scenarios) == 8
    assert scenarios[0].name == "trial doy95 h14 idle none"
    assert scenarios[-1].name == "trial doy95 h23 focus1-i0.4 clear"
    assert all(scenario.expected is None for scenario in scenarios)
    assert all(scenario.note == "matrix trial" for scenario in scenarios)


def test_current_profile_matches_existing_matcher_scoring(tmp_path: Path) -> None:
    config = ConfigLoader(str(_write_config_dir(tmp_path))).load_verified_config()
    scenario = Scenario(
        "day focus clear",
        hour=14,
        day_of_year=95,
        weather=weather("clear"),
        activity=focus(),
        expected="FOCUS",
    )
    context = build_context(scenario)
    policies = [
        DirectActivityPolicy(config.policies.activity, scenario.activity),
        TimePolicy(config.policies.time),
        SeasonPolicy(config.policies.season),
        WeatherPolicy(config.policies.weather),
    ]
    expected_match = Matcher(config.playlists, policies, config.tags).evaluate(context)

    result = evaluate_scenario(config, scenario, MatchProfile("current"))

    assert [name for name, _score in result.match.playlist_matches] == [
        name for name, _score in expected_match.playlist_matches
    ]
    for actual, expected in zip(result.match.playlist_matches, expected_match.playlist_matches):
        assert actual[1] == pytest.approx(expected[1])


def test_run_tuning_writes_report_artifacts(tmp_path: Path) -> None:
    config_dir = _write_config_dir(tmp_path)
    scenarios = [
        Scenario(
            "day focus clear",
            hour=14,
            day_of_year=95,
            weather=weather("clear"),
            activity=focus(),
            expected="FOCUS",
        ),
        Scenario(
            "observed drizzle",
            hour=17,
            day_of_year=220,
            weather=weather("light_rain"),
            activity=ActivitySignal({"focus": 0.7, "chill": 0.3}, intensity=0.4),
        ),
    ]
    profiles = [MatchProfile("current"), MatchProfile("candidate", gamma_playlist=1.2, gamma_context=1.1)]

    run_dir = run_tuning(
        config_dir=config_dir,
        scenarios=scenarios,
        profiles=profiles,
        out_root=tmp_path / "runs",
        run_name="test",
    )

    assert (run_dir / "manifest.json").is_file()
    assert (run_dir / "rankings.csv").is_file()
    assert (run_dir / "compare.csv").is_file()
    assert (run_dir / "summary.md").is_file()

    summary = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "## Scenario Diagnostics" in summary
    assert "### day focus clear" in summary
    assert "- Raw context:" in summary
    assert "- Resolved context:" in summary
    assert "- Policy contributions:" in summary
    assert "activity: active=True" in summary
    assert "time: active=True" in summary

    with (run_dir / "compare.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    observed = next(row for row in rows if row["scenario"] == "observed drizzle")
    assert observed["current_status"] == "observed"
    assert observed["candidate_status"] == "observed"


def test_run_tuning_rejects_duplicate_names(tmp_path: Path) -> None:
    config_dir = _write_config_dir(tmp_path)
    scenario = Scenario("duplicate", hour=14, day_of_year=95, expected="FOCUS")

    with pytest.raises(ValueError, match="scenario names must be unique"):
        run_tuning(
            config_dir=config_dir,
            scenarios=[scenario, scenario],
            profiles=[MatchProfile("current")],
            out_root=tmp_path / "runs",
            run_name="test",
        )

    with pytest.raises(ValueError, match="profile names must be unique"):
        run_tuning(
            config_dir=config_dir,
            scenarios=[scenario],
            profiles=[MatchProfile("current"), MatchProfile("current")],
            out_root=tmp_path / "runs",
            run_name="test",
        )
