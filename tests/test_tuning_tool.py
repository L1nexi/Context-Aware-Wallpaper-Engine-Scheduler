from __future__ import annotations

import csv
import json
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
from tools.tuning.heatmaps import (
    HeatmapFigure,
    HeatmapRenderDependencyError,
    HeatmapSampling,
    activity_from_axis,
    build_heatmap_grid,
)
from tools.tuning.sweep import evaluate_parameter_sweep, write_sweep_csv
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


def test_heatmap_activity_axis_maps_chill_idle_focus() -> None:
    chill_signal = activity_from_axis(-0.4)
    idle_signal = activity_from_axis(0.0)
    focus_signal = activity_from_axis(0.6)

    assert chill_signal is not None
    assert chill_signal.direction == {"chill": 1.0}
    assert chill_signal.intensity == pytest.approx(0.4)
    assert idle_signal is None
    assert focus_signal is not None
    assert focus_signal.direction == {"focus": 1.0}
    assert focus_signal.intensity == pytest.approx(0.6)


def test_heatmap_grid_uses_evaluate_scenario_results(tmp_path: Path) -> None:
    config = ConfigLoader(str(_write_config_dir(tmp_path))).load_verified_config()
    sampling = HeatmapSampling(hour_step=12.0)

    current_grid = build_heatmap_grid(
        config,
        MatchProfile("current"),
        "weather-hour",
        sampling=sampling,
    )
    candidate_grid = build_heatmap_grid(
        config,
        MatchProfile("candidate", gamma_playlist=1.2, gamma_context=1.1),
        "weather-hour",
        sampling=sampling,
    )

    assert current_grid.profile.name == "current"
    assert candidate_grid.profile.name == "candidate"
    assert current_grid.x_axis.values == (0.0, 12.0)
    assert len(current_grid.y_axis.values) == 11
    assert len(current_grid.cells) == 11
    assert all(len(row) == 2 for row in current_grid.cells)
    assert current_grid.cells[0][0].winner in {"FOCUS", "CHILL", None}
    assert current_grid.cells[0][0].score >= 0.0
    assert current_grid.cells[0][0].gap >= 0.0


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


def test_parameter_sweep_summarizes_pass_gap_and_churn(tmp_path: Path) -> None:
    config = ConfigLoader(str(_write_config_dir(tmp_path))).load_verified_config()
    scenarios = [
        Scenario(
            "balanced clear midnight",
            hour=0,
            day_of_year=1,
            weather=weather("clear"),
            activity=ActivitySignal({"focus": 1.0, "chill": 0.8}),
            expected="FOCUS",
        ),
        Scenario(
            "day focus clear",
            hour=14,
            day_of_year=95,
            weather=weather("clear"),
            activity=focus(),
            expected="FOCUS",
        ),
        Scenario(
            "observed rain mix",
            hour=17,
            day_of_year=220,
            weather=weather("light_rain"),
            activity=ActivitySignal({"focus": 0.7, "chill": 0.3}, intensity=0.4),
        ),
    ]

    report = evaluate_parameter_sweep(
        config,
        scenarios,
        gamma_playlist=[1.0, 1.2],
        gamma_context=[1.0],
    )

    assert report.profile_count == 2
    assert [row.profile for row in report.rows] == ["gp1-gc1", "gp1.2-gc1"]
    current_row = report.rows[0]
    assert current_row.expected_total == 2
    assert current_row.pass_count == 2
    assert current_row.fail_count == 0
    assert current_row.pass_rate == pytest.approx(1.0)
    assert current_row.avg_gap == pytest.approx(0.4119700861881485)
    assert current_row.churn_count == 0
    assert current_row.churn_rate == pytest.approx(0.0)

    tuned_row = report.rows[1]
    assert tuned_row.pass_count == 1
    assert tuned_row.fail_count == 1
    assert tuned_row.pass_rate == pytest.approx(0.5)
    assert tuned_row.avg_gap == pytest.approx(0.42170840149684613)
    assert tuned_row.churn_count == 1
    assert tuned_row.churn_rate == pytest.approx(1 / 3)

    csv_path = tmp_path / "sweep.csv"
    write_sweep_csv(csv_path, report)
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[1]["profile"] == "gp1.2-gc1"
    assert rows[1]["pass_rate"] == "0.500000"
    assert rows[1]["churn_rate"] == "0.333333"


def test_parameter_sweep_uses_zero_pass_rate_without_expected_scenarios(tmp_path: Path) -> None:
    config = ConfigLoader(str(_write_config_dir(tmp_path))).load_verified_config()
    scenarios = [
        Scenario(
            "observed rain mix",
            hour=17,
            day_of_year=220,
            weather=weather("light_rain"),
            activity=ActivitySignal({"focus": 0.7, "chill": 0.3}, intensity=0.4),
        )
    ]

    report = evaluate_parameter_sweep(
        config,
        scenarios,
        gamma_playlist=[1.0],
        gamma_context=[1.0],
    )

    assert report.baseline.expected_total == 0
    assert report.baseline.pass_rate == pytest.approx(0.0)
    assert report.rows[0].expected_total == 0
    assert report.rows[0].pass_rate == pytest.approx(0.0)

    csv_path = tmp_path / "sweep.csv"
    write_sweep_csv(csv_path, report)
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["expected_total"] == "0"
    assert rows[0]["pass_rate"] == "0.000000"


def test_run_tuning_writes_report_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    figures = [
        HeatmapFigure(
            path="figures/current-weather-hour-winner.png",
            profile="current",
            mode="weather-hour",
            type="winner",
        )
    ]

    def fake_generate_default_heatmaps(*_args: object, **_kwargs: object) -> list[HeatmapFigure]:
        return figures

    monkeypatch.setattr("tools.tuning.tune.require_heatmap_renderer", lambda: None)
    monkeypatch.setattr("tools.tuning.tune.generate_default_heatmaps", fake_generate_default_heatmaps)

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
    assert (run_dir / "sweep.csv").is_file()

    summary = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "## Parameter Sweep" in summary
    assert "## Scenario Diagnostics" in summary
    assert "### day focus clear" in summary
    assert "- Raw context:" in summary
    assert "- Resolved context:" in summary
    assert "- Policy contributions:" in summary
    assert "activity: active=True" in summary
    assert "time: active=True" in summary

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["figures"] == [figures[0].to_manifest()]
    assert manifest["sweep"] == {
        "path": "sweep.csv",
        "profile_count": 36,
        "gamma_playlist": [0.8, 0.9, 1.0, 1.1, 1.2, 1.3],
        "gamma_context": [0.8, 0.9, 1.0, 1.1, 1.2, 1.3],
    }

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


def test_run_tuning_requires_heatmap_renderer_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = _write_config_dir(tmp_path)
    scenario = Scenario("day focus clear", hour=14, day_of_year=95, expected="FOCUS")

    def fail_require_heatmap_renderer() -> None:
        raise HeatmapRenderDependencyError("missing renderer")

    monkeypatch.setattr("tools.tuning.tune.require_heatmap_renderer", fail_require_heatmap_renderer)

    with pytest.raises(HeatmapRenderDependencyError, match="missing renderer"):
        run_tuning(
            config_dir=config_dir,
            scenarios=[scenario],
            profiles=[MatchProfile("current")],
            out_root=tmp_path / "runs",
            run_name="test",
        )
    assert not (tmp_path / "runs").exists()
