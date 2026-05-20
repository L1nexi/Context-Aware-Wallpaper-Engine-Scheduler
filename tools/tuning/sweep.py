from __future__ import annotations

import csv
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Iterable, Sequence

from tools.tuning.models import (
    MatchProfile,
    Scenario,
    ScenarioProfileResult,
    evaluate_scenario,
)
from utils.runtime_config import SchedulerConfig

DEFAULT_GAMMA_PLAYLIST: tuple[float, ...] = (0.8, 0.9, 1.0, 1.1, 1.2, 1.3)
DEFAULT_GAMMA_CONTEXT: tuple[float, ...] = (0.8, 0.9, 1.0, 1.1, 1.2, 1.3)


@dataclass(frozen=True)
class SweepBaseline:
    profile: str
    expected_total: int
    pass_count: int
    fail_count: int
    pass_rate: float
    avg_gap: float


@dataclass(frozen=True)
class _ProfileSummary:
    expected_total: int
    pass_count: int
    fail_count: int
    pass_rate: float
    avg_gap: float


@dataclass(frozen=True)
class SweepRow:
    profile: str
    gamma_playlist: float
    gamma_context: float
    expected_total: int
    pass_count: int
    fail_count: int
    pass_rate: float
    avg_gap: float
    churn_count: int
    churn_rate: float


@dataclass(frozen=True)
class SweepReport:
    gamma_playlist: tuple[float, ...]
    gamma_context: tuple[float, ...]
    baseline: SweepBaseline
    rows: tuple[SweepRow, ...]

    @property
    def profile_count(self) -> int:
        return len(self.rows)

    def to_manifest(self) -> dict[str, object]:
        return {
            "path": "sweep.csv",
            "profile_count": self.profile_count,
            "gamma_playlist": list(self.gamma_playlist),
            "gamma_context": list(self.gamma_context),
        }


def evaluate_parameter_sweep(
    config: SchedulerConfig,
    scenarios: Iterable[Scenario],
    *,
    gamma_playlist: Sequence[float] = DEFAULT_GAMMA_PLAYLIST,
    gamma_context: Sequence[float] = DEFAULT_GAMMA_CONTEXT,
) -> SweepReport:
    """Evaluate the fixed gamma grid against the real matcher pipeline.

    Raises:
        ValueError: If a gamma value cannot build a valid `MatchProfile`.
    """
    scenario_list = list(scenarios)
    gamma_playlist_values = tuple(gamma_playlist)
    gamma_context_values = tuple(gamma_context)
    baseline_profile = MatchProfile("current")
    baseline_results = [
        evaluate_scenario(config, scenario, baseline_profile)
        for scenario in scenario_list
    ]
    baseline_summary = _summarize_results(scenario_list, baseline_results)
    baseline = SweepBaseline(
        profile=baseline_profile.name,
        expected_total=baseline_summary.expected_total,
        pass_count=baseline_summary.pass_count,
        fail_count=baseline_summary.fail_count,
        pass_rate=baseline_summary.pass_rate,
        avg_gap=baseline_summary.avg_gap,
    )

    rows: list[SweepRow] = []
    for gamma_playlist_value, gamma_context_value in product(
        gamma_playlist_values,
        gamma_context_values,
    ):
        profile = MatchProfile(
            name=f"gp{gamma_playlist_value:g}-gc{gamma_context_value:g}",
            gamma_playlist=gamma_playlist_value,
            gamma_context=gamma_context_value,
        )
        results = [
            evaluate_scenario(config, scenario, profile)
            for scenario in scenario_list
        ]
        summary = _summarize_results(scenario_list, results)
        churn_count = sum(
            1
            for baseline_result, result in zip(baseline_results, results)
            if baseline_result.winner != result.winner
        )
        rows.append(
            SweepRow(
                profile=profile.name,
                gamma_playlist=profile.gamma_playlist,
                gamma_context=profile.gamma_context,
                expected_total=baseline.expected_total,
                pass_count=summary.pass_count,
                fail_count=summary.fail_count,
                pass_rate=summary.pass_rate,
                avg_gap=summary.avg_gap,
                churn_count=churn_count,
                churn_rate=(churn_count / len(scenario_list)) if scenario_list else 0.0,
            )
        )

    return SweepReport(
        gamma_playlist=gamma_playlist_values,
        gamma_context=gamma_context_values,
        baseline=baseline,
        rows=tuple(rows),
    )


def write_sweep_csv(path: Path, report: SweepReport) -> None:
    """Write parameter sweep metrics.

    Raises:
        OSError: If the destination cannot be written.
    """
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "profile",
                "gamma_playlist",
                "gamma_context",
                "expected_total",
                "pass_count",
                "fail_count",
                "pass_rate",
                "avg_gap",
                "churn_count",
                "churn_rate",
            ],
        )
        writer.writeheader()
        for row in report.rows:
            writer.writerow(
                {
                    "profile": row.profile,
                    "gamma_playlist": _fmt_float(row.gamma_playlist),
                    "gamma_context": _fmt_float(row.gamma_context),
                    "expected_total": row.expected_total,
                    "pass_count": row.pass_count,
                    "fail_count": row.fail_count,
                    "pass_rate": _fmt_float(row.pass_rate),
                    "avg_gap": _fmt_float(row.avg_gap),
                    "churn_count": row.churn_count,
                    "churn_rate": _fmt_float(row.churn_rate),
                }
            )


def sorted_sweep_rows(rows: Iterable[SweepRow]) -> list[SweepRow]:
    return sorted(
        rows,
        key=lambda row: (-row.pass_rate, -row.avg_gap, row.churn_rate, row.profile),
    )


def _expected_total(scenarios: list[Scenario]) -> int:
    return sum(1 for scenario in scenarios if scenario.expected is not None)


def _summarize_results(
    scenarios: list[Scenario],
    results: list[ScenarioProfileResult],
) -> _ProfileSummary:
    expected_total = _expected_total(scenarios)
    pass_count, fail_count = _expected_counts(scenarios, results)
    return _ProfileSummary(
        expected_total=expected_total,
        pass_count=pass_count,
        fail_count=fail_count,
        pass_rate=_pass_rate(pass_count, expected_total),
        avg_gap=_average(result.gap for result in results),
    )


def _expected_counts(
    scenarios: list[Scenario],
    results: list[ScenarioProfileResult],
) -> tuple[int, int]:
    pass_count = 0
    fail_count = 0
    for scenario, result in zip(scenarios, results):
        if scenario.expected is None:
            continue
        if result.expected_status == "pass":
            pass_count += 1
        elif result.expected_status == "fail":
            fail_count += 1
    return pass_count, fail_count


def _pass_rate(pass_count: int, expected_total: int) -> float:
    if expected_total == 0:
        return 0.0
    return pass_count / expected_total


def _average(values: Iterable[float]) -> float:
    collected = list(values)
    if not collected:
        return 0.0
    return sum(collected) / len(collected)


def _fmt_float(value: float) -> str:
    return f"{value:.6f}"
