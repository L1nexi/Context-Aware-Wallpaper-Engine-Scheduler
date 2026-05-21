from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.tuning.models import (  # noqa: E402
    MatchProfile,
    Scenario,
    ScenarioProfileResult,
    evaluate_scenario,
)
from tools.tuning.heatmaps import (  # noqa: E402
    HeatmapSampling,
    generate_default_heatmaps,
)
from tools.tuning.sweep import (  # noqa: E402
    SweepReport,
    SweepRow,
    evaluate_parameter_sweep,
    sorted_sweep_rows,
)
from utils.config_loader import ConfigLoader  # noqa: E402

AMBIGUOUS_FAILURE_GAP = 0.05
CONFIDENT_FAILURE_GAP = 0.15
LOW_CHURN_PASS_RATE_TOLERANCE = 0.02


def run_tuning(
    *,
    config_dir: Path,
    scenarios: Iterable[Scenario],
    profiles: Iterable[MatchProfile],
    out_root: Path,
    run_name: str,
    heatmap_sampling: HeatmapSampling = HeatmapSampling(),
) -> Path:
    scenario_list = list(scenarios)
    profile_list = list(profiles)
    if not profile_list:
        raise ValueError("at least one match profile is required")
    if not scenario_list:
        raise ValueError("at least one scenario is required")
    _ensure_unique_names((scenario.name for scenario in scenario_list), "scenario")
    _ensure_unique_names((profile.name for profile in profile_list), "profile")

    config = ConfigLoader(str(config_dir)).load_verified_config()
    run_dir = _make_run_dir(out_root, run_name)

    results: dict[str, dict[str, ScenarioProfileResult]] = {}
    for scenario in scenario_list:
        scenario_results: dict[str, ScenarioProfileResult] = {}
        results[scenario.name] = scenario_results
        for profile in profile_list:
            scenario_results[profile.name] = evaluate_scenario(config, scenario, profile)

    figures = generate_default_heatmaps(
        config,
        profile_list,
        run_dir / "heatmaps",
        sampling=heatmap_sampling,
    )
    sweep_report = evaluate_parameter_sweep(
        config,
        scenario_list,
        confident_failure_gap=CONFIDENT_FAILURE_GAP,
    )

    _write_report(run_dir, scenario_list, profile_list, results, sweep_report, len(figures))
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run internal matcher tuning scenarios.")
    parser.add_argument("--config", default="config", help="Config directory to load.")
    parser.add_argument("--run-name", default="r6-tuning", help="Name suffix for the run output directory.")
    parser.add_argument(
        "--out-root",
        default=str(Path(__file__).resolve().parent / "runs"),
        help="Directory where run outputs are written.",
    )
    args = parser.parse_args()

    from tools.tuning.scenarios_r6 import PROFILES, SCENARIOS

    run_dir = run_tuning(
        config_dir=Path(args.config),
        scenarios=SCENARIOS,
        profiles=PROFILES,
        out_root=Path(args.out_root),
        run_name=args.run_name,
    )
    print(f"Wrote tuning report: {run_dir}")


def _make_run_dir(out_root: Path, run_name: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", run_name.strip()).strip("-_.") or "run"
    for index in range(100):
        suffix = "" if index == 0 else f"-{index + 1}"
        run_dir = out_root / f"{timestamp}_{safe_name}{suffix}"
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            return run_dir
        except FileExistsError:
            continue
    raise FileExistsError(f"could not create a unique run directory for {safe_name!r}")


def _ensure_unique_names(names: Iterable[str], label: str) -> None:
    counts = Counter(names)
    duplicates = [name for name, count in counts.items() if count > 1]
    if duplicates:
        raise ValueError(f"{label} names must be unique: {', '.join(sorted(duplicates))}")


def _write_report(
    run_dir: Path,
    scenarios: list[Scenario],
    profiles: list[MatchProfile],
    results: dict[str, dict[str, ScenarioProfileResult]],
    sweep_report: SweepReport,
    figure_count: int,
) -> None:
    baseline = profiles[0]
    baseline_results = [results[scenario.name][baseline.name] for scenario in scenarios]
    expected_scenarios = [scenario for scenario in scenarios if scenario.expected is not None]
    observed_scenarios = [scenario for scenario in scenarios if scenario.expected is None]
    lines = ["# Tuning Report", ""]
    lines.append(
        f"Baseline profile: {baseline.name}. Scenarios: {len(scenarios)} "
        f"({len(expected_scenarios)} expected, {len(observed_scenarios)} observed). "
        f"Winner heatmaps: {figure_count}."
    )
    lines.extend(["", "## Scenario Results", ""])
    lines.append("| Scenario | Category | Expected | Winner | Status | Gap | Top3 | Resolved Tags Top |")
    lines.append("| --- | --- | --- | --- | --- | ---: | --- | --- |")
    for scenario, result in zip(scenarios, baseline_results):
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_table(scenario.name),
                    _escape_table(scenario.category),
                    _escape_table(scenario.expected or "observed"),
                    _escape_table(result.winner or "none"),
                    result.expected_status,
                    _fmt_float(result.gap),
                    _escape_table(_format_top_rankings(result)),
                    _escape_table(_format_resolved_tags_top(result)),
                ]
            )
            + " |"
        )

    _append_coverage_summary(lines, scenarios, baseline_results)
    _append_parameter_sweep_summary(lines, sweep_report)

    (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def _append_coverage_summary(
    lines: list[str],
    scenarios: list[Scenario],
    results: list[ScenarioProfileResult],
) -> None:
    expected_results = [
        result
        for scenario, result in zip(scenarios, results)
        if scenario.expected is not None
    ]
    pass_count = sum(1 for result in expected_results if result.expected_status == "pass")
    lines.extend(["", "## Coverage Summary", ""])
    lines.append(f"Overall expected pass: {pass_count}/{len(expected_results)}")
    lines.append("")
    lines.append("| Category | Pass | Fail | Observed |")
    lines.append("| --- | ---: | ---: | ---: |")
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for scenario, result in zip(scenarios, results):
        grouped[scenario.category][result.expected_status] += 1
    for category in sorted(grouped):
        counts = grouped[category]
        lines.append(
            f"| {category} | {counts['pass']} | {counts['fail']} | {counts['observed']} |"
        )
    ambiguous = [
        (scenario, result)
        for scenario, result in zip(scenarios, results)
        if result.expected_status == "fail" and result.gap < AMBIGUOUS_FAILURE_GAP
    ]
    confident = [
        (scenario, result)
        for scenario, result in zip(scenarios, results)
        if result.expected_status == "fail" and result.gap >= CONFIDENT_FAILURE_GAP
    ]
    lines.extend(["", "Ambiguous failures:"])
    _append_failure_list(lines, ambiguous)
    lines.extend(["", "Confident failures:"])
    _append_failure_list(lines, confident)


def _append_failure_list(
    lines: list[str],
    failures: list[tuple[Scenario, ScenarioProfileResult]],
) -> None:
    if not failures:
        lines.append("- none")
        return
    for scenario, result in failures:
        lines.append(
            f"- {scenario.name}: expected {scenario.expected}, got {result.winner or 'none'}, "
            f"gap={_fmt_float(result.gap)}"
        )


def _append_parameter_sweep_summary(lines: list[str], sweep_report: SweepReport) -> None:
    lines.extend(["", "## Sweep Summary", ""])
    lines.append("Baseline current:")
    lines.append("")
    baseline = sweep_report.baseline
    lines.append(
        f"- pass_rate_expected={_fmt_float(baseline.pass_rate_expected)}, "
        f"avg_gap_expected={_fmt_float(baseline.avg_gap_expected)}, "
        f"confident_fail_count_expected={baseline.confident_fail_count_expected}"
    )
    lines.append("")
    best_pass_rate = sorted_sweep_rows(sweep_report.rows)[0]
    best_low_churn = _best_low_churn_candidate(sweep_report.rows, best_pass_rate.pass_rate_expected)
    lines.append("Best pass-rate candidate:")
    lines.append(f"- {_format_sweep_row(best_pass_rate)}")
    lines.append("")
    lines.append("Best low-churn candidate:")
    lines.append(f"- {_format_sweep_row(best_low_churn)}")


def _best_low_churn_candidate(rows: Iterable[SweepRow], best_pass_rate: float) -> SweepRow:
    eligible = [
        row
        for row in rows
        if (
            row.core_regression_count_expected == 0
            and row.pass_rate_expected >= best_pass_rate - LOW_CHURN_PASS_RATE_TOLERANCE
        )
    ]
    if not eligible:
        eligible = [
            row
            for row in rows
            if row.pass_rate_expected >= best_pass_rate - LOW_CHURN_PASS_RATE_TOLERANCE
        ]
    return sorted(
        eligible,
        key=lambda row: (
            row.core_regression_count_expected,
            row.churn_rate_expected,
            row.confident_fail_count_expected,
            -row.pass_rate_expected,
            -row.avg_gap_expected,
            row.profile,
        ),
    )[0]


def _format_sweep_row(row: SweepRow) -> str:
    return (
        f"{row.profile}: pass_rate_expected={_fmt_float(row.pass_rate_expected)}, "
        f"avg_gap_expected={_fmt_float(row.avg_gap_expected)}, "
        f"churn_rate_expected={_fmt_float(row.churn_rate_expected)}, "
        f"confident_fail_count_expected={row.confident_fail_count_expected}, "
        f"core_regression_count_expected={row.core_regression_count_expected}"
    )


def _fmt_float(value: float) -> str:
    return f"{value:.6f}"


def _format_top_rankings(result: ScenarioProfileResult, limit: int = 3) -> str:
    if not result.rankings:
        return "none"
    return ", ".join(
        f"{row.playlist} {_fmt_float(row.score)}"
        for row in result.rankings[:limit]
    )


def _format_resolved_tags_top(result: ScenarioProfileResult, limit: int = 5) -> str:
    if not result.match.resolved_context_vector:
        return "none"
    items = sorted(
        result.match.resolved_context_vector.items(),
        key=lambda item: (-item[1], item[0]),
    )
    return ", ".join(f"{tag} {_fmt_float(value)}" for tag, value in items[:limit])


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    main()
