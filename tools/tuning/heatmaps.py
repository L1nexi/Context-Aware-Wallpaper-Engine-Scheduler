from __future__ import annotations

import math
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from configurations.runtime_models import SchedulerConfig
from core.models.context import Context
from core.models.playlist import Playlists
from core.policies import Policy, SeasonPolicy, TimePolicy, WeatherPolicy
from core.runtime.tag_resolver import resolve_raw_tags
from tools.tuning.models import (
    ActivitySignal,
    DirectActivityPolicy,
    MatchProfile,
    Scenario,
    build_context,
    chill,
    focus,
    normalize_pow,
    weather,
)

type HeatmapMode = Literal["wx-hour", "act-hour", "wx-act", "wx-doy", "act-doy", "hour-doy"]
type HeatmapType = Literal["winner"]
type AxisName = Literal["weather", "hour", "activity", "day_of_year"]

WEATHER_HEATMAP_PRESETS: tuple[str | None, ...] = (
    None,
    "clear",
    "overcast",
    "drizzle",
    "mod_rain",
    "heavy_rain",
    "light_snow",
    "heavy_snow",
    "storm",
    "heavy_storm",
    "fog",
)
_ACTIVITY_IDLE_EPSILON = 1e-9


@dataclass(frozen=True)
class HeatmapSampling:
    hour_step: float = 0.5
    day_step: int = 4
    activity_step: float = 0.05

    def __post_init__(self) -> None:
        if self.hour_step <= 0 or self.hour_step > 24:
            raise ValueError("hour_step must be in (0, 24]")
        if self.day_step <= 0 or self.day_step > 365:
            raise ValueError("day_step must be in [1, 365]")
        if self.activity_step <= 0 or self.activity_step > 2:
            raise ValueError("activity_step must be in (0, 2]")


@dataclass(frozen=True)
class HeatmapCell:
    winner: str | None
    score: float
    gap: float


@dataclass(frozen=True)
class HeatmapAxis:
    name: AxisName
    values: tuple[float | int | str | None, ...]

    @property
    def label(self) -> str:
        if self.name == "day_of_year":
            return "Day of year"
        return self.name.replace("_", " ").title()


@dataclass(frozen=True)
class HeatmapGrid:
    mode: HeatmapMode
    profile: MatchProfile
    case_name: str
    x_axis: HeatmapAxis
    y_axis: HeatmapAxis
    fixed: dict[str, object]
    cells: tuple[tuple[HeatmapCell, ...], ...]


@dataclass(frozen=True)
class HeatmapFigure:
    path: str
    profile: str
    mode: HeatmapMode
    case_name: str
    type: HeatmapType


@dataclass(frozen=True)
class ViewSpec:
    mode: HeatmapMode
    x_axis: AxisName
    y_axis: AxisName
    fixed: dict[str, object]


@dataclass(frozen=True)
class HeatmapCase:
    name: str
    mode: HeatmapMode
    fixed: dict[str, object]


_MODE_TO_AXES: dict[HeatmapMode, tuple[AxisName, AxisName]] = {
    "wx-hour": ("hour", "weather"),
    "act-hour": ("hour", "activity"),
    "wx-act": ("activity", "weather"),
    "wx-doy": ("day_of_year", "weather"),
    "act-doy": ("day_of_year", "activity"),
    "hour-doy": ("hour", "day_of_year"),
}


DEFAULT_HEATMAP_CASES: tuple[HeatmapCase, ...] = (
    HeatmapCase("wxhr-idle-haru", "wx-hour", {"activity": None, "day_of_year": 80}),
    HeatmapCase("wxhr-idle-natsu", "wx-hour", {"activity": None, "day_of_year": 172}),
    HeatmapCase("wxhr-idle-aki", "wx-hour", {"activity": None, "day_of_year": 265}),
    HeatmapCase("wxhr-idle-fuyu", "wx-hour", {"activity": None, "day_of_year": 355}),
    HeatmapCase("wxhr-idle-fuyu-haru", "wx-hour", {"activity": None, "day_of_year": 35}),
    HeatmapCase("wxhr-idle-haru-natsu", "wx-hour", {"activity": None, "day_of_year": 126}),
    HeatmapCase("wxhr-idle-natsu-aki", "wx-hour", {"activity": None, "day_of_year": 218}),
    HeatmapCase("wxhr-idle-aki-fuyu", "wx-hour", {"activity": None, "day_of_year": 310}),
    HeatmapCase("wxhr-focus-haru", "wx-hour", {"activity": "#focus", "day_of_year": 80}),
    HeatmapCase("wxhr-focus-natsu", "wx-hour", {"activity": "#focus", "day_of_year": 172}),
    HeatmapCase("wxhr-chill-natsu", "wx-hour", {"activity": "#chill", "day_of_year": 172}),
    HeatmapCase("wxhr-chill-fuyu", "wx-hour", {"activity": "#chill", "day_of_year": 355}),
    HeatmapCase("acthr-none-haru", "act-hour", {"weather": None, "day_of_year": 80}),
    HeatmapCase("acthr-none-natsu-aki", "act-hour", {"weather": None, "day_of_year": 218}),
    HeatmapCase("acthr-none-fuyu", "act-hour", {"weather": None, "day_of_year": 355}),
    HeatmapCase("acthr-clear-haru", "act-hour", {"weather": "clear", "day_of_year": 80}),
    HeatmapCase("acthr-clear-haru-natsu", "act-hour", {"weather": "clear", "day_of_year": 126}),
    HeatmapCase("acthr-clear-natsu", "act-hour", {"weather": "clear", "day_of_year": 172}),
    HeatmapCase("acthr-clear-fuyu", "act-hour", {"weather": "clear", "day_of_year": 355}),
    HeatmapCase("acthr-rain-natsu", "act-hour", {"weather": "mod_rain", "day_of_year": 172}),
    HeatmapCase("acthr-rain-aki-fuyu", "act-hour", {"weather": "mod_rain", "day_of_year": 310}),
    HeatmapCase("acthr-storm-fuyu-haru", "act-hour", {"weather": "storm", "day_of_year": 35}),
    HeatmapCase("acthr-storm-haru", "act-hour", {"weather": "storm", "day_of_year": 80}),
    HeatmapCase("acthr-storm-fuyu", "act-hour", {"weather": "storm", "day_of_year": 355}),
    HeatmapCase("wxdoy-idle-06", "wx-doy", {"activity": None, "hour": 6.0}),
    HeatmapCase("wxdoy-idle-10", "wx-doy", {"activity": None, "hour": 10.0}),
    HeatmapCase("wxdoy-idle-14", "wx-doy", {"activity": None, "hour": 14.0}),
    HeatmapCase("wxdoy-idle-18", "wx-doy", {"activity": None, "hour": 18.0}),
    HeatmapCase("wxdoy-idle-22", "wx-doy", {"activity": None, "hour": 22.0}),
    HeatmapCase("wxdoy-focus-10", "wx-doy", {"activity": "#focus", "hour": 10.0}),
    HeatmapCase("wxdoy-focus-22", "wx-doy", {"activity": "#focus", "hour": 22.0}),
    HeatmapCase("wxdoy-chill-14", "wx-doy", {"activity": "#chill", "hour": 14.0}),
    HeatmapCase("wxdoy-chill-20", "wx-doy", {"activity": "#chill", "hour": 20.0}),
    HeatmapCase("actdoy-none-10", "act-doy", {"weather": None, "hour": 10.0}),
    HeatmapCase("actdoy-none-22", "act-doy", {"weather": None, "hour": 22.0}),
    HeatmapCase("actdoy-clear-10", "act-doy", {"weather": "clear", "hour": 10.0}),
    HeatmapCase("actdoy-clear-14", "act-doy", {"weather": "clear", "hour": 14.0}),
    HeatmapCase("actdoy-clear-22", "act-doy", {"weather": "clear", "hour": 22.0}),
    HeatmapCase("actdoy-rain-10", "act-doy", {"weather": "mod_rain", "hour": 10.0}),
    HeatmapCase("actdoy-rain-22", "act-doy", {"weather": "mod_rain", "hour": 22.0}),
    HeatmapCase("actdoy-storm-14", "act-doy", {"weather": "storm", "hour": 14.0}),
    HeatmapCase("actdoy-storm-22", "act-doy", {"weather": "storm", "hour": 22.0}),
    HeatmapCase("wxact-haru-08", "wx-act", {"hour": 8.0, "day_of_year": 80}),
    HeatmapCase("wxact-haru-20", "wx-act", {"hour": 20.0, "day_of_year": 80}),
    HeatmapCase("wxact-natsu-14", "wx-act", {"hour": 14.0, "day_of_year": 172}),
    HeatmapCase("wxact-natsu-23", "wx-act", {"hour": 23.0, "day_of_year": 172}),
    HeatmapCase("wxact-aki-14", "wx-act", {"hour": 14.0, "day_of_year": 265}),
    HeatmapCase("wxact-aki-23", "wx-act", {"hour": 23.0, "day_of_year": 265}),
    HeatmapCase("wxact-fuyu-20", "wx-act", {"hour": 20.0, "day_of_year": 355}),
    HeatmapCase("wxact-fuyu-23", "wx-act", {"hour": 23.0, "day_of_year": 355}),
    HeatmapCase("wxact-fuyu-haru-14", "wx-act", {"hour": 14.0, "day_of_year": 35}),
    HeatmapCase("wxact-haru-natsu-14", "wx-act", {"hour": 14.0, "day_of_year": 126}),
    HeatmapCase("wxact-natsu-aki-14", "wx-act", {"hour": 14.0, "day_of_year": 218}),
    HeatmapCase("wxact-aki-fuyu-14", "wx-act", {"hour": 14.0, "day_of_year": 310}),
    HeatmapCase("hrdoy-idle-none", "hour-doy", {"activity": None, "weather": None}),
    HeatmapCase("hrdoy-idle-clear", "hour-doy", {"activity": None, "weather": "clear"}),
    HeatmapCase("hrdoy-idle-drizzle", "hour-doy", {"activity": None, "weather": "drizzle"}),
    HeatmapCase("hrdoy-idle-snow", "hour-doy", {"activity": None, "weather": "heavy_snow"}),
    HeatmapCase("hrdoy-focus-clear", "hour-doy", {"activity": "#focus", "weather": "clear"}),
    HeatmapCase("hrdoy-chill-clear", "hour-doy", {"activity": "#chill", "weather": "clear"}),
    HeatmapCase("hrdoy-focus-cloud", "hour-doy", {"activity": "#focus", "weather": "overcast"}),
    HeatmapCase("hrdoy-focus-rain", "hour-doy", {"activity": "#focus", "weather": "mod_rain"}),
    HeatmapCase("hrdoy-chill-rain", "hour-doy", {"activity": "#chill", "weather": "mod_rain"}),
)


def activity_from_axis(value: float) -> ActivitySignal | None:
    if abs(value) <= _ACTIVITY_IDLE_EPSILON:
        return None
    if value < 0:
        return chill(abs(value))
    return focus(value)


class BatchEvaluator:
    def __init__(self, config: SchedulerConfig) -> None:
        self.config = config
        self._tag_specs = config.tags

        all_tags: set[str] = set()
        for playlist in config.playlists.values():
            all_tags.update(playlist.tags.keys())
        self._known_tags = all_tags
        self._tag_to_index = {tag: i for i, tag in enumerate(sorted(all_tags))}
        self._dim = len(all_tags)

        Playlists.configure(config.playlists)

    def build_profile_playlist_vectors(
        self,
        profiles: Sequence[MatchProfile],
    ) -> dict[str, list[tuple[str, list[float]]]]:
        result: dict[str, list[tuple[str, list[float]]]] = {}
        for profile in profiles:
            normalized: list[tuple[str, list[float]]] = []
            for name, playlist in self.config.playlists.items():
                tags = playlist.tags
                powered = {t: v**profile.gamma_playlist for t, v in tags.items() if v > 0}
                norm = math.sqrt(sum(v * v for v in powered.values()))
                if norm >= 1e-6:
                    vec = [0.0] * self._dim
                    for t, v in powered.items():
                        if t in self._tag_to_index:
                            vec[self._tag_to_index[t]] = v / norm
                    normalized.append((name, vec))
            result[profile.name] = normalized
        return result

    def resolve_context(
        self,
        policies: list[Policy],
        context: Context,
    ) -> dict[str, float]:
        resolved: dict[str, float] = {}
        for policy in policies:
            evaluation = policy.evaluate(context)
            policy_resolved, _ = resolve_raw_tags(
                evaluation.raw_contribution,
                known_tags=self._known_tags,
                tag_specs=self._tag_specs,
            )
            for tag, weight in policy_resolved.items():
                resolved[tag] = resolved.get(tag, 0.0) + weight
        return resolved

    def rank_with_gamma(
        self,
        resolved_context_vector: dict[str, float],
        gamma_context: float,
        profile_playlist_vectors: dict[str, list[tuple[str, list[float]]]],
        profile_name: str,
    ) -> tuple[str | None, float, float]:
        context_dir = normalize_pow(resolved_context_vector, gamma_context)
        return self._rank_with_context_dir(context_dir, profile_playlist_vectors, profile_name)

    def _rank_with_context_dir(
        self,
        context_dir: dict[str, float],
        profile_playlist_vectors: dict[str, list[tuple[str, list[float]]]],
        profile_name: str,
    ) -> tuple[str | None, float, float]:
        if not context_dir:
            return None, 0.0, 0.0

        context_vec = [0.0] * self._dim
        for tag, weight in context_dir.items():
            if tag in self._tag_to_index:
                context_vec[self._tag_to_index[tag]] = weight

        scores: list[tuple[float, str]] = []
        for name, playlist_vec in profile_playlist_vectors[profile_name]:
            score = sum(a * b for a, b in zip(context_vec, playlist_vec))
            scores.append((score, name))
        scores.sort(reverse=True)

        if not scores or scores[0][0] <= 0.001:
            return None, 0.0, 0.0
        winner = scores[0][1]
        top_score = scores[0][0]
        gap = top_score - scores[1][0] if len(scores) >= 2 else top_score
        return winner, top_score, gap

    def evaluate_grid(
        self,
        cases: Sequence[HeatmapCase],
        profiles: Sequence[MatchProfile],
        sampling: HeatmapSampling = HeatmapSampling(),
    ) -> dict[str, dict[str, HeatmapGrid]]:
        profile_pv = self.build_profile_playlist_vectors(profiles)
        static_policies: list[Policy] = [
            TimePolicy(self.config.policies.time),
            SeasonPolicy(self.config.policies.season),
            WeatherPolicy(self.config.policies.weather),
        ]
        result: dict[str, dict[str, HeatmapGrid]] = {}

        for case in cases:
            spec = _case2spec(case.mode, case.fixed)
            x_axis = HeatmapAxis(spec.x_axis, _axis_values(spec.x_axis, sampling))
            y_axis = HeatmapAxis(spec.y_axis, _axis_values(spec.y_axis, sampling))

            profile_cells: dict[str, list[tuple[HeatmapCell, ...]]] = {profile.name: [] for profile in profiles}

            for y_value in y_axis.values:
                profile_rows: dict[str, list[HeatmapCell]] = {profile.name: [] for profile in profiles}
                for x_value in x_axis.values:
                    scenario = _scenario_for_point(spec, x_axis.name, x_value, y_axis.name, y_value)
                    context = build_context(scenario)
                    activity_policy = DirectActivityPolicy(self.config.policies.activity, scenario.activity)
                    resolved = self.resolve_context([activity_policy, *static_policies], context)

                    for profile in profiles:
                        winner, score, gap = self.rank_with_gamma(
                            resolved,
                            profile.gamma_context,
                            profile_pv,
                            profile.name,
                        )
                        profile_rows[profile.name].append(HeatmapCell(winner, score, gap))

                for profile in profiles:
                    profile_cells[profile.name].append(tuple(profile_rows[profile.name]))

            case_grids: dict[str, HeatmapGrid] = {}
            for profile in profiles:
                grid = HeatmapGrid(
                    mode=case.mode,
                    profile=profile,
                    case_name=case.name,
                    x_axis=x_axis,
                    y_axis=y_axis,
                    fixed=dict(spec.fixed),
                    cells=tuple(profile_cells[profile.name]),
                )
                case_grids[profile.name] = grid
            result[case.name] = case_grids

        return result


def build_heatmap_grids_batch(
    config: SchedulerConfig,
    cases: Sequence[HeatmapCase],
    profiles: Sequence[MatchProfile],
    *,
    sampling: HeatmapSampling = HeatmapSampling(),
) -> dict[str, dict[str, HeatmapGrid]]:
    """Build heatmap grids for all cases and profiles in one batch.

    Returns:
        Nested dict: ``result[case_name][profile_name] -> HeatmapGrid``.
    """
    evaluator = BatchEvaluator(config)
    return evaluator.evaluate_grid(cases, profiles, sampling)


def generate_default_heatmaps(
    config: SchedulerConfig,
    profiles: Sequence[MatchProfile],
    figures_dir: Path,
    *,
    sampling: HeatmapSampling = HeatmapSampling(),
    cases: Sequence[HeatmapCase] = DEFAULT_HEATMAP_CASES,
) -> list[HeatmapFigure]:
    """Render aggregated winner heatmaps grouped by mode.

    Produces one PNG per mode per profile (12 figures for 2 profiles x 6 modes).
    """
    figures_dir.mkdir(parents=True, exist_ok=True)

    all_grids = build_heatmap_grids_batch(config, list(cases), list(profiles), sampling=sampling)

    cases_by_mode: dict[HeatmapMode, list[HeatmapCase]] = {}
    for case in cases:
        cases_by_mode.setdefault(case.mode, []).append(case)

    ordered_modes: list[HeatmapMode] = []
    seen_modes: set[HeatmapMode] = set()
    for case in cases:
        if case.mode not in seen_modes:
            seen_modes.add(case.mode)
            ordered_modes.append(case.mode)

    figures: list[HeatmapFigure] = []
    for profile in profiles:
        for mode in ordered_modes:
            mode_cases = cases_by_mode[mode]
            grids = [all_grids[case.name][profile.name] for case in mode_cases]

            profile_slug = _profile_slug(profile)
            file_name = f"{profile_slug}-{_slug(mode)}.png"
            output_path = figures_dir / file_name

            _render_mode_figure(grids, config, output_path, mode)

            for case in mode_cases:
                figures.append(
                    HeatmapFigure(
                        path=f"heatmaps/{file_name}",
                        profile=profile.name,
                        mode=mode,
                        case_name=case.name,
                        type="winner",
                    )
                )

    return figures


def _render_mode_figure(
    grids: list[HeatmapGrid],
    config: SchedulerConfig,
    output_path: Path,
    mode: HeatmapMode,
) -> None:
    """Render an aggregated figure with multiple case subplots for one mode."""
    import matplotlib.colors as mpl_colors
    import matplotlib.patches as patches
    import matplotlib.pyplot as plt
    import numpy as np

    n_cases = len(grids)
    ncols, nrows = _subplot_layout(n_cases)
    fig_w, fig_h = _aggregated_figure_size(ncols, nrows, mode)

    fig, axes_array = plt.subplots(nrows, ncols, figsize=(fig_w, fig_h))
    axes_flat = [axes_array] if not hasattr(axes_array, "flat") else list(axes_array.flat)

    for idx, grid in enumerate(grids):
        ax = axes_flat[idx]
        _draw_winner_map(ax, grid, config, np, mpl_colors)
        _style_axes(ax, grid)
        fixed = ", ".join(f"{k}={_value_label(v)}" for k, v in sorted(grid.fixed.items()))
        ax.set_title(f"{grid.case_name}\n{fixed}", fontsize=8, pad=4)

    for idx in range(n_cases, len(axes_flat)):
        axes_flat[idx].set_visible(False)

    _add_winner_legend(fig, config, patches)
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _subplot_layout(n_cases: int) -> tuple[int, int]:
    ncols = 4 if n_cases > 9 else 3
    return ncols, math.ceil(n_cases / ncols)


def _aggregated_figure_size(ncols: int, nrows: int, mode: HeatmapMode) -> tuple[float, float]:
    cell_h = 5.5 if mode == "hour-doy" else 5.0
    return (ncols * 6.0, nrows * cell_h)


def _case2spec(mode: HeatmapMode, fixed: dict[str, object]) -> ViewSpec:
    try:
        axes = _MODE_TO_AXES[mode]
    except KeyError as exc:
        raise ValueError(f"unknown heatmap mode: {mode}") from exc
    return ViewSpec(mode, x_axis=axes[0], y_axis=axes[1], fixed=fixed)


def _axis_values(
    axis_name: AxisName,
    sampling: HeatmapSampling,
) -> tuple[float | int | str | None, ...]:
    if axis_name == "weather":
        return WEATHER_HEATMAP_PRESETS
    if axis_name == "hour":
        return tuple(_float_axis(0.0, 24.0 - sampling.hour_step, sampling.hour_step))
    if axis_name == "activity":
        return tuple(_float_axis(-1.0, 1.0, sampling.activity_step))
    if axis_name == "day_of_year":
        values = list(range(1, 366, sampling.day_step))
        if values[-1] != 365:
            values.append(365)
        return tuple(values)
    raise ValueError(f"unknown heatmap axis: {axis_name}")


def _float_axis(start: float, stop: float, step: float) -> list[float]:
    count = int(round((stop - start) / step))
    return [round(start + index * step, 10) for index in range(count + 1)]


def _scenario_for_point(
    spec: ViewSpec,
    x_name: AxisName,
    x_value: float | int | str | None,
    y_name: AxisName,
    y_value: float | int | str | None,
) -> Scenario:
    values = dict(spec.fixed)
    values[x_name] = x_value
    values[y_name] = y_value
    activity_value = values.get("activity")
    activity = _coerce_activity(activity_value)
    weather_value = values.get("weather")
    weather_name = None if weather_value is None else str(weather_value)
    hour = float(values["hour"])
    day_of_year = int(values["day_of_year"])
    return Scenario(
        name=(f"heatmap {spec.mode} {x_name}={_value_label(x_value)} {y_name}={_value_label(y_value)}"),
        hour=hour,
        day_of_year=day_of_year,
        weather=weather(weather_name),
        activity=activity,
        note="heatmap grid point",
    )


def _draw_winner_map(ax, grid: HeatmapGrid, config: SchedulerConfig, np, mpl_colors):
    playlists = list(config.playlists)
    index_by_playlist = {playlist: index + 1 for index, playlist in enumerate(playlists)}
    colors = ["#111827", *(config.playlists[name].color for name in playlists)]
    data = np.array(
        [[index_by_playlist.get(cell.winner, 0) for cell in row] for row in grid.cells],
        dtype=float,
    )
    cmap = mpl_colors.ListedColormap(colors)
    norm = mpl_colors.BoundaryNorm(np.arange(len(colors) + 1) - 0.5, len(colors))
    return ax.pcolormesh(
        _axis_edges(grid.x_axis, np),
        _axis_edges(grid.y_axis, np),
        data,
        cmap=cmap,
        norm=norm,
        shading="flat",
        rasterized=True,
    )


def _style_axes(ax, grid: HeatmapGrid) -> None:
    _style_single_axis(ax, "x", grid.x_axis)
    _style_single_axis(ax, "y", grid.y_axis)
    if grid.x_axis.name == "hour":
        for hour in (8, 14, 20, 23):
            ax.axvline(hour, color="white", linewidth=0.6, linestyle="--", alpha=0.45)
    if grid.y_axis.name == "hour":
        for hour in (8, 14, 20, 23):
            ax.axhline(hour, color="white", linewidth=0.6, linestyle="--", alpha=0.45)
    if grid.x_axis.name == "activity":
        ax.axvline(0, color="white", linewidth=0.8, linestyle="--", alpha=0.65)
    if grid.y_axis.name == "activity":
        ax.axhline(0, color="white", linewidth=0.8, linestyle="--", alpha=0.65)


def _style_single_axis(ax, orientation: Literal["x", "y"], axis: HeatmapAxis) -> None:
    values = axis.values
    setter_label = ax.set_xlabel if orientation == "x" else ax.set_ylabel
    setter_label(axis.label)
    if axis.name == "weather":
        ticks = [index + 0.5 for index in range(len(values))]
        labels = [_value_label(value) for value in values]
        if orientation == "x":
            ax.set_xticks(ticks)
            ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
        else:
            ax.set_yticks(ticks)
            ax.set_yticklabels(labels, fontsize=8)
            ax.invert_yaxis()
        return
    if axis.name == "hour":
        ticks = list(range(0, 25, 4))
        labels = [f"{hour:02d}:00" for hour in ticks]
        if orientation == "x":
            ax.set_xlim(0, 24)
            ax.set_xticks(ticks)
            ax.set_xticklabels(labels, fontsize=8)
        else:
            ax.set_ylim(0, 24)
            ax.set_yticks(ticks)
            ax.set_yticklabels(labels, fontsize=8)
        return
    if axis.name == "activity":
        ticks = [-1, -0.5, 0, 0.5, 1]
        labels = ["chill 1.0", "0.5", "idle", "0.5", "focus 1.0"]
        if orientation == "x":
            ax.set_xlim(-1, 1)
            ax.set_xticks(ticks)
            ax.set_xticklabels(labels, fontsize=8)
        else:
            ax.set_ylim(-1, 1)
            ax.set_yticks(ticks)
            ax.set_yticklabels(labels, fontsize=8)
        return
    if axis.name == "day_of_year":
        ticks = [15, 46, 74, 105, 135, 166, 196, 227, 258, 288, 319, 349]
        labels = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        if orientation == "x":
            ax.set_xlim(1, 365)
            ax.set_xticks(ticks)
            ax.set_xticklabels(labels, fontsize=8)
        else:
            ax.set_ylim(1, 365)
            ax.set_yticks(ticks)
            ax.set_yticklabels(labels, fontsize=8)
            ax.invert_yaxis()


def _axis_edges(axis: HeatmapAxis, np):
    values = axis.values
    if axis.name == "weather":
        return np.arange(len(values) + 1)
    numeric_values = [float(value) for value in values]
    if axis.name == "hour":
        step = numeric_values[1] - numeric_values[0] if len(numeric_values) > 1 else 1.0
        return np.append(np.array(numeric_values), numeric_values[-1] + step)
    if axis.name == "activity":
        return _midpoint_edges(numeric_values, np, -1.0, 1.0)
    if axis.name == "day_of_year":
        return _midpoint_edges(numeric_values, np, 1.0, 365.0)
    raise ValueError(f"unknown heatmap axis: {axis.name}")


def _midpoint_edges(values: list[float], np, lower: float, upper: float):
    if len(values) == 1:
        return np.array([lower, upper])
    mids = [(left + right) / 2 for left, right in zip(values, values[1:])]
    return np.array([lower, *mids, upper])


def _add_winner_legend(fig, config: SchedulerConfig, patches) -> None:
    handles = [patches.Patch(facecolor=playlist.color, label=name) for name, playlist in config.playlists.items()]
    handles.insert(0, patches.Patch(facecolor="#111827", label="no winner"))
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=min(5, len(handles)),
        frameon=True,
        fontsize=8,
        title="Playlist",
    )


def _value_label(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-_.")
    return slug or "profile"


def _profile_slug(profile: MatchProfile) -> str:
    if profile.name == "current":
        return "cur"
    return f"p{_compact_gamma(profile.gamma_playlist)}c{_compact_gamma(profile.gamma_context)}"


def _compact_gamma(value: float) -> str:
    return f"{round(value * 100):03d}"


def _coerce_activity(value: object) -> ActivitySignal | None:
    if isinstance(value, ActivitySignal) or value is None:
        return value
    if value == "#focus":
        return focus()
    if value == "#chill":
        return chill()
    return activity_from_axis(float(value))
