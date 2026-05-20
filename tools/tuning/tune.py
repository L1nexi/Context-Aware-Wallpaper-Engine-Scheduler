from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
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
    profile_to_dict,
    scenario_to_dict,
)
from utils.config_loader import ConfigLoader  # noqa: E402


def run_tuning(
    *,
    config_dir: Path,
    scenarios: Iterable[Scenario],
    profiles: Iterable[MatchProfile],
    out_root: Path,
    run_name: str,
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

    _write_manifest(run_dir, config_dir, run_name, scenario_list, profile_list)
    _write_rankings(run_dir, scenario_list, profile_list, results)
    _write_compare(run_dir, scenario_list, profile_list, results)
    _write_summary(run_dir, scenario_list, profile_list, results)
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


def _write_manifest(
    run_dir: Path,
    config_dir: Path,
    run_name: str,
    scenarios: list[Scenario],
    profiles: list[MatchProfile],
) -> None:
    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_name": run_name,
        "config_dir": str(config_dir),
        "scenario_count": len(scenarios),
        "profiles": [profile_to_dict(profile) for profile in profiles],
        "scenarios": [scenario_to_dict(scenario) for scenario in scenarios],
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_rankings(
    run_dir: Path,
    scenarios: list[Scenario],
    profiles: list[MatchProfile],
    results: dict[str, dict[str, ScenarioProfileResult]],
) -> None:
    with (run_dir / "rankings.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["scenario", "profile", "rank", "playlist", "score"],
        )
        writer.writeheader()
        for scenario in scenarios:
            for profile in profiles:
                for ranking in results[scenario.name][profile.name].rankings:
                    writer.writerow(
                        {
                            "scenario": ranking.scenario,
                            "profile": ranking.profile,
                            "rank": ranking.rank,
                            "playlist": ranking.playlist,
                            "score": _fmt_float(ranking.score),
                        }
                    )


def _write_compare(
    run_dir: Path,
    scenarios: list[Scenario],
    profiles: list[MatchProfile],
    results: dict[str, dict[str, ScenarioProfileResult]],
) -> None:
    baseline = profiles[0]
    candidates = profiles[1:] or profiles[:1]
    with (run_dir / "compare.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "scenario",
                "expected",
                "candidate_profile",
                "current_winner",
                "candidate_winner",
                "current_gap",
                "candidate_gap",
                "current_status",
                "candidate_status",
                "winner_changed",
                "status_changed",
                "gap_delta",
                "note",
            ],
        )
        writer.writeheader()
        for scenario in scenarios:
            current = results[scenario.name][baseline.name]
            for candidate_profile in candidates:
                candidate = results[scenario.name][candidate_profile.name]
                writer.writerow(
                    {
                        "scenario": scenario.name,
                        "expected": scenario.expected or "",
                        "candidate_profile": candidate_profile.name,
                        "current_winner": current.winner or "",
                        "candidate_winner": candidate.winner or "",
                        "current_gap": _fmt_float(current.gap),
                        "candidate_gap": _fmt_float(candidate.gap),
                        "current_status": current.expected_status,
                        "candidate_status": candidate.expected_status,
                        "winner_changed": current.winner != candidate.winner,
                        "status_changed": current.expected_status != candidate.expected_status,
                        "gap_delta": _fmt_float(candidate.gap - current.gap),
                        "note": scenario.note,
                    }
                )


def _write_summary(
    run_dir: Path,
    scenarios: list[Scenario],
    profiles: list[MatchProfile],
    results: dict[str, dict[str, ScenarioProfileResult]],
) -> None:
    expected_scenarios = [scenario for scenario in scenarios if scenario.expected is not None]
    observed_scenarios = [scenario for scenario in scenarios if scenario.expected is None]
    lines = ["# Tuning Summary", ""]
    lines.append(f"Scenarios: {len(scenarios)} ({len(expected_scenarios)} expected, {len(observed_scenarios)} observed)")
    lines.append("")
    lines.append("## Profile Results")
    lines.append("")
    lines.append("| Profile | Pass | Fail | Avg Gap |")
    lines.append("| --- | ---: | ---: | ---: |")
    for profile in profiles:
        profile_results = [results[scenario.name][profile.name] for scenario in expected_scenarios]
        passed = sum(1 for result in profile_results if result.expected_status == "pass")
        failed = sum(1 for result in profile_results if result.expected_status == "fail")
        avg_gap = _average(result.gap for result in profile_results)
        lines.append(f"| {profile.name} | {passed} | {failed} | {_fmt_float(avg_gap)} |")

    if len(profiles) > 1:
        baseline = profiles[0]
        lines.extend(["", "## Changes vs Current", ""])
        for candidate_profile in profiles[1:]:
            changed = []
            status_changed = []
            for scenario in scenarios:
                current = results[scenario.name][baseline.name]
                candidate = results[scenario.name][candidate_profile.name]
                if current.winner != candidate.winner:
                    changed.append((scenario, current, candidate))
                if current.expected_status != candidate.expected_status:
                    status_changed.append((scenario, current, candidate))

            lines.append(f"### {candidate_profile.name}")
            lines.append("")
            lines.append(f"Winner changes: {len(changed)}")
            for scenario, current, candidate in changed[:20]:
                marker = "observed" if scenario.expected is None else scenario.expected
                lines.append(f"- {scenario.name}: {current.winner} -> {candidate.winner} ({marker})")
            if len(changed) > 20:
                lines.append(f"- ... {len(changed) - 20} more")
            lines.append("")
            lines.append(f"Status changes: {len(status_changed)}")
            for scenario, current, candidate in status_changed[:20]:
                lines.append(
                    f"- {scenario.name}: {current.expected_status} -> {candidate.expected_status}"
                )
            lines.append("")

    lines.extend(["", "## Top 3", ""])
    for scenario in scenarios:
        lines.append(f"### {scenario.name}")
        if scenario.expected is not None:
            lines.append(f"Expected: {scenario.expected}")
        if scenario.note:
            lines.append(f"Note: {scenario.note}")
        for profile in profiles:
            result = results[scenario.name][profile.name]
            top3 = ", ".join(
                f"{row.playlist}({_fmt_float(row.score)})"
                for row in result.rankings[:3]
            )
            lines.append(f"- {profile.name}: {result.winner} gap={_fmt_float(result.gap)} top3={top3}")
        lines.append("")

    lines.extend(["", "## Scenario Diagnostics", ""])
    for scenario in scenarios:
        lines.append(f"### {scenario.name}")
        if scenario.expected is not None:
            lines.append(f"Expected: {scenario.expected}")
        else:
            lines.append("Expected: observed")
        if scenario.note:
            lines.append(f"Note: {scenario.note}")

        for profile in profiles:
            result = results[scenario.name][profile.name]
            lines.append("")
            lines.append(f"#### {profile.name}")
            lines.append(
                "- Result: "
                f"winner={result.winner or 'none'} "
                f"status={result.expected_status} "
                f"score={_fmt_float(result.score)} "
                f"gap={_fmt_float(result.gap)}"
            )
            lines.append(f"- Top 3: {_format_top_rankings(result)}")
            lines.append(f"- Raw context: {_format_vector(result.match.raw_context_vector)}")
            lines.append(f"- Resolved context: {_format_vector(result.match.resolved_context_vector)}")
            if result.match.fallback_expansions:
                lines.append(
                    f"- Fallback expansions: {_format_nested_vector(result.match.fallback_expansions)}"
                )
            lines.append("- Policy contributions:")
            for evaluation in result.match.policy_evaluations:
                lines.append(
                    "  - "
                    f"{evaluation.policy_id}: "
                    f"active={evaluation.active} "
                    f"weight={_fmt_float(evaluation.weight)} "
                    f"salience={_fmt_float(evaluation.salience)} "
                    f"intensity={_fmt_float(evaluation.intensity)} "
                    f"magnitude={_fmt_float(evaluation.effective_magnitude)} "
                    f"dominant={evaluation.dominant_tag or 'none'} "
                    f"raw={_format_vector(evaluation.raw_contribution)} "
                    f"resolved={_format_vector(evaluation.resolved_contribution)}"
                )
        lines.append("")

    (run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def _average(values: Iterable[float]) -> float:
    collected = list(values)
    if not collected:
        return 0.0
    return sum(collected) / len(collected)


def _fmt_float(value: float) -> str:
    return f"{value:.6f}"


def _format_top_rankings(result: ScenarioProfileResult, limit: int = 3) -> str:
    if not result.rankings:
        return "none"
    return ", ".join(
        f"{row.playlist}({_fmt_float(row.score)})"
        for row in result.rankings[:limit]
    )


def _format_vector(vector: dict[str, float]) -> str:
    if not vector:
        return "{}"
    return "{" + ", ".join(
        f"{tag}: {_fmt_float(vector[tag])}"
        for tag in sorted(vector)
    ) + "}"


def _format_nested_vector(vector: dict[str, dict[str, float]]) -> str:
    if not vector:
        return "{}"
    return "{" + ", ".join(
        f"{tag}: {_format_vector(vector[tag])}"
        for tag in sorted(vector)
    ) + "}"


if __name__ == "__main__":
    main()
