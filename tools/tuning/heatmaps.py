from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from tools.tuning.models import (
    ActivitySignal,
    MatchProfile,
    Scenario,
    chill,
    evaluate_scenario,
    focus,
    weather,
)
from utils.runtime_config import SchedulerConfig

HeatmapMode = Literal["wx-hour", "act-hour", "wx-act", "hour-doy"]
HeatmapType = Literal["winner", "margin"]
AxisName = Literal["weather", "hour", "activity", "day_of_year"]

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
DEFAULT_VIEW_MODES: tuple[HeatmapMode, ...] = (
    "wx-hour",
    "act-hour",
    "wx-act",
    "hour-doy",
)
DEFAULT_MARGIN_MAX = 0.35
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
    x_axis: HeatmapAxis
    y_axis: HeatmapAxis
    fixed: dict[str, object]
    cells: tuple[tuple[HeatmapCell, ...], ...]


@dataclass(frozen=True)
class HeatmapFigure:
    path: str
    profile: str
    mode: HeatmapMode
    type: HeatmapType

    def to_manifest(self) -> dict[str, str]:
        return {
            "path": self.path,
            "profile": self.profile,
            "mode": self.mode,
            "type": self.type,
        }


class HeatmapRenderDependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class _ViewSpec:
    mode: HeatmapMode
    x_axis: AxisName
    y_axis: AxisName
    fixed: dict[str, object]


_VIEW_SPECS: dict[HeatmapMode, _ViewSpec] = {
    "wx-hour": _ViewSpec(
        mode="wx-hour",
        x_axis="hour",
        y_axis="weather",
        fixed={"activity": None, "day_of_year": 172},
    ),
    "act-hour": _ViewSpec(
        mode="act-hour",
        x_axis="hour",
        y_axis="activity",
        fixed={"weather": "clear", "day_of_year": 172},
    ),
    "wx-act": _ViewSpec(
        mode="wx-act",
        x_axis="activity",
        y_axis="weather",
        fixed={"hour": 14.0, "day_of_year": 172},
    ),
    "hour-doy": _ViewSpec(
        mode="hour-doy",
        x_axis="hour",
        y_axis="day_of_year",
        fixed={"activity": None, "weather": "clear"},
    ),
}


def activity_from_axis(value: float) -> ActivitySignal | None:
    if abs(value) <= _ACTIVITY_IDLE_EPSILON:
        return None
    if value < 0:
        return chill(abs(value))
    return focus(value)


def build_heatmap_grid(
    config: SchedulerConfig,
    profile: MatchProfile,
    mode: HeatmapMode,
    *,
    sampling: HeatmapSampling = HeatmapSampling(),
    fixed: dict[str, object] | None = None,
) -> HeatmapGrid:
    """Evaluate one heatmap grid against the real matcher pipeline.

    Raises:
        ValueError: If `mode` is unknown or a fixed/axis value cannot be
            converted into a valid tuning scenario.
    """
    spec = _view_spec(mode, fixed)
    x_axis = HeatmapAxis(spec.x_axis, _axis_values(spec.x_axis, sampling))
    y_axis = HeatmapAxis(spec.y_axis, _axis_values(spec.y_axis, sampling))
    rows: list[tuple[HeatmapCell, ...]] = []

    for y_value in y_axis.values:
        row: list[HeatmapCell] = []
        for x_value in x_axis.values:
            scenario = _scenario_for_point(spec, x_axis.name, x_value, y_axis.name, y_value)
            result = evaluate_scenario(config, scenario, profile)
            row.append(HeatmapCell(winner=result.winner, score=result.score, gap=result.gap))
        rows.append(tuple(row))

    return HeatmapGrid(
        mode=mode,
        profile=profile,
        x_axis=x_axis,
        y_axis=y_axis,
        fixed=dict(spec.fixed),
        cells=tuple(rows),
    )


def generate_default_heatmaps(
    config: SchedulerConfig,
    profiles: Sequence[MatchProfile],
    figures_dir: Path,
    *,
    sampling: HeatmapSampling = HeatmapSampling(),
    modes: Sequence[HeatmapMode] = DEFAULT_VIEW_MODES,
) -> list[HeatmapFigure]:
    """Render the default winner and margin heatmaps for all profiles.

    Raises:
        HeatmapRenderDependencyError: If matplotlib or numpy is not installed.
        ValueError: If a requested mode cannot be evaluated or rendered.
    """
    figures_dir.mkdir(parents=True, exist_ok=True)
    figures: list[HeatmapFigure] = []
    for profile in profiles:
        for mode in modes:
            grid = build_heatmap_grid(config, profile, mode, sampling=sampling)
            profile_slug = _slug(profile.name)
            for heatmap_type in ("winner", "margin"):
                file_name = f"{profile_slug}-{mode}-{heatmap_type}.png"
                output_path = figures_dir / file_name
                render_heatmap(grid, config, output_path, heatmap_type)
                figures.append(
                    HeatmapFigure(
                        path=f"figures/{file_name}",
                        profile=profile.name,
                        mode=mode,
                        type=heatmap_type,
                    )
                )
    return figures

def render_heatmap(
    grid: HeatmapGrid,
    config: SchedulerConfig,
    output_path: Path,
    heatmap_type: HeatmapType,
    *,
    margin_max: float = DEFAULT_MARGIN_MAX,
) -> None:
    """Render a single heatmap PNG.

    Raises:
        HeatmapRenderDependencyError: If matplotlib or numpy is not installed.
        ValueError: If `heatmap_type` is unknown.
    """
    import matplotlib.colors as mpl_colors
    import matplotlib.patches as patches
    import matplotlib.pyplot as plt
    import numpy as np
    fig, ax = plt.subplots(figsize=_figure_size(grid))
    try:
        if heatmap_type == "winner":
            _draw_winner_map(ax, grid, config, np, mpl_colors)
            _add_winner_legend(fig, config, patches)
        elif heatmap_type == "margin":
            mesh = _draw_margin_map(ax, grid, np, margin_max)
            colorbar = fig.colorbar(mesh, ax=ax, fraction=0.035, pad=0.02)
            colorbar.set_label("Winner margin")
        else:
            raise ValueError(f"unknown heatmap type: {heatmap_type}")

        _style_axes(ax, grid)
        ax.set_title(_title(grid, heatmap_type), fontsize=12, pad=10)
        fig.tight_layout()
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
    finally:
        plt.close(fig)


def _view_spec(mode: HeatmapMode, fixed: dict[str, object] | None) -> _ViewSpec:
    try:
        base = _VIEW_SPECS[mode]
    except KeyError as exc:
        raise ValueError(f"unknown heatmap mode: {mode}") from exc
    merged = dict(base.fixed)
    if fixed:
        merged.update(fixed)
    return _ViewSpec(mode=base.mode, x_axis=base.x_axis, y_axis=base.y_axis, fixed=merged)


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
    spec: _ViewSpec,
    x_name: AxisName,
    x_value: float | int | str | None,
    y_name: AxisName,
    y_value: float | int | str | None,
) -> Scenario:
    values = dict(spec.fixed)
    values[x_name] = x_value
    values[y_name] = y_value
    activity_value = values.get("activity")
    activity = (
        activity_value
        if isinstance(activity_value, ActivitySignal) or activity_value is None
        else activity_from_axis(float(activity_value))
    )
    weather_value = values.get("weather")
    weather_name = None if weather_value is None else str(weather_value)
    hour = float(values["hour"])
    day_of_year = int(values["day_of_year"])
    return Scenario(
        name=(
            f"heatmap {spec.mode} "
            f"{x_name}={_value_label(x_value)} {y_name}={_value_label(y_value)}"
        ),
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
        [
            [index_by_playlist.get(cell.winner, 0) for cell in row]
            for row in grid.cells
        ],
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


def _draw_margin_map(ax, grid: HeatmapGrid, np, margin_max: float):
    data = np.array(
        [
            [min(max(cell.gap, 0.0), margin_max) for cell in row]
            for row in grid.cells
        ],
        dtype=float,
    )
    return ax.pcolormesh(
        _axis_edges(grid.x_axis, np),
        _axis_edges(grid.y_axis, np),
        data,
        cmap="YlOrRd",
        vmin=0.0,
        vmax=margin_max,
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
        labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
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
    handles = [
        patches.Patch(facecolor=playlist.color, label=name)
        for name, playlist in config.playlists.items()
    ]
    handles.insert(0, patches.Patch(facecolor="#111827", label="no winner"))
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=min(5, len(handles)),
        frameon=True,
        fontsize=8,
        title="Playlist",
    )


def _title(grid: HeatmapGrid, heatmap_type: HeatmapType) -> str:
    fixed = ", ".join(
        f"{name}={_value_label(value)}"
        for name, value in sorted(grid.fixed.items())
    )
    label = "Winner map" if heatmap_type == "winner" else "Margin map"
    return f"{label} | profile={grid.profile.name} | mode={grid.mode} | fixed: {fixed}"


def _figure_size(grid: HeatmapGrid) -> tuple[float, float]:
    if grid.mode == "hour-doy":
        return (12.0, 7.0)
    if grid.mode == "act-hour":
        return (12.0, 6.0)
    return (10.0, 5.6)


def _value_label(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-_.")
    return slug or "profile"