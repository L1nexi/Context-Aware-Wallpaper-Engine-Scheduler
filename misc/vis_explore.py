#!/usr/bin/env python3
"""
vis_explore.py — 多轴 playlist 决策空间探索器
==============================================

播放列表决策可抽象为四变量函数：

    f(activity, weather, hour, doy) → playlist_index

本脚本覆盖全部 6 种"固定二变动二"的组合:

  模式          X 轴          Y 轴         固定变量        语义
  ────────────────────────────────────────────────────────────────────
  hr-doy        hour          doy/month    act, wx         一年中每时刻的 playlist 全景 (12 面板)
  wx-hour       hour          weather      act, doy        天气如何随时段影响选择
  act-hour      hour          activity     wx, doy         用户活跃度随时段的影响
  wx-season     doy/month     weather      act, hour       天气在不同季节的效果差异
  act-season    doy/month     activity     wx, hour        活跃度在不同季节的效果差异
  wx-act        activity      weather      hour, doy       某时刻下天气 × 活跃度全交叉

其中：
  - weather  是分类轴 (10 个天气预设, 从 none → heavy_storm)
  - activity 是连续轴 (-1.0 = 完全 #chill → 0.0 = idle → +1.0 = 完全 #focus)

Usage:
  python misc/vis_explore.py wx-hour                        # 默认面板, 弹窗
  python misc/vis_explore.py act-hour --save misc/explore   # 保存 PNG
  python misc/vis_explore.py wx-act                         # 天气 × 活跃度
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError as exc:
    print(f"Missing dependency: {exc}")
    print("Install with:  pip install matplotlib numpy")
    sys.exit(1)

from vis_common import (
    CMAP, BNORM,
    MONTH_MIDS, MONTH_NAMES, SEASON_PEAKS, TIME_PEAKS,
    WEATHER_AXIS, WEATHER_AXIS_LABELS, ACT_AXIS,
    legend_patches, winner_idx, winner_idx_ex, doy_to_label,
)


# ======================================================================
#  § 1  Default panel configurations
#
#  每种模式展示若干面板，面板数任意增减——make_figure 会自动推断 (rows, cols)。
#  布局算法：cols = ceil(sqrt(n))，rows = ceil(n / cols)，多余格子隐藏。
#  常见面板数对应的布局：4→2×2  6→2×3  9→3×3  12→3×4
# ======================================================================

DEFAULT_PANELS = {
    # wx-hour: 固定 (activity, doy), 变动 weather × hour  — 9 panels (3×3)
    # 四季 × {idle, #focus, #chill} 采样，观察天气信号在不同季节和活跃状态下的权重
    "wx-hour": [
        {"activity": None,     "doy": 80,  "title": "idle · spring (doy 80)"},
        {"activity": None,     "doy": 172, "title": "idle · summer (doy 172)"},
        {"activity": None,     "doy": 265, "title": "idle · autumn (doy 265)"},
        {"activity": None,     "doy": 355, "title": "idle · winter (doy 355)"},
        {"activity": "#focus", "doy": 80,  "title": "#focus · spring (doy 80)"},
        {"activity": "#focus", "doy": 172, "title": "#focus · summer (doy 172)"},
        {"activity": "#focus", "doy": 355, "title": "#focus · winter (doy 355)"},
        {"activity": "#chill", "doy": 172, "title": "#chill · summer (doy 172)"},
        {"activity": "#chill", "doy": 355, "title": "#chill · winter (doy 355)"},
    ],
    # act-hour: 固定 (weather, doy), 变动 activity × hour  — 9 panels (3×3)
    # 天气预设 × 代表性季节，观察活跃度渐变在不同外部条件下的决策边界
    "act-hour": [
        {"weather": "none",     "doy": 80,  "title": "none · spring (doy 80)"},
        {"weather": "none",     "doy": 355, "title": "none · winter (doy 355)"},
        {"weather": "clear",    "doy": 80,  "title": "clear · spring (doy 80)"},
        {"weather": "clear",    "doy": 172, "title": "clear · summer (doy 172)"},
        {"weather": "clear",    "doy": 355, "title": "clear · winter (doy 355)"},
        {"weather": "mod_rain", "doy": 172, "title": "mod_rain · summer (doy 172)"},
        {"weather": "mod_rain", "doy": 265, "title": "mod_rain · autumn (doy 265)"},
        {"weather": "storm",    "doy": 80,  "title": "storm · spring (doy 80)"},
        {"weather": "storm",    "doy": 355, "title": "storm · winter (doy 355)"},
    ],
    # wx-season: 固定 (activity, hour), 变动 weather × doy  — 9 panels (3×3)
    # 覆盖全天各时段 + 活跃度基线，观察天气对季节维度的影响强度
    "wx-season": [
        {"activity": None,     "hour": 6.0,  "title": "idle · 06:00"},
        {"activity": None,     "hour": 10.0, "title": "idle · 10:00"},
        {"activity": None,     "hour": 14.0, "title": "idle · 14:00"},
        {"activity": None,     "hour": 18.0, "title": "idle · 18:00"},
        {"activity": None,     "hour": 22.0, "title": "idle · 22:00"},
        {"activity": "#focus", "hour": 10.0, "title": "#focus · 10:00"},
        {"activity": "#focus", "hour": 22.0, "title": "#focus · 22:00"},
        {"activity": "#chill", "hour": 14.0, "title": "#chill · 14:00"},
        {"activity": "#chill", "hour": 20.0, "title": "#chill · 20:00"},
    ],
    # act-season: 固定 (weather, hour), 变动 activity × doy  — 9 panels (3×3)
    # 4 种天气 × 代表性时段，观察活跃度在全年维度上与季节 Policy 的竞争
    "act-season": [
        {"weather": "none",     "hour": 10.0, "title": "none · 10:00"},
        {"weather": "none",     "hour": 22.0, "title": "none · 22:00"},
        {"weather": "clear",    "hour": 10.0, "title": "clear · 10:00"},
        {"weather": "clear",    "hour": 14.0, "title": "clear · 14:00"},
        {"weather": "clear",    "hour": 22.0, "title": "clear · 22:00"},
        {"weather": "mod_rain", "hour": 10.0, "title": "mod_rain · 10:00"},
        {"weather": "mod_rain", "hour": 22.0, "title": "mod_rain · 22:00"},
        {"weather": "storm",    "hour": 14.0, "title": "storm · 14:00"},
        {"weather": "storm",    "hour": 22.0, "title": "storm · 22:00"},
    ],
    # wx-act: 固定 (hour, doy), 变动 weather × activity  — 9 panels (3×3)
    # 四季 × 白天/夜晚两个时段，呈现天气 × 活跃度在不同时空背景下的完整交叉
    "wx-act": [
        {"hour":  8.0, "doy": 80,  "title": "08:00 · spring (doy 80)"},
        {"hour": 14.0, "doy": 80,  "title": "14:00 · spring (doy 80)"},
        {"hour":  8.0, "doy": 172, "title": "08:00 · summer (doy 172)"},
        {"hour": 14.0, "doy": 172, "title": "14:00 · summer (doy 172)"},
        {"hour": 20.0, "doy": 265, "title": "20:00 · autumn (doy 265)"},
        {"hour": 23.0, "doy": 265, "title": "23:00 · autumn (doy 265)"},
        {"hour": 20.0, "doy": 355, "title": "20:00 · winter (doy 355)"},
        {"hour": 23.0, "doy": 355, "title": "23:00 · winter (doy 355)"},
        {"hour": 14.0, "doy": 355, "title": "14:00 · winter (doy 355)"},
    ],
    # hr-doy: 固定 (activity, weather), 变动 hour × doy — 3×4 共 12 个面板
    # Row 1 — idle × 天气梯度（无信号 → 小雨）
    # Row 2 — idle × 极端天气  +  纯活动基线（晴天对照）
    # Row 3 — activity × weather 交叉组合
    "hr-doy": [
        {"activity": None,     "weather": "none",       "title": "idle · none"},
        {"activity": None,     "weather": "clear",      "title": "idle · clear"},
        {"activity": None,     "weather": "drizzle",    "title": "idle · drizzle"},
        {"activity": None,     "weather": "mod_rain",   "title": "idle · mod_rain"},
        {"activity": None,     "weather": "storm",      "title": "idle · storm"},
        {"activity": None,     "weather": "heavy_snow", "title": "idle · heavy_snow"},
        {"activity": "#focus", "weather": "clear",      "title": "#focus · clear"},
        {"activity": "#chill", "weather": "clear",      "title": "#chill · clear"},
        {"activity": "#focus", "weather": "overcast",   "title": "#focus · overcast"},
        {"activity": "#focus", "weather": "mod_rain",   "title": "#focus · mod_rain"},
        {"activity": "#chill", "weather": "mod_rain",   "title": "#chill · mod_rain"},
        {"activity": "#chill", "weather": "storm",      "title": "#chill · storm"},
    ],
}

# 每种模式的大标题
MODE_TITLES = {
    "hr-doy":     "Hour of Day × Month  (12 scenarios, fixed: activity, weather)",
    "wx-hour":    "Weather × Hour  (fixed: activity, season)",
    "act-hour":   "Activity × Hour  (fixed: weather, season)",
    "wx-season":  "Weather × Season  (fixed: activity, hour)",
    "act-season": "Activity × Season  (fixed: weather, hour)",
    "wx-act":     "Weather × Activity  (fixed: hour, season)",
}


# ======================================================================
#  § 2  Grid builders
#
#  每个 builder 返回 (轴采样点..., grid[row, col])。
#  分类轴 (weather) 的 grid 行数 = len(WEATHER_AXIS)。
#  连续轴 (activity) 的 grid 行数 = len(ACT_AXIS)。
#  pcolormesh 需要的 edge 数组在 § 3 的 draw 函数中计算。
# ======================================================================

def build_hr_doy(activity, weather: str, hour_step: float = 0.5, doy_step: int = 2):
    """策略 1: hour (cols) × doy (rows)。"""
    hours = np.arange(0, 24, hour_step)
    doys  = np.arange(1, 366, doy_step)
    grid  = np.array([
        [winner_idx(float(h), int(d), activity, weather) for h in hours]
        for d in doys
    ])
    return hours, doys, grid


def build_wx_hour(activity, doy: int, h_step: float = 0.25):
    """策略 2: weather (rows) × hour (cols)。"""
    hours = np.arange(0, 24, h_step)
    grid = np.array([
        [winner_idx(float(h), doy, activity, wx) for h in hours]
        for wx in WEATHER_AXIS
    ])
    return hours, grid


def build_act_hour(weather: str, doy: int, h_step: float = 0.25):
    """策略 3: activity (rows) × hour (cols)。"""
    hours = np.arange(0, 24, h_step)
    grid = np.array([
        [winner_idx_ex(float(h), doy, float(s), weather) for h in hours]
        for s in ACT_AXIS
    ])
    return hours, grid


def build_wx_season(activity, hour: float, d_step: int = 2):
    """策略 4: weather (rows) × doy (cols)。"""
    doys = np.arange(1, 366, d_step)
    grid = np.array([
        [winner_idx(hour, int(d), activity, wx) for d in doys]
        for wx in WEATHER_AXIS
    ])
    return doys, grid


def build_act_season(weather: str, hour: float, d_step: int = 2):
    """策略 5: activity (rows) × doy (cols)。"""
    doys = np.arange(1, 366, d_step)
    grid = np.array([
        [winner_idx_ex(hour, int(d), float(s), weather) for d in doys]
        for s in ACT_AXIS
    ])
    return doys, grid


def build_wx_act(hour: float, doy: int):
    """策略 6: weather (rows) × activity (cols)。"""
    grid = np.array([
        [winner_idx_ex(hour, doy, float(s), wx) for s in ACT_AXIS]
        for wx in WEATHER_AXIS
    ])
    return grid


# ======================================================================
#  § 3  Drawing functions
#
#  axis helper 用法与 vis_transitions.py § 5 相同：
#    pcolormesh(x_edges, y_edges, grid, cmap=CMAP, norm=BNORM,
#               shading="flat", rasterized=True)
#  其中 edges = append(centers - step/2, last_center + step/2)。
#
#  分类轴 (weather)：行号 0, 1, 2, ... 对应 WEATHER_AXIS 的预设,
#  edges = arange(N+1), 刻度放在 i+0.5 处使标签居中。
#
#  连续轴 (activity)：值域 [-1, +1], 用 edges 计算方式同 hour/doy。
#  idle 位置 (0.0) 画白色虚线分隔 chill 和 focus 区域。
# ======================================================================

# --- shared axis helpers ---

def _hour_xaxis(ax):
    """配置横轴为 hour (0-24)。"""
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 4))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 4)], fontsize=8)
    ax.set_xlabel("Hour of day", fontsize=9)


def _doy_xaxis(ax):
    """配置横轴为 doy (month 刻度)。"""
    ax.set_xlim(1, 365)
    ax.set_xticks(MONTH_MIDS)
    ax.set_xticklabels(MONTH_NAMES, fontsize=8)
    ax.set_xlabel("Month", fontsize=9)


def _wx_yaxis(ax):
    """配置纵轴为分类天气预设行。"""
    n = len(WEATHER_AXIS)
    ax.set_yticks(np.arange(n) + 0.5)
    ax.set_yticklabels(WEATHER_AXIS_LABELS, fontsize=8)
    ax.set_ylim(0, n)
    ax.invert_yaxis()     # "none" (最弱) 在顶部
    for y in range(1, n):
        ax.axhline(y, color="white", linewidth=0.3, alpha=0.6)
    ax.set_ylabel("Weather", fontsize=9)


def _act_yaxis(ax):
    """配置纵轴为连续 activity 强度 [-1, +1]。"""
    s_step = ACT_AXIS[1] - ACT_AXIS[0]
    ax.set_ylim(ACT_AXIS[0] - s_step / 2, ACT_AXIS[-1] + s_step / 2)
    ax.axhline(0, color="white", linewidth=0.9, linestyle="--", alpha=0.6)
    ax.set_yticks([-1, -0.5, 0, 0.5, 1])
    ax.set_yticklabels(["chill 1.0", "chill 0.5", "idle", "focus 0.5", "focus 1.0"],
                       fontsize=8)
    ax.set_ylabel("Activity  ← chill    idle    focus →", fontsize=9)


def _act_xaxis(ax):
    """配置横轴为连续 activity 强度 (mode wx-act)。"""
    s_step = ACT_AXIS[1] - ACT_AXIS[0]
    ax.set_xlim(ACT_AXIS[0] - s_step / 2, ACT_AXIS[-1] + s_step / 2)
    ax.axvline(0, color="white", linewidth=0.9, linestyle="--", alpha=0.6)
    ax.set_xticks([-1, -0.5, 0, 0.5, 1])
    ax.set_xticklabels(["chill\n1.0", "0.5", "idle", "0.5", "focus\n1.0"], fontsize=8)
    ax.set_xlabel("Activity  ← chill    idle    focus →", fontsize=9)


def _time_vlines(ax):
    """TimePolicy Hann 窗峰值垂直虚线 (hour 在 X 轴时)。"""
    for peak, lbl in TIME_PEAKS:
        ax.axvline(peak, color="white", linewidth=0.7, linestyle="--", alpha=0.4)


def _season_vlines(ax):
    """SeasonPolicy Hann 窗峰值垂直虚线 (doy 在 X 轴时)。"""
    for peak, lbl in SEASON_PEAKS:
        ax.axvline(peak, color="white", linewidth=0.7, linestyle="--", alpha=0.4)


# --- per-mode draw functions ---

def draw_hr_doy(ax, *, activity, weather, title):
    """策略 1: hour × doy 二维热力图面板。"""
    hours, doys, grid = build_hr_doy(activity, weather)
    h_step = hours[1] - hours[0]
    d_step = doys[1]  - doys[0]
    h_edges = np.append(hours - h_step / 2, hours[-1] + h_step / 2)
    d_edges = np.append(doys  - d_step / 2, doys[-1]  + d_step / 2)
    ax.pcolormesh(h_edges, d_edges, grid, cmap=CMAP, norm=BNORM,
                  shading="flat", rasterized=True)
    ax.set_xlim(0, 24)
    ax.set_ylim(1, 365)
    ax.invert_yaxis()   # Jan 显示在顶部
    ax.set_xticks(range(0, 25, 4))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 4)], fontsize=8)
    ax.set_yticks(MONTH_MIDS)
    ax.set_yticklabels(MONTH_NAMES, fontsize=8)
    ax.set_xlabel("Hour of day", fontsize=9)
    ax.set_ylabel("Month", fontsize=9)
    ax.set_title(title, fontsize=10, pad=4)
    for peak, _ in SEASON_PEAKS:
        ax.axhline(peak, color="white", linewidth=0.8, linestyle="--", alpha=0.45)
    for peak, _ in TIME_PEAKS:
        ax.axvline(peak, color="white", linewidth=0.8, linestyle="--", alpha=0.45)


def draw_wx_hour(ax, *, activity, doy, title):
    """策略 2: weather × hour 热力图面板。"""
    hours, grid = build_wx_hour(activity, doy)
    h_step = hours[1] - hours[0]
    h_edges = np.append(hours - h_step / 2, hours[-1] + h_step / 2)
    w_edges = np.arange(len(WEATHER_AXIS) + 1)
    ax.pcolormesh(h_edges, w_edges, grid, cmap=CMAP, norm=BNORM,
                  shading="flat", rasterized=True)
    _hour_xaxis(ax)
    _wx_yaxis(ax)
    _time_vlines(ax)
    ax.set_title(title, fontsize=10, pad=4)


def draw_act_hour(ax, *, weather, doy, title):
    """策略 3: activity × hour 热力图面板。"""
    hours, grid = build_act_hour(weather, doy)
    h_step = hours[1] - hours[0]
    s_step = ACT_AXIS[1] - ACT_AXIS[0]
    h_edges = np.append(hours - h_step / 2, hours[-1] + h_step / 2)
    s_edges = np.append(ACT_AXIS - s_step / 2, ACT_AXIS[-1] + s_step / 2)
    ax.pcolormesh(h_edges, s_edges, grid, cmap=CMAP, norm=BNORM,
                  shading="flat", rasterized=True)
    _hour_xaxis(ax)
    _act_yaxis(ax)
    _time_vlines(ax)
    ax.set_title(title, fontsize=10, pad=4)


def draw_wx_season(ax, *, activity, hour, title):
    """策略 4: weather × season 热力图面板。"""
    doys, grid = build_wx_season(activity, hour)
    d_step = doys[1] - doys[0]
    d_edges = np.append(doys - d_step / 2, doys[-1] + d_step / 2)
    w_edges = np.arange(len(WEATHER_AXIS) + 1)
    ax.pcolormesh(d_edges, w_edges, grid, cmap=CMAP, norm=BNORM,
                  shading="flat", rasterized=True)
    _doy_xaxis(ax)
    _wx_yaxis(ax)
    _season_vlines(ax)
    ax.set_title(title, fontsize=10, pad=4)


def draw_act_season(ax, *, weather, hour, title):
    """策略 5: activity × season 热力图面板。"""
    doys, grid = build_act_season(weather, hour)
    d_step = doys[1] - doys[0]
    s_step = ACT_AXIS[1] - ACT_AXIS[0]
    d_edges = np.append(doys - d_step / 2, doys[-1] + d_step / 2)
    s_edges = np.append(ACT_AXIS - s_step / 2, ACT_AXIS[-1] + s_step / 2)
    ax.pcolormesh(d_edges, s_edges, grid, cmap=CMAP, norm=BNORM,
                  shading="flat", rasterized=True)
    _doy_xaxis(ax)
    _act_yaxis(ax)
    _season_vlines(ax)
    ax.set_title(title, fontsize=10, pad=4)


def draw_wx_act(ax, *, hour, doy, title):
    """策略 6: weather × activity 热力图面板。"""
    grid = build_wx_act(hour, doy)
    s_step = ACT_AXIS[1] - ACT_AXIS[0]
    s_edges = np.append(ACT_AXIS - s_step / 2, ACT_AXIS[-1] + s_step / 2)
    w_edges = np.arange(len(WEATHER_AXIS) + 1)
    ax.pcolormesh(s_edges, w_edges, grid, cmap=CMAP, norm=BNORM,
                  shading="flat", rasterized=True)
    _act_xaxis(ax)
    _wx_yaxis(ax)
    ax.set_title(title, fontsize=10, pad=4)


# — dispatch table —
_DRAW_FN = {
    "hr-doy":     draw_hr_doy,
    "wx-hour":    draw_wx_hour,
    "act-hour":   draw_act_hour,
    "wx-season":  draw_wx_season,
    "act-season": draw_act_season,
    "wx-act":     draw_wx_act,
}


# ======================================================================
#  § 4  Figure assembler
# ======================================================================

def make_figure(mode: str) -> plt.Figure:
    """根据 mode 生成热力图，布局从面板数量自动推断。

    布局算法：
      cols = ceil(sqrt(n))，rows = ceil(n / cols)
      figsize 按每格 5.5w × 4.5h 计算；多余空格自动隐藏。
    """
    panels = DEFAULT_PANELS[mode]
    draw_fn = _DRAW_FN[mode]

    n = len(panels)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    fig_w = cols * 5.5
    fig_h = rows * 4.5

    fig, axes = plt.subplots(rows, cols, figsize=(fig_w, fig_h),
                             gridspec_kw={"hspace": 0.50, "wspace": 0.35})

    axes_flat = list(np.array(axes).flat) if rows * cols > 1 else [axes]

    for ax, panel in zip(axes_flat, panels):
        title = panel["title"]
        kwargs = {k: v for k, v in panel.items() if k != "title"}
        draw_fn(ax, title=title, **kwargs)

    # 隐藏多余的空白子图（当 n < rows×cols 时）
    for ax in axes_flat[n:]:
        ax.set_visible(False)

    fig.legend(
        handles=legend_patches(),
        loc="lower center",
        ncol=5,
        bbox_to_anchor=(0.5, -0.03),
        frameon=True,
        fontsize=9,
        title="Playlist",
        title_fontsize=9,
    )
    fig.suptitle(MODE_TITLES[mode], fontsize=13, y=1.01)
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    return fig


# ======================================================================
#  § 5  CLI
# ======================================================================

def main() -> None:
    modes = list(DEFAULT_PANELS.keys())
    parser = argparse.ArgumentParser(
        description="Multi-axis playlist decision explorer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  hr-doy       时间 × 月份    — 全年 hour×doy 全景 (12 场景, 3×4)
  wx-hour      天气 × 时间    — 不同天气预设在一天中如何影响选歌
  act-hour     活跃度 × 时间  — 用户活跃度 (EMA) 如何随时段影响选歌
  wx-season    天气 × 季节    — 天气在不同季节的效果差异
  act-season   活跃度 × 季节  — 用户活跃度在不同季节的效果差异
  wx-act       天气 × 活跃度  — 某一确定时刻的全交叉

Examples:
  python misc/vis_explore.py hr-doy
  python misc/vis_explore.py wx-hour
  python misc/vis_explore.py act-hour --save misc/explore
  python misc/vis_explore.py wx-act
""")
    parser.add_argument("mode", choices=modes, help="可视化模式")
    parser.add_argument("--save", metavar="BASENAME",
                        help="保存为 BASENAME_{mode}.png, 不弹窗")
    args = parser.parse_args()

    print(f"Building {args.mode} grids...", end=" ", flush=True)
    fig = make_figure(args.mode)
    print("done.")

    if args.save:
        path = f"{args.save}_{args.mode}.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        print(f"Saved: {path}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
