#!/usr/bin/env python3
"""
vis_transitions.py — Playlist winner transition visualizer
==========================================================

Default: 2×4 heatmap grid  (Hour of day × Month, 8 scenario panels)
  Each panel answers: given this fixed (activity, weather) combo,
  which playlist wins as hour and month vary?  Smooth color boundaries
  confirm the Hann-window interpolation is gradual, not step-like.

  python misc/vis_transitions.py                     # show heatmap (8 panels)
  python misc/vis_transitions.py --save out          # save as out_heatmap.png

Optional: daily strip  (X = hour, rows = scenario variants, fixed month/day)
  python misc/vis_transitions.py --strip             # heatmap + strip
  python misc/vis_transitions.py --strip --day 172   # summer solstice day
  python misc/vis_transitions.py --strip --save out  # save both figures

Note: "day" refers to day-of-year (1-365), a standard meteorological index.
  Quick reference: 80=Mar-21  95=Apr-05  172=Jun-21  265=Sep-22  355=Dec-21
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.colors import ListedColormap, BoundaryNorm
    import numpy as np
except ImportError as exc:
    print(f"Missing dependency: {exc}")
    print("Install with:  pip install matplotlib numpy")
    sys.exit(1)

from sim_match import env_vector, rank_playlists, CUSTOM_PLAYLISTS


# ======================================================================
#  § 1  Palette & categorical colormap
#
#  【绘制分类热力图的核心思路】
#  普通热力图用连续数值→连续颜色渐变（如 viridis）。
#  分类热力图用整数类别索引→离散颜色表，每种颜色对应一个类别。
#  实现步骤：
#    1. 为每个类别指定一种 hex 颜色，存入有序列表 COLORS。
#    2. 用 ListedColormap(COLORS) 创建"固定色槽"的 colormap，
#       第 0 号色槽 → COLORS[0]，第 1 号 → COLORS[1]，以此类推。
#    3. 用 BoundaryNorm 把 colormap 的 [0, 1] 范围切成 N 个等宽色块，
#       使得数据值 i（整数）恰好落入第 i 号色槽。
#       boundaries = [-0.5, 0.5, 1.5, ..., N-0.5]  ← 每个整数居于区间中央
#    4. 把数据矩阵（每个格子存整数类别索引）送给 pcolormesh，
#       指定 cmap=CMAP, norm=BNORM，即可得到分类热力图。
# ======================================================================

PLAYLIST_NAMES = [name for name, _ in CUSTOM_PLAYLISTS]

# 每个 playlist 的语义颜色（与播放列表内容的视觉联想保持一致）
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

# COLORS[i] 对应 PLAYLIST_NAMES[i]，顺序必须严格一致
COLORS = [_PALETTE.get(n, "#999999") for n in PLAYLIST_NAMES]

# ListedColormap：把一组颜色列表封装成 matplotlib 可识别的 colormap。
# 与 viridis/plasma 等连续 colormap 不同，它没有插值，每个色槽是纯色。
CMAP = ListedColormap(COLORS)

# BoundaryNorm：定义数据值如何映射到色槽编号。
#   np.arange(-0.5, N, 1) 生成 [-0.5, 0.5, 1.5, ..., N-0.5] 共 N+1 个边界，
#   将 [0, N-1] 的整数各自放进独立色槽，不与相邻颜色混合。
BNORM = BoundaryNorm(np.arange(-0.5, len(PLAYLIST_NAMES), 1), len(PLAYLIST_NAMES))


# ======================================================================
#  § 2  Scenario rows  (edit to add/remove rows from the strip charts)
#
#  Format: (display_label, activity, weather_preset)
#  activity : "#focus" | "#chill" | None (idle)
#  weather  : any key from WEATHER_PRESETS in sim_match.py, or "none"
# ======================================================================

VIS_SCENARIOS = [
    #  display label           activity    weather
    ("idle · none",            None,       "none"),
    ("idle · clear",           None,       "clear"),
    ("idle · overcast",        None,       "overcast"),
    ("idle · drizzle",         None,       "drizzle"),
    ("idle · mod_rain",        None,       "mod_rain"),
    ("idle · storm",           None,       "storm"),
    ("idle · heavy_snow",      None,       "heavy_snow"),
    ("#focus · clear",         "#focus",   "clear"),
    ("#chill · clear",         "#chill",   "clear"),
]

# Scenarios used for the 2D heatmap figure (3 rows × 4 cols)
# Format: (activity, weather_preset, panel_title)
#
# 布局逻辑：
#   Row 1 — 纯天气梯度（idle），从无信号到强降雨，观察季节优先级
#   Row 2 — 极端天气（idle）+ 纯活动（天气恒定 clear），建立对照基线
#   Row 3 — 天气 × 活动 交叉组合，观察两种外部信号叠加时的竞争结果
HEATMAP_SCENARIOS = [
    # Row 1 — idle, weather gradient: no signal → heavy weather
    (None,     "none",       "idle · none"),
    (None,     "clear",      "idle · clear"),
    (None,     "drizzle",    "idle · drizzle"),
    (None,     "mod_rain",   "idle · mod_rain"),
    # Row 2 — idle extreme weather  +  activity baselines (clear sky)
    (None,     "storm",      "idle · storm"),
    (None,     "heavy_snow", "idle · heavy_snow"),
    ("#focus", "clear",      "#focus · clear"),
    ("#chill", "clear",      "#chill · clear"),
    # Row 3 — activity × weather cross combinations
    ("#focus", "overcast",   "#focus · overcast"),
    ("#focus", "mod_rain",   "#focus · mod_rain"),
    ("#chill", "mod_rain",   "#chill · mod_rain"),
    ("#chill", "storm",      "#chill · storm"),
]


# ======================================================================
#  § 3  Grid builders
#
#  【如何生成热力图的数据矩阵】
#  热力图本质上是一个二维数组，这里每个格子存的是"哪个 playlist 获胜"的
#  整数索引。构建流程：
#    1. 定义横轴范围（小时）和纵轴范围（日序数）的采样点。
#    2. 对笛卡尔积 (hour, doy) 中每个点，调用下方 _winner_idx 求获胜者索引。
#    3. 用 np.array 列表推导式组装成 grid[row, col] = 整数 的矩阵，
#       交给 § 5 中的 pcolormesh 即可上色。
#
#  采样分辨率（hour_step / doy_step）越小，图像越细腻，但计算越慢。
#  0.5 小时 + 2 天的步长在普通笔记本约 1 秒内完成。
# ======================================================================

def _winner_idx(hour: float, doy: int, activity, weather: str) -> int:
    """给定一个时间点和环境状态，返回当前获胜 playlist 在 PLAYLIST_NAMES 中的索引。

    这个整数索引就是送给 pcolormesh 的"分类标签"——
    pcolormesh + BoundaryNorm 会把整数 i 映射到 COLORS[i]。
    """
    ev = env_vector(hour, doy, activity, weather)
    return PLAYLIST_NAMES.index(rank_playlists(CUSTOM_PLAYLISTS, ev)[0][0])


def build_daily_grid(day: int, step: float = 0.25) -> tuple[np.ndarray, np.ndarray]:
    """在固定日期（day-of-year）上，扫描 hour 0→24，构建一维条带数据。

    用于 strip chart（横轴=小时，每行=一种场景）。
    返回：
        hours : shape (H,)       — 采样小时值
        grid  : shape (S, H)     — S 个场景 × H 个小时，每格存获胜者索引
    """
    hours = np.arange(0, 24, step)
    grid = np.array([
        [_winner_idx(float(h), doy, act, wx) for h in hours]
        for _, act, wx in VIS_SCENARIOS
    ])
    return hours, grid


def build_2d_grid(
    activity, weather: str,
    hour_step: float = 0.5, doy_step: int = 2,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """在固定 (activity, weather) 下，扫描 hour × day-of-year 全平面，
    构建 2D 热力图数据矩阵。

    返回：
        hours : shape (H,)         — 横轴采样点（小时）
        doys  : shape (D,)         — 纵轴采样点（日序数 1-365）
        grid  : shape (D, H)       — 每格存获胜者索引
                注意 grid[row, col] → row=纵轴(doy)，col=横轴(hour)，
                符合 pcolormesh 的 Z[i, j] 在 Y[i] × X[j] 处着色的约定。
    """
    hours = np.arange(0, 24, hour_step)
    doys  = np.arange(1, 366, doy_step)
    grid  = np.array([
        [_winner_idx(float(h), int(d), activity, weather) for h in hours]
        for d in doys
    ])
    return hours, doys, grid


# ======================================================================
#  § 4  Calendar / time reference constants
# ======================================================================

_MONTH_STARTS  = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
_MONTH_LENGTHS = [31, 28, 31, 30,  31,  30,  31,  31,  30,  31,  30,  31]
_MONTH_MIDS    = [s + l // 2 for s, l in zip(_MONTH_STARTS, _MONTH_LENGTHS)]
_MONTH_NAMES   = ["Jan","Feb","Mar","Apr","May","Jun",
                  "Jul","Aug","Sep","Oct","Nov","Dec"]

# Hann-window peak DOYs (matches SeasonPolicy / sim_match.py)
_SEASON_PEAKS  = [(80, "Spr"), (172, "Sum"), (265, "Aut"), (355, "Win")]
# TimePolicy peaks (default day_start=8, night_start=20)
_TIME_PEAKS    = [(8, "dawn"), (14, "day"), (20, "sunset"), (23, "night")]


# ======================================================================
#  § 5  Drawing helpers
#
#  【pcolormesh 绘制分类热力图的关键细节】
#
#  pcolormesh(X_edges, Y_edges, Z, cmap=..., norm=..., shading="flat")
#  ───────────────────────────────────────────────────────────────────
#  ① X_edges / Y_edges 是"格子边界"，比数据点多 1 个。
#    例如数据点 hours = [0.0, 0.5, 1.0, ...]（N 个），
#    边界 = [-0.25, 0.25, 0.75, ...]（N+1 个）。
#    计算方式：edges = append(centers - step/2, last_center + step/2)
#    这样每个格子恰好以数据点为中心，而非左对齐。
#
#  ② shading="flat"：每个格子涂单色（不插值）。
#    对于整数分类数据这是正确选择；如果用 "gouraud" 会在类别边界产生渐变，
#    出现"颜色混合"的假象。
#
#  ③ rasterized=True：把 pcolormesh 输出写为位图而非矢量路径。
#    大分辨率热力图（如 365×48 格）用矢量路径会让 SVG/PDF 文件极大，
#    rasterized=True 可把它压缩到合理大小。
#
#  ④ 分类图没有自然的 colorbar（因为颜色没有大小顺序），
#    用 mpatches.Patch 手动构造图例是最常见做法：
#    每个 Patch 一种颜色 + 一个标签，和 fig.legend() 配合。
# ======================================================================

def _legend_patches() -> list:
    """生成图例所需的色块列表，每个 playlist 一个带颜色的 Patch。

    分类热力图没有自动 colorbar，需要用 Patch 手动构造图例。
    edgecolor/linewidth 让相近颜色的 Patch 之间有细边框，视觉上更好区分。
    """
    return [
        mpatches.Patch(facecolor=COLORS[i], label=PLAYLIST_NAMES[i],
                       edgecolor="#aaaaaa", linewidth=0.4)
        for i in range(len(PLAYLIST_NAMES))
    ]


def _configure_strip_yaxis(ax, n_rows: int) -> None:
    """配置条带图的 Y 轴：刻度居中对齐每行，并画白色分隔线。

    pcolormesh 的格子是 [0, n_rows] 区间，刻度 +0.5 才能居中落在每行中央。
    invert_yaxis() 让第 0 行显示在顶部，与列表顺序保持一致（直觉上更自然）。
    """
    ax.set_yticks(np.arange(n_rows) + 0.5)
    ax.set_yticklabels([s[0] for s in VIS_SCENARIOS[:n_rows]], fontsize=9)
    ax.set_ylim(0, n_rows)
    ax.invert_yaxis()   # 第 0 行在顶部，与 VIS_SCENARIOS 列表顺序对应
    for y in range(1, n_rows):
        ax.axhline(y, color="white", linewidth=0.4, alpha=0.7)


def draw_daily_strip(ax, doy: int) -> None:
    """绘制"固定日期，横轴=时间"的一维条带图。

    pcolormesh 核心用法：
      x_edges : 小时边界，形状 (H+1,)，每格以采样点为中心
      y_edges : 行边界，形状 (S+1,)，整数 0, 1, 2, ...
      grid    : 形状 (S, H)，每格存整数类别索引
    """
    hours, grid = build_daily_grid(doy)
    n_rows = grid.shape[0]
    step = hours[1] - hours[0]

    # 边界 = 采样中心 ± 半步长，最后追加末尾边界
    # 这确保每个色格恰好覆盖 [center - step/2, center + step/2] 的区间
    x_edges = np.append(hours - step / 2, hours[-1] + step / 2)
    y_edges = np.arange(n_rows + 1)   # 整数行边界：0, 1, 2, ...

    # shading="flat"：每格单色，不在边界插值 —— 分类数据的正确选择
    ax.pcolormesh(x_edges, y_edges, grid, cmap=CMAP, norm=BNORM,
                  shading="flat", rasterized=True)
    _configure_strip_yaxis(ax, n_rows)
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 2))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 2)], fontsize=9)

    # 将 day-of-year 转换为近似日历日期，用于坐标轴标签
    _DOY_TO_MD = [(1,1),(32,2),(60,3),(91,4),(121,5),(152,6),
                  (182,7),(213,8),(244,9),(274,10),(305,11),(335,12)]
    month = max(m for d, m in _DOY_TO_MD if d <= doy)
    mdoy  = doy - [d for d, m in _DOY_TO_MD if m == month][0] + 1
    ax.set_xlabel(f"Hour of doy  (fixed date ≈ {month:02d}-{mdoy:02d},  doy {doy} of year)",
                  fontsize=10)
    ax.set_title("Daily cycle — winning playlist per scenario variant", fontsize=11, pad=4)

    # 在 TimePolicy Hann 窗峰值处画白色虚线，帮助识别时段切换点
    for peak, label in _TIME_PEAKS:
        ax.axvline(peak, color="white", linewidth=0.9, linestyle="--", alpha=0.5)
        ax.text(peak, n_rows + 0.15, label, ha="center", va="bottom",
                fontsize=7.5, color="#555555",
                transform=ax.transData, clip_on=False)


def draw_2d_heatmap(ax, activity, weather: str, title: str) -> None:
    """绘制一个完整的 Hour × Day-of-Year 二维分类热力图面板。

    与 draw_daily_strip 逻辑完全一致，区别仅在于两个维度都是连续扫描的，
    即 X=小时，Y=日序数，每个格子颜色 = 该 (hour, doy) 下的获胜 playlist。

    关键：d_edges 的计算与 h_edges 相同——都是"中心点 ± 半步长"，
    保证格子在坐标轴上的位置与采样点严格对齐。
    """
    hours, doys, grid = build_2d_grid(activity, weather)
    h_step = hours[1] - hours[0]
    d_step = doys[1] - doys[0]

    # 两个轴都需要比数据点多 1 个的边界数组
    h_edges = np.append(hours - h_step / 2, hours[-1] + h_step / 2)
    d_edges = np.append(doys  - d_step / 2, doys[-1]  + d_step / 2)

    ax.pcolormesh(h_edges, d_edges, grid, cmap=CMAP, norm=BNORM,
                  shading="flat", rasterized=True)

    # --- 坐标轴配置 ---
    ax.set_xlim(0, 24)
    ax.set_ylim(1, 365)
    ax.invert_yaxis()   # Jan 显示在顶部（1月 = doy 1 在上方）
    ax.set_xticks(range(0, 25, 4))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 4)], fontsize=8)
    # Y 轴：用月份中间日序数定位刻度，显示月份名
    ax.set_yticks(_MONTH_MIDS)
    ax.set_yticklabels(_MONTH_NAMES, fontsize=8)
    ax.set_xlabel("Hour of day", fontsize=9)
    ax.set_ylabel("Month", fontsize=9)
    ax.set_title(title, fontsize=10, pad=4)

    # 季节峰值处画水平虚线（对应 SeasonPolicy Hann 窗的 4 个峰）
    for peak, _ in _SEASON_PEAKS:
        ax.axhline(peak, color="white", linewidth=0.8, linestyle="--", alpha=0.45)
    # 时间峰值处画垂直虚线（対应 TimePolicy Hann 窗的 4 个峰）
    for peak, label in _TIME_PEAKS:
        ax.axvline(peak, color="white", linewidth=0.8, linestyle="--", alpha=0.45)
        ax.text(peak, 0, label, ha="center", va="bottom",
                fontsize=7, color="#dddddd",
                transform=ax.transData, clip_on=False)


# ======================================================================
#  § 6  Figure assemblers
#
#  【多面板布局技巧】
#  plt.subplots(nrows, ncols, figsize=..., gridspec_kw=...)
#    hspace : 子图行间距（相对于子图高度的比例）
#    wspace : 子图列间距（相对于子图宽度的比例）
#
#  tight_layout(rect=[left, bottom, right, top])
#    将所有子图压缩到 rect 指定的区域内，为图例预留空间：
#    rect=[0, 0.07, 1, 1] → 底部留 7% 给图例
#    rect=[0, 0, 0.88, 1] → 右侧留 12% 给图例
# ======================================================================

def make_strip_figure(doy: int) -> plt.Figure:
    """单日条带图：X = 小时，每行 = 一种场景变体。"""
    fig, ax = plt.subplots(1, 1, figsize=(16, 5))
    draw_daily_strip(ax, doy=doy)

    # 图例放在图形右侧外部：bbox_to_anchor=(1.01, 0.5) 超出坐标轴范围
    fig.legend(
        handles=_legend_patches(),
        loc="center right",
        bbox_to_anchor=(1.01, 0.5),
        frameon=True,
        fontsize=9,
        title="Playlist",
        title_fontsize=9,
    )
    fig.suptitle("Playlist Daily Transition Strip", fontsize=12, y=1.02)
    fig.tight_layout(rect=[0, 0, 0.88, 1])   # 右侧留 12% 给图例
    return fig


def make_heatmap_figure() -> plt.Figure:
    """3×4 热力图网格，覆盖 12 种场景，X=小时，Y=月份。

    Row 1: idle × 天气梯度（无→小雨）
    Row 2: idle × 极端天气  +  activity × clear（对照基线）
    Row 3: activity × 天气 交叉组合（最复杂的场景）
    """
    n_rows, n_cols = 3, 4
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(20, 14),
                             gridspec_kw={"hspace": 0.50, "wspace": 0.25})

    # axes.flat 将 2D 数组展平为迭代器，与 HEATMAP_SCENARIOS 逐一配对
    for ax, (act, wx, title) in zip(axes.flat, HEATMAP_SCENARIOS):
        draw_2d_heatmap(ax, act, wx, title)

    # 图例放在图形底部中央：需要在 tight_layout 的 rect 中为其预留空间
    fig.legend(
        handles=_legend_patches(),
        loc="lower center",
        ncol=5,                            # 5 列排布以节省垂直空间
        bbox_to_anchor=(0.5, -0.03),
        frameon=True,
        fontsize=9,
        title="Playlist",
        title_fontsize=9,
    )
    fig.suptitle("Playlist Heatmap: Hour of Day × Month  (12 scenarios)",
                 fontsize=13, y=1.01)
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    return fig


# ======================================================================
#  § 7  CLI
# ======================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visualize playlist winner transitions across time and seasons",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python misc/vis_transitions.py                     # heatmap (8 panels), show window
  python misc/vis_transitions.py --save out          # save as out_heatmap.png
  python misc/vis_transitions.py --strip             # heatmap + daily strip
  python misc/vis_transitions.py --strip --day 265   # autumn (Sep-22) daily strip
  python misc/vis_transitions.py --strip --save out  # save both figures
""")
    parser.add_argument("--strip", action="store_true",
                        help="Also show the daily strip chart (hour of day, fixed date)")
    parser.add_argument("--day", type=int, default=95, metavar="N",
                        help="Day of year for the daily strip (default: 95 = Apr-05).  "
                             "Reference: 80=Mar-21  172=Jun-21  265=Sep-22  355=Dec-21")
    parser.add_argument("--save", metavar="BASENAME",
                        help="Save figures to BASENAME_heatmap.png [and BASENAME_strip.png] "
                             "instead of opening a window")
    args = parser.parse_args()

    print("Building grids...", end=" ", flush=True)
    fig_heatmap = make_heatmap_figure()
    fig_strip   = make_strip_figure(day=args.day) if args.strip else None
    print("done.")

    if args.save:
        base = args.save
        path = f"{base}_heatmap.png"
        fig_heatmap.savefig(path, dpi=150, bbox_inches="tight")
        print(f"Saved: {path}")
        if fig_strip:
            path2 = f"{base}_strip.png"
            fig_strip.savefig(path2, dpi=150, bbox_inches="tight")
            print(f"Saved: {path2}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
