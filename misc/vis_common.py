"""
vis_common.py — 可视化脚本的共享工具集
========================================

提供分类热力图 (categorical heatmap) 所需的三件套：
  1. ListedColormap  — 离散颜色表, 每个色槽是纯色
  2. BoundaryNorm    — 把整数类别索引映射到对应色槽
  3. legend_patches  — 手动构造图例色块(分类图没有 colorbar)

还提供：
  - 日历 / 时间常量
  - winner_idx / winner_idx_ex — 求解获胜 playlist 索引
  - 天气 / 活动轴定义 — 供 vis_explore.py 使用

关于 pcolormesh 分类着色的详细教学注释, 请参阅 vis_transitions.py § 5。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import matplotlib.patches as mpatches
from matplotlib.colors import ListedColormap, BoundaryNorm

from sim_match import (
    env_vector, rank_playlists, CUSTOM_PLAYLISTS,
    SimPolicyOutput, _contribute,
    time_output, season_output, activity_output, weather_output,
    POLICY_WEIGHTS, WEATHER_PRESETS,
)


# ======================================================================
#  Palette & categorical colormap
#
#  【核心思路】
#  ListedColormap 接收颜色列表, 按索引取色(0 号→第一种颜色, ...)。
#  BoundaryNorm 把 [-0.5, 0.5, 1.5, ..., N-0.5] 切成 N 段,
#  使整数 i 恰好落入第 i 号色槽。
#  两者配合 pcolormesh(shading="flat") 即可画分类热力图。
# ======================================================================

PLAYLIST_NAMES = [name for name, _ in CUSTOM_PLAYLISTS]

_PALETTE = {
    "BRIGHT_FLOW":   "#F5C518",   # 金黄  — 晨光 / 专注
    "CASUAL_ANIME":  "#5BB8D4",   # 天蓝  — 日常休闲
    "SUNSET_GLOW":   "#FF8C00",   # 橙    — 日落
    "NIGHT_CHILL":   "#7B68EE",   # 中灰紫 — 夜晚放松
    "NIGHT_FOCUS":   "#2E5F8A",   # 深海蓝 — 夜晚专注
    "RAINY_MOOD":    "#4A90D9",   # 矢车菊蓝 — 雨天
    "WINTER_VIBES":  "#ADC8E0",   # 淡钢蓝 — 冬季
    "SPRING_BLOOM":  "#5CBE5C",   # 嫩绿  — 春季
    "SUMMER_GLOW":   "#D83820",   # 番茄红 — 夏季
    "AUTUMN_DRIFT":  "#C07830",   # 琥珀  — 秋季
}

COLORS = [_PALETTE.get(n, "#999999") for n in PLAYLIST_NAMES]
CMAP   = ListedColormap(COLORS)
BNORM  = BoundaryNorm(np.arange(-0.5, len(PLAYLIST_NAMES), 1), len(PLAYLIST_NAMES))


# ======================================================================
#  Calendar / time constants
# ======================================================================

MONTH_STARTS  = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
MONTH_LENGTHS = [31, 28, 31, 30,  31,  30,  31,  31,  30,  31,  30,  31]
MONTH_MIDS    = [s + l // 2 for s, l in zip(MONTH_STARTS, MONTH_LENGTHS)]
MONTH_NAMES   = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

SEASON_PEAKS = [(80, "Spr"), (172, "Sum"), (265, "Aut"), (355, "Win")]
TIME_PEAKS   = [(8, "dawn"), (14, "day"), (20, "sunset"), (23, "night")]

DOY_TO_MD = [(1, 1), (32, 2), (60, 3), (91, 4), (121, 5), (152, 6),
             (182, 7), (213, 8), (244, 9), (274, 10), (305, 11), (335, 12)]


def doy_to_label(doy: int) -> str:
    """将 day-of-year 转换为近似日历日期字符串 'MM-DD'。"""
    month = max(m for d, m in DOY_TO_MD if d <= doy)
    mday  = doy - [d for d, m in DOY_TO_MD if m == month][0] + 1
    return f"{month:02d}-{mday:02d}"


# ======================================================================
#  Legend
# ======================================================================

def legend_patches() -> list:
    """生成图例色块列表, 每个 playlist 一个 Patch。"""
    return [
        mpatches.Patch(facecolor=COLORS[i], label=PLAYLIST_NAMES[i],
                       edgecolor="#aaaaaa", linewidth=0.4)
        for i in range(len(PLAYLIST_NAMES))
    ]


# ======================================================================
#  Winner-index functions
# ======================================================================

def winner_idx(hour: float, doy: int, activity, weather: str) -> int:
    """离散 activity 版本。activity = "#focus" | "#chill" | None。"""
    ev = env_vector(hour, doy, activity, weather)
    return PLAYLIST_NAMES.index(rank_playlists(CUSTOM_PLAYLISTS, ev)[0][0])


def _merge(dst: dict, src: dict) -> None:
    for k, v in src.items():
        dst[k] = dst.get(k, 0.0) + v


def winner_idx_ex(
    hour: float, doy: int,
    act_strength: float,
    weather: str,
) -> int:
    """连续 activity 强度版本。

    act_strength 取值 [-1, +1]:
      -1.0 = 完全 #chill  (intensity = 1.0)
       0.0 = idle          (无 activity 信号)
      +1.0 = 完全 #focus  (intensity = 1.0)

    中间值映射到 intensity（EMA 收敛程度），而非 weight_scale。
    """
    ev: dict[str, float] = {}
    _merge(ev, _contribute(time_output(hour), POLICY_WEIGHTS["time"]))
    _merge(ev, _contribute(season_output(doy), POLICY_WEIGHTS["season"]))
    if abs(act_strength) > 0.01:
        tag = "#focus" if act_strength > 0 else "#chill"
        output = activity_output(tag)
        output.intensity = abs(act_strength)
        _merge(ev, _contribute(output, POLICY_WEIGHTS["activity"]))
    wx_output = weather_output(weather)
    if wx_output is not None:
        _merge(ev, _contribute(wx_output, POLICY_WEIGHTS["weather"]))
    return PLAYLIST_NAMES.index(rank_playlists(CUSTOM_PLAYLISTS, ev)[0][0])


# ======================================================================
#  Axis definitions  (used by vis_explore.py)
# ======================================================================

# 有序天气预设, 从平静 → 极端, 用作分类轴的 Y 行
WEATHER_AXIS = [
    "none", "clear", "overcast", "drizzle", "mod_rain",
    "heavy_rain", "light_snow", "heavy_snow", "storm", "heavy_storm",
]
WEATHER_AXIS_LABELS = [p.replace("_", " ") for p in WEATHER_AXIS]

# 连续 activity 轴: -1 = 完全 chill, 0 = idle, +1 = 完全 focus
ACT_AXIS = np.linspace(-1.0, 1.0, 41)   # 步长 0.05
