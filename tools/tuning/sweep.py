from __future__ import annotations

from dataclasses import dataclass
from itertools import product
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
    pass_rate_expected: float
    avg_gap_expected: float
    churn_count_expected: int
    churn_rate_expected: float
    confident_fail_count_expected: int
    core_regression_count_expected: int
    avg_gap_all: float
    churn_rate_all: float


@dataclass(frozen=True)
class _ProfileSummary:
    expected_total: int
    pass_count: int
    fail_count: int
    pass_rate_expected: float
    avg_gap_expected: float
    avg_gap_all: float
    confident_fail_count_expected: int


@dataclass(frozen=True)
class SweepRow:
    profile: str
    gamma_playlist: float
    gamma_context: float
    expected_total: int
    pass_count: int
    fail_count: int
    pass_rate_expected: float
    avg_gap_expected: float
    churn_count_expected: int
    churn_rate_expected: float
    confident_fail_count_expected: int
    core_regression_count_expected: int
    avg_gap_all: float
    churn_count_all: int
    churn_rate_all: float


@dataclass(frozen=True)
class SweepReport:
    gamma_playlist: tuple[float, ...]
    gamma_context: tuple[float, ...]
    baseline: SweepBaseline
    rows: tuple[SweepRow, ...]

    @property
    def profile_count(self) -> int:
        return len(self.rows)


def evaluate_parameter_sweep(
    config: SchedulerConfig,
    scenarios: Iterable[Scenario],
    *,
    gamma_playlist: Sequence[float] = DEFAULT_GAMMA_PLAYLIST,
    gamma_context: Sequence[float] = DEFAULT_GAMMA_CONTEXT,
    confident_failure_gap: float = 0.15,
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
    baseline_summary = _summarize_results(
        scenario_list,
        baseline_results,
        confident_failure_gap=confident_failure_gap,
    )
    baseline = SweepBaseline(
        profile=baseline_profile.name,
        expected_total=baseline_summary.expected_total,
        pass_count=baseline_summary.pass_count,
        fail_count=baseline_summary.fail_count,
        pass_rate_expected=baseline_summary.pass_rate_expected,
        avg_gap_expected=baseline_summary.avg_gap_expected,
        churn_count_expected=0,
        churn_rate_expected=0.0,
        confident_fail_count_expected=baseline_summary.confident_fail_count_expected,
        core_regression_count_expected=0,
        avg_gap_all=baseline_summary.avg_gap_all,
        churn_rate_all=0.0,
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
        summary = _summarize_results(
            scenario_list,
            results,
            confident_failure_gap=confident_failure_gap,
        )
        churn_count_expected = sum(
            1
            for scenario, baseline_result, result in zip(scenario_list, baseline_results, results)
            if scenario.expected is not None and baseline_result.winner != result.winner
        )
        churn_count_all = sum(
            1
            for baseline_result, result in zip(baseline_results, results)
            if baseline_result.winner != result.winner
        )
        core_regression_count_expected = sum(
            1
            for scenario, baseline_result, result in zip(scenario_list, baseline_results, results)
            if (
                scenario.category == "core"
                and baseline_result.expected_status == "pass"
                and result.expected_status != "pass"
            )
        )
        rows.append(
            SweepRow(
                profile=profile.name,
                gamma_playlist=profile.gamma_playlist,
                gamma_context=profile.gamma_context,
                expected_total=baseline.expected_total,
                pass_count=summary.pass_count,
                fail_count=summary.fail_count,
                pass_rate_expected=summary.pass_rate_expected,
                avg_gap_expected=summary.avg_gap_expected,
                churn_count_expected=churn_count_expected,
                churn_rate_expected=_pass_rate(churn_count_expected, baseline.expected_total),
                confident_fail_count_expected=summary.confident_fail_count_expected,
                core_regression_count_expected=core_regression_count_expected,
                avg_gap_all=summary.avg_gap_all,
                churn_count_all=churn_count_all,
                churn_rate_all=(churn_count_all / len(scenario_list)) if scenario_list else 0.0,
            )
        )

    return SweepReport(
        gamma_playlist=gamma_playlist_values,
        gamma_context=gamma_context_values,
        baseline=baseline,
        rows=tuple(rows),
    )


def sorted_sweep_rows(rows: Iterable[SweepRow]) -> list[SweepRow]:
    return sorted(
        rows,
        key=lambda row: (
            row.core_regression_count_expected,
            -row.pass_rate_expected,
            row.confident_fail_count_expected,
            row.churn_rate_expected,
            -row.avg_gap_expected,
            row.profile,
        ),
    )


def _expected_total(scenarios: list[Scenario]) -> int:
    return sum(1 for scenario in scenarios if scenario.expected is not None)


def _summarize_results(
    scenarios: list[Scenario],
    results: list[ScenarioProfileResult],
    *,
    confident_failure_gap: float,
) -> _ProfileSummary:
    expected_total = _expected_total(scenarios)
    pass_count, fail_count = _expected_counts(scenarios, results)
    expected_results = [
        result
        for scenario, result in zip(scenarios, results)
        if scenario.expected is not None
    ]
    return _ProfileSummary(
        expected_total=expected_total,
        pass_count=pass_count,
        fail_count=fail_count,
        pass_rate_expected=_pass_rate(pass_count, expected_total),
        avg_gap_expected=_average(result.gap for result in expected_results),
        avg_gap_all=_average(result.gap for result in results),
        confident_fail_count_expected=sum(
            1
            for result in expected_results
            if result.expected_status == "fail" and result.gap >= confident_failure_gap
        ),
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
