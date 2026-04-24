#!/usr/bin/env python3
"""
sim_match.py — 离线 Policy 模拟器 & 播单标签调优工具
=====================================================

功能
----
1. 复现真实 Policy 的数学（Hann 窗、L2 归一化、强度模型）
2. 对给定场景矩阵计算每个播单的余弦相似度得分
3. 反向求解：根据"期望场景→播单"映射，推导理想的播单标签值

快速上手
--------
# 运行内置播单对所有场景的匹配结果（默认）:
    python misc/sim_match.py

# 从你的 scheduler_config.json 读取播单:
    python misc/sim_match.py --config scheduler_config.json

# 对比旧版 vs 优化版播单:
    python misc/sim_match.py --compare

# 反向求解理想标签（从 EXPECTED_WINNERS 出发）:
    python misc/sim_match.py --solve

# 跳过 Policy 诊断输出（更简洁）:
    python misc/sim_match.py --no-diag

# 测试不同 #clear 基线强度（what-if 分析）:
    python misc/sim_match.py --clear-cap 0.5

可配置内容
----------
- POLICY_WEIGHTS   : 各 Policy 的 weight_scale (ws) 参数
- CUSTOM_PLAYLISTS : 你的播单名称 + 标签权重（主要调优区域）
- SCENARIOS        : 测试场景矩阵（时间/季节/活动/天气）
- EXPECTED_WINNERS : --solve 模式的期望映射（场景名 → 播单名）

注意
----
本文件是独立工具，刻意 **不导入** core/policies.py：
  - WeatherPolicy 有 HTTP 副作用（会真实请求 OWM API）
  - ActivityPolicy 有状态 EMA，需多 tick 收敛
  - 此处用纯函数实现等价数学，便于 what-if 参数扫描
"""
import argparse
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# ======================================================================
#  SECTION 1  Policy Weight Scales
#  These mirror the weight_scale field in scheduler_config.json.
#  Changing these affects both env_vector synthesis and --solve output.
# ======================================================================

POLICY_WEIGHTS = {
    "time":     0.8,   # TimePolicy     ||contrib|| = salience * 0.8  (0.4–0.8)
    "season":   0.6,   # SeasonPolicy   ||contrib|| = salience * 0.6  (0.3–0.6)
    "activity": 1.2,   # ActivityPolicy ||contrib|| = intensity * 1.2 (0 idle, 1.2 active)
    "weather":  1.5,   # WeatherPolicy  ||contrib|| = raw_norm * 1.5
}


# ======================================================================
#  SECTION 2  Policy Math  (mirrors core/policies.py exactly)
# ======================================================================

def _circ(a: float, b: float, p: float) -> float:
    """Shortest arc distance on a circle of period p."""
    d = abs(a - b) % p
    return min(d, p - d)


def _hann(d: float, H: float) -> float:
    """Hann window: [0,1] weight for distance d within half-bandwidth H."""
    return 0.5 * (1.0 + math.cos(math.pi * d / H)) if d < H else 0.0


def _l2(v: Dict[str, float]) -> float:
    """L2 norm of a tag vector."""
    return math.sqrt(sum(w * w for w in v.values())) if v else 0.0


def _l2_normalize(v: Dict[str, float]) -> Dict[str, float]:
    """L2-normalize a tag vector. Returns empty dict if near-zero."""
    n = _l2(v)
    return {t: w / n for t, w in v.items()} if n > 1e-6 else {}


@dataclass
class SimPolicyOutput:
    """Mirrors core/policies.PolicyOutput for offline simulation."""
    direction: Dict[str, float]   # L2-normalized
    salience: float = 1.0         # [0, 1]
    intensity: float = 1.0        # [0, ∞) — WeatherPolicy can exceed 1.0


def _contribute(output: SimPolicyOutput, ws: float) -> Dict[str, float]:
    """Compute contribution vector: direction * salience * intensity * ws."""
    scale = output.salience * output.intensity * ws
    return {t: w * scale for t, w in output.direction.items()}


# -- TimePolicy ----------------------------------------------------------
#  4 peaks evenly distributed on the 24h circle; half-bandwidth H = 6h.
#  Default day_start=8, night_start=20 gives peaks:
#    #dawn=8, #day=14, #sunset=20, #night=2
#
#  Semantic output: direction = normalized Hann weights,
#                   salience  = peak Hann value (1.0 at peak, <1 at transitions),
#                   intensity = 1.0 (time is always present)

def time_output(
    hour: float,
    day_start: int = 8,
    night_start: int = 20,
) -> SimPolicyOutput:
    """
    Returns the time SimPolicyOutput for the given hour.

    direction : L2-normalized Hann window weights over #dawn/#day/#sunset/#night
    salience  : peak Hann value — high at period centers, low at transitions
    intensity : 1.0 (time signal is always present)
    """
    day_span = (night_start - day_start) % 24
    night_span = 24 - day_span
    peaks = {
        "#dawn":   day_start,
        "#day":    (day_start + day_span / 2) % 24,
        "#sunset": night_start % 24,
        "#night":  (night_start + night_span / 2) % 24,
    }
    H = 24 / len(peaks)  # half-bandwidth = 6h
    raw = {}
    best_w = 0.0
    for tag, peak in peaks.items():
        w = _hann(_circ(hour, peak, 24), H)
        if w > 1e-4:
            raw[tag] = w
            if w > best_w:
                best_w = w
    direction = _l2_normalize(raw)
    return SimPolicyOutput(direction=direction, salience=best_w, intensity=1.0)


# -- SeasonPolicy --------------------------------------------------------
#  4 peaks on the 365d circle; half-bandwidth H ~= 91.25d (one quarter-year).
#  Peaks: spring=80 (Mar-21), summer=172 (Jun-21),
#         autumn=265 (Sep-22),  winter=355 (Dec-21)
#
#  Semantic output: same pattern as TimePolicy.

_SEASON_PEAKS = {"#spring": 80, "#summer": 172, "#autumn": 265, "#winter": 355}

def season_output(doy: int) -> SimPolicyOutput:
    """
    Returns the season SimPolicyOutput for day-of-year doy.

    direction : L2-normalized Hann window weights over #spring/#summer/#autumn/#winter
    salience  : peak Hann value
    intensity : 1.0

    doy: day of year (1-365).  Quick reference:
         80=Mar-21  95=Apr-05  172=Jun-21  265=Sep-22  355=Dec-21
    """
    H = 365 / len(_SEASON_PEAKS)  # ~91.25d
    raw = {}
    best_w = 0.0
    for tag, peak in _SEASON_PEAKS.items():
        w = _hann(_circ(doy, peak, 365), H)
        if w > 1e-4:
            raw[tag] = w
            if w > best_w:
                best_w = w
    direction = _l2_normalize(raw)
    return SimPolicyOutput(direction=direction, salience=best_w, intensity=1.0)


# -- ActivityPolicy ------------------------------------------------------
#  Assumes EMA has fully converged (steady state).
#  direction = unit tag, salience = 1.0, intensity = 1.0.
#  For partial convergence (EMA in transition), set intensity < 1.0.

def activity_output(tag: Optional[str]) -> Optional[SimPolicyOutput]:
    """
    Returns steady-state activity SimPolicyOutput.

    tag: "#focus" | "#chill" | None (idle)
    Returns None when idle (no activity signal).
    """
    if not tag:
        return None
    return SimPolicyOutput(direction={tag: 1.0}, salience=1.0, intensity=1.0)


# -- WeatherPolicy -------------------------------------------------------
#  Semantic decomposition:
#    direction = L2-normalized tag vector (weather type)
#    salience  = 1.0 (weather IDs are unambiguous)
#    intensity = L2 norm of raw vector (physical severity, unclamped)
#
#  Intensity tiers visible in raw norms:
#    T1 (~0.25) - barely noticeable  (light drizzle, haze)
#    T2 (~0.50) - ambient / baseline (clear sky, light cloud)
#    T3 (~0.75) - noticeable         (heavy rain, fog, moderate storm)
#    T4 (~1.00+) - dominant / extreme (extreme rain, heavy snow, heavy storm)
#
#  IMPORTANT: clear sky (#clear) is intentionally T2 (raw=0.50, intensity=0.50).
#  Before the v1.1.0 fix it was T4 (1.00), which overpowered focus/chill signals.
#  To simulate old behavior: pass clear_intensity=2.0 to weather_output().

WEATHER_PRESETS: Dict[str, Dict[str, float]] = {
    # -- Sky conditions (capped at T2=0.50) ------------------------------
    "clear":         {"#clear": 0.50},               # T2 — sunny, ambient
    "few_clouds":    {"#clear": 0.47, "#cloudy": 0.16},
    "scattered":     {"#clear": 0.35, "#cloudy": 0.35},
    "broken_clouds": {"#cloudy": 0.47, "#clear": 0.16},
    "overcast":      {"#cloudy": 0.50},              # T2 — fully overcast
    # -- Rain ------------------------------------------------------------
    "light_drizzle": {"#rain": 0.25},                # T1 — barely noticeable
    "drizzle":       {"#rain": 0.40},
    "light_rain":    {"#rain": 0.40},                # OWM code 500
    "mod_rain":      {"#rain": 0.65},                # OWM code 501
    "heavy_rain":    {"#rain": 0.85},                # OWM code 502
    "extreme_rain":  {"#rain": 1.00},                # OWM code 503/504, T4
    # -- Snow ------------------------------------------------------------
    "light_snow":    {"#snow": 0.40},
    "snow":          {"#snow": 0.70},
    "heavy_snow":    {"#snow": 1.00},                # T4
    # -- Storm -----------------------------------------------------------
    # Pure storm codes (21x) now include #rain: dry lightning is rare in
    # practice; real thunderstorms almost always carry precipitation.
    # light_storm stays below RAINY_MOOD threshold (like light_drizzle).
    "light_storm":   {"#storm": 0.50, "#rain": 0.25},  # s≈0.56  below RAINY threshold
    "storm":         {"#storm": 0.75, "#rain": 0.50},  # s≈0.90  triggers RAINY_MOOD
    "storm+rain":    {"#storm": 0.80, "#rain": 0.40},  # s≈0.89  as before
    "heavy_storm":   {"#storm": 1.00, "#rain": 0.60},  # s≈1.17  strongly triggers RAINY
    # -- Other -----------------------------------------------------------
    "fog":           {"#fog": 0.75},                 # T3
    "haze":          {"#fog": 0.25},                 # T1
    "none":          {},                              # no weather signal
}


def weather_output(
    preset: str,
    clear_intensity: float = 1.0,
) -> Optional[SimPolicyOutput]:
    """
    Returns the weather SimPolicyOutput.

    direction       : L2-normalized weather type
    salience        : 1.0 (weather codes are unambiguous)
    intensity       : L2 norm of raw vector (physical severity, unclamped)
    preset          : key in WEATHER_PRESETS
    clear_intensity : multiplier for all #clear values
                      (1.0 = as-is; 2.0 = restore old T4 behavior)
    Returns None for "none" or empty presets.
    """
    raw = dict(WEATHER_PRESETS.get(preset, {}))
    if not raw:
        return None
    if "#clear" in raw and clear_intensity != 1.0:
        raw["#clear"] = raw["#clear"] * clear_intensity
    norm = _l2(raw)
    if norm < 1e-6:
        return None
    direction = {t: w / norm for t, w in raw.items()}
    return SimPolicyOutput(direction=direction, salience=1.0, intensity=norm)


# ======================================================================
#  SECTION 3  Environment Vector & Cosine Similarity
# ======================================================================

def env_vector(
    hour: float,
    doy: int,
    activity: Optional[str],
    weather: str,
    clear_intensity: float = 1.0,
) -> Dict[str, float]:
    """
    Sums all four Policy contributions into a single environment vector.
    Mirrors core/matcher.py aggregation: direction * salience * intensity * ws.

    hour            : current hour (0-23)
    doy             : day of year (1-365)
    activity        : "#focus" | "#chill" | None
    weather         : key in WEATHER_PRESETS, or "none"
    clear_intensity : multiplier forwarded to weather_output
    """
    v: Dict[str, float] = {}
    sources = [
        (time_output(hour),                                    POLICY_WEIGHTS["time"]),
        (season_output(doy),                                   POLICY_WEIGHTS["season"]),
        (activity_output(activity),                            POLICY_WEIGHTS["activity"]),
        (weather_output(weather, clear_intensity=clear_intensity), POLICY_WEIGHTS["weather"]),
    ]
    for output, ws in sources:
        if output is not None:
            for t, w in _contribute(output, ws).items():
                v[t] = v.get(t, 0.0) + w
    return v


def cosine_sim(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Cosine similarity between two tag vectors (mirrors core/matcher.py)."""
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
    na = math.sqrt(sum(a.get(k, 0.0) ** 2 for k in keys))
    nb = math.sqrt(sum(b.get(k, 0.0) ** 2 for k in keys))
    return dot / (na * nb) if na > 1e-6 and nb > 1e-6 else 0.0


def rank_playlists(
    playlists: List[Tuple[str, Dict[str, float]]],
    ev: Dict[str, float],
) -> List[Tuple[str, float]]:
    """Rank all playlists by cosine similarity to ev (descending)."""
    scores = [(name, cosine_sim(ev, tags)) for name, tags in playlists]
    scores.sort(key=lambda x: -x[1])
    return scores


# ======================================================================
#  SECTION 4  User Configuration   <-- PRIMARY EDITING AREA
# ======================================================================

# -- 4a  Playlist Tag Weights -------------------------------------------
#
#  Format: (playlist_name, {tag: weight, ...})
#
#  Weight guidelines vs. effective signal magnitudes:
#
#    Signal              Max ||contrib||    Note
#    ------------------  ---------------   ------
#    #focus / #chill      1.200             ActivityPolicy ws=1.2, steady-state
#    #rain  (mod_rain)    0.975             #rain:0.65 → norm=0.65, × ws:1.5
#    #day   / #night      0.800             TimePolicy ws=0.8, at period peak (sal=1.0)
#    #clear (clear sky)   0.750             #clear:0.50 → norm=0.50, × ws:1.5
#    #spring / ...        0.600             SeasonPolicy ws=0.6, at peak (sal=1.0)
#
#  NOTE: Time/Season magnitudes drop at transitions (sal < 1.0).
#  At transition midpoints, sal ≈ 0.5, so ||contrib|| ≈ half of peak.
#
#  Design rules:
#  1. Never put both #focus and #chill in the same playlist (direction conflict)
#  2. Weather playlists (RAINY_MOOD) should NOT include #clear
#  3. Seasonal playlists use small #day / #clear as time-of-day anchors only

CUSTOM_PLAYLISTS: List[Tuple[str, Dict[str, float]]] = [
    # -- Daytime: focus / chill ------------------------------------------
    ("BRIGHT_FLOW",   {"#focus": 1.0, "#day": 0.9, "#dawn": 0.3, "#clear": 0.3}),
    # #dawn:0.3 makes it competitive at dawn → fog/dawn scenes fall here

    ("CASUAL_ANIME",  {"#chill": 1.0, "#day": 0.9, "#clear": 0.3}),
    # Neutral daytime fallback; light drizzle and overcast also land here

    # -- Sunset ----------------------------------------------------------
    ("SUNSET_GLOW",   {"#sunset": 1.0, "#chill": 0.5, "#clear": 0.3}),
    # No #day/#night — keeps sunset anchor tight (20:00 window)

    # -- Night: focus / chill --------------------------------------------
    ("NIGHT_CHILL",   {"#chill": 1.0, "#night": 0.9, "#clear": 0.2}),
    ("NIGHT_FOCUS",   {"#focus": 1.0, "#night": 0.9, "#clear": 0.2}),

    # -- Weather-driven --------------------------------------------------
    ("RAINY_MOOD",    {"#rain": 1.2, "#storm": 0.4, "#day": 0.3, "#night": 0.3, "#chill": 0.3}),
    # #rain:1.2 > mod_rain signal 0.975 → moderate rain triggers it
    # #storm:0.4 catches thunderstorms; #day+#night = all-hours coverage

    ("WINTER_VIBES",  {"#winter": 1.0, "#sunset": 0.7, "#snow": 0.5, "#chill": 0.3, "#clear": 0.3}),
    # #sunset:0.7 beats SUNSET_GLOW in winter → winter-toned sunset

    # -- Seasonal (new) --------------------------------------------------
    ("SPRING_BLOOM",  {"#spring": 1.0, "#day": 0.5, "#clear": 0.3, "#chill": 0.2}),
    ("SUMMER_GLOW",   {"#summer": 1.0, "#day": 0.5, "#clear": 0.4, "#chill": 0.3}),
    ("AUTUMN_DRIFT",  {"#autumn": 1.0, "#sunset": 0.5, "#day": 0.3, "#chill": 0.3, "#clear": 0.2}),
    # #sunset:0.5 → activates at BOTH autumn AND sunset time simultaneously
]


# -- 4b  Test Scenario Matrix -------------------------------------------
#
#  Format: (label, hour, doy, activity, weather_preset)
#
#  hour    : 0-23  (8=dawn, 14=noon, 20=sunset, 23=late night)
#  doy     : 1-365 (80=spring equinox, 172=summer solstice,
#                   265=autumn equinox, 355=winter solstice;
#                   95=Apr-05,  127=May-07,  310=Nov-06)
#  activity: "#focus" | "#chill" | None (idle)
#  weather : any key from WEATHER_PRESETS, or "none"
#
#  To add a new scenario: append a tuple here.
#  To make --solve recognize it: also add to EXPECTED_WINNERS below.

SCENARIOS: List[Tuple[str, int, int, Optional[str], str]] = [
    # -- Core: day/night x focus/chill (spring, clear) -------------------
    ("Day + focus + clear",             14, 95,  "#focus", "clear"),
    ("Day + chill + clear",             14, 95,  "#chill", "clear"),
    ("Night + focus + clear",           23, 95,  "#focus", "clear"),
    ("Night + chill + clear",           23, 95,  "#chill", "clear"),
    # -- Sunset ----------------------------------------------------------
    ("Sunset + idle + clear",           20, 95,  None,     "clear"),
    ("Sunset + chill + clear",          20, 95,  "#chill", "clear"),
    # -- Dawn ------------------------------------------------------------
    ("Dawn + focus + clear",             8, 95,  "#focus", "clear"),
    # -- Rain (varying intensity) ----------------------------------------
    ("Day + idle + light_drizzle",      14, 95,  None,     "light_drizzle"),
    ("Day + idle + drizzle",            14, 95,  None,     "drizzle"),
    ("Day + idle + light_rain",         14, 95,  None,     "light_rain"),
    ("Day + focus + light_rain",        14, 95,  "#focus", "light_rain"),
    ("Day + idle + mod_rain",           14, 95,  None,     "mod_rain"),
    ("Day + focus + mod_rain",          14, 95,  "#focus", "mod_rain"),
    ("Night + idle + heavy_rain",       23, 95,  None,     "heavy_rain"),
    ("Night + chill + mod_rain",        23, 95,  "#chill", "mod_rain"),
    # -- Storm -----------------------------------------------------------
    ("Night + idle + storm+rain",       23, 95,  None,     "storm+rain"),
    ("Day + idle + storm",              14, 95,  None,     "storm"),
    # -- Cloudy / overcast -----------------------------------------------
    ("Day + idle + few_clouds",         14, 95,  None,     "few_clouds"),
    ("Day + idle + overcast",           14, 95,  None,     "overcast"),
    # -- Fog -------------------------------------------------------------
    ("Dawn + idle + fog",                8, 95,  None,     "fog"),
    # -- Cross-season ----------------------------------------------------
    ("Summer day + chill + clear",      14, 172, "#chill", "clear"),
    ("Autumn sunset + idle + none",     20, 265, None,     "none"),
    ("Autumn sunset + idle + overcast", 20, 265, None,     "overcast"),
    ("Winter sunset + idle + clear",    20, 355, None,     "clear"),
    ("Winter sunset + idle + snow",     20, 355, None,     "light_snow"),
    ("Winter night + idle + snow",      23, 355, None,     "heavy_snow"),
    ("Spring day + idle + none",        14, 95,  None,     "none"),
]


# -- 4c  Expected Winners (oracle for --solve) --------------------------
#
#  key   = exact label string from SCENARIOS
#  value = desired winning playlist name (must exist in CUSTOM_PLAYLISTS)
#
#  Scenarios not listed here are ignored by --solve but still shown
#  in the regular run_scenarios output.

EXPECTED_WINNERS: Dict[str, str] = {
    "Day + focus + clear":              "BRIGHT_FLOW",
    "Day + chill + clear":              "CASUAL_ANIME",
    "Night + focus + clear":            "NIGHT_FOCUS",
    "Night + chill + clear":            "NIGHT_CHILL",
    "Sunset + idle + clear":            "SUNSET_GLOW",
    "Sunset + chill + clear":           "SUNSET_GLOW",
    "Dawn + focus + clear":             "BRIGHT_FLOW",
    "Day + idle + light_drizzle":       "CASUAL_ANIME",   # too light to trigger RAINY
    "Day + idle + drizzle":             "RAINY_MOOD",
    "Day + idle + light_rain":          "RAINY_MOOD",
    "Day + focus + light_rain":         "BRIGHT_FLOW",    # focus overrides light rain
    "Day + idle + mod_rain":            "RAINY_MOOD",
    "Day + focus + mod_rain":           "BRIGHT_FLOW",    # focus still wins at mod_rain
    "Night + idle + heavy_rain":        "RAINY_MOOD",
    "Night + chill + mod_rain":         "RAINY_MOOD",
    "Night + idle + storm+rain":        "RAINY_MOOD",
    "Day + idle + storm":               "RAINY_MOOD",
    "Day + idle + few_clouds":          "CASUAL_ANIME",
    "Day + idle + overcast":            "CASUAL_ANIME",
    "Dawn + idle + fog":                "BRIGHT_FLOW",    # no fog playlist, falls to dawn
    "Summer day + chill + clear":       "SUMMER_GLOW",
    "Autumn sunset + idle + none":      "AUTUMN_DRIFT",
    "Autumn sunset + idle + overcast":  "AUTUMN_DRIFT",
    "Winter sunset + idle + clear":     "WINTER_VIBES",
    "Winter sunset + idle + snow":      "WINTER_VIBES",
    "Winter night + idle + snow":       "WINTER_VIBES",
    "Spring day + idle + none":         "SPRING_BLOOM",
}


# ======================================================================
#  SECTION 5  Reference Playlists  (historical, used by --compare)
# ======================================================================

_BUILTIN_V100: List[Tuple[str, Dict[str, float]]] = [
    # v1.0.0 original tags (before #focus/#chill separation, no seasonal playlists)
    ("BRIGHT_FLOW",  {"#focus": 0.9, "#day": 0.8, "#chill": 0.2, "#clear": 0.4}),
    ("CASUAL_ANIME", {"#chill": 0.7, "#day": 0.9, "#focus": 0.3, "#clear": 0.5}),
    ("SUNSET_GLOW",  {"#sunset": 1.0, "#chill": 0.6, "#day": 0.3, "#night": 0.3}),
    ("NIGHT_CHILL",  {"#chill": 0.9, "#night": 0.8, "#sunset": 0.2, "#focus": 0.2}),
    ("NIGHT_FOCUS",  {"#focus": 1.0, "#night": 0.8, "#chill": 0.1}),
    ("RAINY_MOOD",   {"#rain": 1.0, "#chill": 0.4, "#focus": 0.3}),
    ("WINTER_VIBES", {"#winter": 1.0, "#chill": 0.3, "#sunset": 0.5, "#day": 0.2}),
]


# ======================================================================
#  SECTION 6  Policy Output Diagnostics
# ======================================================================

def show_policy_outputs() -> None:
    """Print per-Policy output vectors at key time/season/weather points."""

    def _fmt_output(output: Optional[SimPolicyOutput], ws: float) -> str:
        if output is None:
            return "None"
        dir_str = ", ".join(f"{t}:{w:.2f}" for t, w in
                            sorted(output.direction.items(), key=lambda x: -x[1]))
        contrib = _contribute(output, ws)
        c_norm = _l2(contrib)
        return (f"dir={{{dir_str}}}  "
                f"sal={output.salience:.3f}  int={output.intensity:.3f}  "
                f"||c||={c_norm:.3f}")

    print("\n" + "=" * 80)
    print("  POLICY OUTPUT DIAGNOSTICS (semantic decomposition)")
    print("=" * 80)

    ws_t = POLICY_WEIGHTS['time']
    print(f"\n-- TimePolicy (ws={ws_t}, day_start=8, night_start=20) --")
    for hour, label in [(8, "08:00 dawn"), (14, "14:00 day"), (17, "17:00 ->sunset"),
                        (20, "20:00 sunset"), (23, "23:00 night"), (2, "02:00 deep night")]:
        print(f"  {label:<22s} {_fmt_output(time_output(hour), ws_t)}")

    ws_s = POLICY_WEIGHTS['season']
    print(f"\n-- SeasonPolicy (ws={ws_s}) --")
    for doy, label in [(80, "Mar-21 spring equinox"), (95, "Apr-05 spring"),
                       (127, "May-07 spring->summer"), (172, "Jun-21 summer solstice"),
                       (265, "Sep-22 autumn equinox"), (310, "Nov-06 autumn->winter"),
                       (355, "Dec-21 winter solstice"), (35, "Feb-04 winter->spring")]:
        print(f"  {label:<28s} {_fmt_output(season_output(doy), ws_s)}")

    ws_w = POLICY_WEIGHTS['weather']
    print(f"\n-- WeatherPolicy (ws={ws_w}) --")
    for preset in ["clear", "few_clouds", "scattered", "overcast",
                   "light_drizzle", "drizzle", "mod_rain", "heavy_rain",
                   "light_snow", "heavy_snow", "storm+rain", "fog", "none"]:
        print(f"  {preset:<18s} {_fmt_output(weather_output(preset), ws_w)}")

    ws_a = POLICY_WEIGHTS['activity']
    print(f"\n-- ActivityPolicy (ws={ws_a}) --")
    for tag in ["#focus", "#chill", None]:
        print(f"  tag={str(tag):<10s} {_fmt_output(activity_output(tag), ws_a)}")


# ======================================================================
#  SECTION 7  Scenario Matching Output
# ======================================================================

def run_scenarios(
    playlists: List[Tuple[str, Dict[str, float]]],
    label: str = "",
    clear_intensity: float = 1.0,
) -> None:
    """Run all SCENARIOS through playlists, print ranked top-3 per scenario."""
    print(f"\n{'=' * 72}")
    print(f"  MATCH RESULTS: {label}")
    if clear_intensity != 1.0:
        print(f"  [#clear base x {clear_intensity:.2f}]")
    print(f"{'=' * 72}")
    print(f"  {'Scenario':<40s} {'Winner':<16s} {'Score':>6s}   2nd / 3rd")
    print(f"  {'-' * 38}   {'-' * 14}  {'-' * 5}   {'-' * 30}")

    for name, hour, doy, act, wx in SCENARIOS:
        ev = env_vector(hour, doy, act, wx, clear_intensity=clear_intensity)
        scores = rank_playlists(playlists, ev)
        winner, top_score = scores[0]
        rest = ", ".join(f"{n}({s:.3f})" for n, s in scores[1:3])
        print(f"  {name:<40s} {winner:<16s} {top_score:>5.3f}   {rest}")


def load_playlists_from_config(path: str) -> List[Tuple[str, Dict[str, float]]]:
    """Load playlist definitions from a scheduler_config.json file."""
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return [(pl["name"], pl["tags"]) for pl in cfg.get("playlists", [])]


# ======================================================================
#  SECTION 8  Reverse Solver: Expected Mappings -> Ideal Playlist Tags
# ======================================================================
#
#  Algorithm: for each playlist, compute the centroid (average) of the
#  env_vectors from all its assigned scenarios, then normalize to max=1.0.
#  The centroid direction is the cosine-similarity-optimal tag vector.
#
#  Known limitation: if most SCENARIOS share the same season (e.g. doy=95
#  for spring), every playlist's centroid will contain a #spring component.
#  Manual tuning's value is deliberately removing such "test-set bias" to
#  make playlists season-agnostic where intended (e.g. RAINY_MOOD).

def solve_playlists(
    clear_intensity: float = 1.0,
    threshold: float = 0.05,
) -> List[Tuple[str, Dict[str, float]]]:
    """
    Derive ideal playlist tags from EXPECTED_WINNERS via centroid method.

    clear_intensity : forwarded to env_vector for all scenarios
    threshold       : tags with centroid value below this are pruned (denoising)
    Returns list of (playlist_name, {tag: normalized_weight}), sorted by name.
    """
    # Pre-compute env vectors for all scenarios
    scenario_envs: Dict[str, Dict[str, float]] = {
        name: env_vector(hour, doy, act, wx, clear_intensity=clear_intensity)
        for name, hour, doy, act, wx in SCENARIOS
    }

    # Group scenarios by expected winning playlist
    groups: Dict[str, List[Dict[str, float]]] = defaultdict(list)
    for sc_name, pl_name in EXPECTED_WINNERS.items():
        if sc_name in scenario_envs:
            groups[pl_name].append(scenario_envs[sc_name])

    results: List[Tuple[str, Dict[str, float]]] = []
    for pl_name in sorted(groups.keys()):
        envs = groups[pl_name]
        all_tags: set = set().union(*envs)

        # Centroid: mean value per tag across all assigned scenarios
        centroid = {
            tag: sum(ev.get(tag, 0.0) for ev in envs) / len(envs)
            for tag in all_tags
        }

        # Prune low-weight noise, normalize to max=1.0
        sparse = {t: w for t, w in centroid.items() if abs(w) > threshold}
        if sparse:
            max_w = max(abs(w) for w in sparse.values())
            if max_w > 1e-6:
                sparse = {t: round(w / max_w, 2)
                          for t, w in sparse.items() if w > 0}

        results.append((pl_name, sparse))

    return results


def show_solved(clear_intensity: float = 1.0) -> None:
    """Run solver, validate against EXPECTED_WINNERS, print comparison + JSON."""
    solved = solve_playlists(clear_intensity=clear_intensity)
    manual_map = {n: t for n, t in CUSTOM_PLAYLISTS}

    print(f"\n{'=' * 72}")
    print("  SOLVED PLAYLIST TAGS  (centroid of assigned scenario env-vectors)")
    print(f"{'=' * 72}\n")

    for name, tags in solved:
        tag_str = ", ".join(f"{t}:{w}" for t, w in sorted(tags.items(), key=lambda x: -x[1]))
        print(f"  {name:<16s} {{ {tag_str} }}")
        if (manual := manual_map.get(name)):
            m_str = ", ".join(f"{t}:{w}" for t, w in sorted(manual.items(), key=lambda x: -x[1]))
            print(f"  {'(manual)':<16s} {{ {m_str} }}")
        print()

    # Validate solver output against EXPECTED_WINNERS
    print(f"  {'-' * 70}")
    print(f"  {'Scenario':<40s} {'Expected':<16s} {'Got':<16s} {'Score':>5s}  OK?")
    print(f"  {'-' * 38}   {'-' * 14}  {'-' * 14}  {'-' * 5}  {'---'}")

    errors = 0
    for name, hour, doy, act, wx in SCENARIOS:
        expected = EXPECTED_WINNERS.get(name, "?")
        ev = env_vector(hour, doy, act, wx, clear_intensity=clear_intensity)
        scores = rank_playlists(solved, ev)
        winner, score = scores[0]
        ok = "v" if winner == expected else "x"
        if winner != expected:
            errors += 1
        print(f"  {name:<40s} {expected:<16s} {winner:<16s} {score:>5.3f}  {ok}")

    total = len(SCENARIOS)
    print(f"\n  Result: {total - errors}/{total} correct", end="")
    print(f"  [!] {errors} mismatch(es)" if errors else "  -- all pass")

    print(f"\n  {'-' * 70}")
    print("  JSON (paste into scheduler_config.json playlists array):\n")
    print(json.dumps([{"name": n, "tags": t} for n, t in solved], indent=2, ensure_ascii=False))


# ======================================================================
#  SECTION 9  CLI Entry Point
# ======================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline Policy -> playlist match simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python misc/sim_match.py                          # run CUSTOM_PLAYLISTS (default)
  python misc/sim_match.py --config cfg.json        # load playlists from config file
  python misc/sim_match.py --compare                # compare old v1.0.0 vs CUSTOM_PLAYLISTS
  python misc/sim_match.py --solve                  # reverse-solve ideal tags
  python misc/sim_match.py --no-diag                # skip Policy diagnostics
  python misc/sim_match.py --clear-cap 2.0 --solve  # simulate old T4 clear behavior
""")
    parser.add_argument("--config", "-c", metavar="PATH",
                        help="Load playlists from scheduler_config.json (overrides CUSTOM_PLAYLISTS)")
    parser.add_argument("--no-diag", action="store_true",
                        help="Skip Policy output diagnostics section")
    parser.add_argument("--compare", action="store_true",
                        help="Compare v1.0.0 builtin tags versus CUSTOM_PLAYLISTS side-by-side")
    parser.add_argument("--solve", action="store_true",
                        help="Reverse-solve ideal playlist tags from EXPECTED_WINNERS")
    parser.add_argument("--clear-cap", type=float, metavar="FACTOR", default=1.0,
                        help="Multiply all #clear intensities by FACTOR (default: 1.0). "
                             "Use 2.0 to simulate old T4 behavior.")
    args = parser.parse_args()

    ci = args.clear_cap

    if not args.no_diag:
        show_policy_outputs()

    if args.compare:
        run_scenarios(_BUILTIN_V100, "OLD v1.0.0 tags", clear_intensity=ci)
        run_scenarios(CUSTOM_PLAYLISTS, "CUSTOM_PLAYLISTS (optimized)", clear_intensity=ci)
    elif args.solve:
        show_solved(clear_intensity=ci)
    elif args.config:
        playlists = load_playlists_from_config(args.config)
        run_scenarios(playlists, f"FROM {args.config}", clear_intensity=ci)
    else:
        run_scenarios(CUSTOM_PLAYLISTS, "CUSTOM_PLAYLISTS", clear_intensity=ci)


if __name__ == "__main__":
    main()