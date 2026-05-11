"""
Lightweight internationalisation (i18n) module.

Detects the OS locale at import time and exposes a single ``t(key, **kwargs)``
function used by the UI layer to look up translated strings.

Currently supported locales:
  - ``en`` — English (fallback)
  - ``zh`` — Simplified Chinese

Adding a new locale:
  1. Add a new column in ``_STRINGS`` for each key.
  2. (Optional) adjust ``_detect_lang()`` if the locale prefix differs.
"""

import locale
import logging
from typing import Dict

logger = logging.getLogger("WEScheduler.I18n")

# ── Translation table ────────────────────────────────────────────
# Key -> { lang_prefix: translated_string }
# Strings may contain ``{placeholder}`` for runtime formatting.

_STRINGS: Dict[str, Dict[str, str]] = {
    # -- Tray: status --
    "status_running":          {"en": "Status: Running",                     "zh": "状态: 运行中"},
    "status_paused":           {"en": "Status: Paused",                      "zh": "状态: 已暂停"},
    "status_paused_remaining": {"en": "Status: Paused ({remaining} left)",   "zh": "状态: 已暂停 (剩余 {remaining})"},

    # -- Tray: actions --
    "resume":                  {"en": "Resume",            "zh": "恢复"},
    "pause":                   {"en": "Pause...",          "zh": "暂停..."},
    "pause_indefinitely":      {"en": "Indefinitely",      "zh": "保持暂停"},
    "pause_30m":               {"en": "30 Minutes",        "zh": "30 分钟"},
    "pause_2h":                {"en": "2 Hours",           "zh": "2 小时"},
    "pause_12h":               {"en": "12 Hours",          "zh": "12 小时"},
    "pause_24h":               {"en": "24 Hours",          "zh": "24 小时"},
    "pause_48h":               {"en": "48 Hours",          "zh": "48 小时"},
    "pause_1w":                {"en": "1 Week",            "zh": "1 周"},
    "pause_custom":            {"en": "Custom...",         "zh": "自定义..."},
    "open_config":             {"en": "Open Config",       "zh": "打开配置"},
    "open_logs":               {"en": "Open Logs",         "zh": "打开日志"},
    "exit":                    {"en": "Exit",              "zh": "退出"},

    # -- Custom pause dialog --
    "dialog_title":            {"en": "Custom Pause Duration",  "zh": "自定义暂停时长"},
    "days":                    {"en": "Days:",             "zh": "天:"},
    "hours":                   {"en": "Hours:",            "zh": "小时:"},
    "minutes":                 {"en": "Minutes:",          "zh": "分钟:"},
    "ok":                      {"en": "OK",                "zh": "确定"},
    "cancel":                  {"en": "Cancel",            "zh": "取消"},

    # -- Startup error dialog --
    "startup_error_title":     {"en": "Startup Failed",                    "zh": "启动失败"},
    "startup_error_body":      {"en": "Scheduler failed to start.\n\n{detail}\n\nCheck the log for details.",
                                "zh": "调度器启动失败。\n\n{detail}\n\n请查看日志获取详情。"},
    "reload_error_title":      {"en": "Config Reload Failed",              "zh": "配置重载失败"},
    "reload_error_body":       {
        "en": "The updated config is invalid.\n\n{detail}\n\nThe scheduler will continue using the previous valid runtime.",
        "zh": "更新后的配置无效。\n\n{detail}\n\n调度器将继续使用上一份有效的运行时配置。",
    },

    # -- Dashboard --
    "dashboard_show":          {"en": "Dashboard",              "zh": "仪表盘"},
    "dashboard_title":         {"en": "WEScheduler Dashboard",  "zh": "WEScheduler 仪表盘"},
    "dashboard_running":       {"en": "Running",                "zh": "运行中"},
    "dashboard_paused":        {"en": "Paused",                 "zh": "已暂停"},
    "dashboard_fullscreen":    {"en": "Fullscreen",             "zh": "全屏"},
    "dashboard_waiting":       {"en": "Waiting...",             "zh": "等待中..."},
    "dashboard_no_data":       {"en": "No data",                "zh": "暂无数据"},
    "dashboard_loading":       {"en": "Loading...",             "zh": "加载中..."},
    "dashboard_similarity":    {"en": "Similarity",             "zh": "匹配度"},
    "dashboard_gap":           {"en": "Confidence Gap",         "zh": "置信度差值"},
    "dashboard_magnitude":     {"en": "Signal Strength",        "zh": "信号强度"},
    "dashboard_tags":          {"en": "Top Tags",               "zh": "主要标签"},
    "dashboard_context":       {"en": "Context",                "zh": "环境信息"},
    "dashboard_active_window": {"en": "Active Window",          "zh": "活动窗口"},
    "dashboard_idle":          {"en": "Idle",                   "zh": "空闲"},
    "dashboard_cpu":           {"en": "CPU",                    "zh": "CPU"},
    "dashboard_connection_lost": {
        "en": "Scheduler connection lost. This window will close in {seconds} seconds.",
        "zh": "调度器连接丢失。窗口将在 {seconds} 秒后关闭。",
    },
}


# ── Locale detection ─────────────────────────────────────────────

def _detect_lang() -> str:
    """Return a language prefix (``'zh'`` or ``'en'``) based on the OS locale."""
    try:
        loc, _ = locale.getdefaultlocale()
        if loc and loc.startswith("zh"):
            return "zh"
    except Exception:
        pass
    return "en"


_current_lang: str = _detect_lang()

logger.debug("I18n: detected language = %s", _current_lang)


# ── Public API ───────────────────────────────────────────────────

def t(key: str, **kwargs) -> str:
    """
    Look up *key* in the translation table for the current locale.

    Any extra ``kwargs`` are passed to ``str.format()`` on the result,
    allowing placeholders like ``{remaining}`` in the translated string.

    Returns *key* unchanged if no translation is found.
    """
    entry = _STRINGS.get(key)
    if not entry:
        return key
    text = entry.get(_current_lang, entry.get("en", key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass
    return text
