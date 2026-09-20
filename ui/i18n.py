import locale
import logging
import os
from typing import Literal

from core.models.scene import SceneId

logger = logging.getLogger("WEScheduler.I18n")

type Lang = Literal["zh", "en"]

_ZH: dict[str, str] = {
    "status_running": "调度状态: 运行中",
    "status_paused": "调度状态: 已暂停",
    "status_paused_remaining": "调度状态: 已暂停 (剩余 {remaining})",
    "tray_active": "当前活跃: {scene}",
    "tray_match": "当前匹配: {scene}",
    "tray_outside_configured_scenes": "不在已配置场景中",
    "tray_no_schedulable_target": "无可调度目标",
    "tray_apply_match": "应用匹配: {scene}",
    "scene_day_work": "日间工作",
    "scene_day_leisure": "日间休闲",
    "scene_night_work": "夜间工作",
    "scene_night_leisure": "夜间休闲",
    "scene_spring": "春季",
    "scene_summer": "夏季",
    "scene_autumn": "秋季",
    "scene_winter": "冬季",
    "scene_sunset": "黄昏",
    "scene_rain": "雨天",
    "tray_unavailable": "不可用",
    "resume": "恢复",
    "pause": "暂停...",
    "pause_indefinitely": "保持暂停",
    "pause_30m": "30 分钟",
    "pause_2h": "2 小时",
    "pause_12h": "12 小时",
    "pause_24h": "24 小时",
    "pause_48h": "48 小时",
    "pause_1w": "1 周",
    "pause_custom": "自定义...",
    "apply_current_match_now": "立即按当前上下文调度",
    "open_logs": "打开日志",
    "about": "关于",
    "about_title": "关于 WEScheduler",
    "about_body": "WEScheduler\n版本：{version}",
    "exit": "退出",
    "dialog_title": "自定义暂停时长",
    "days": "天:",
    "hours": "小时:",
    "minutes": "分钟:",
    "ok": "确定",
    "cancel": "取消",
    "startup_error_title": "启动失败",
    "startup_error_body": "调度器启动失败。\n\n{detail}\n\n请查看日志获取详情。",
    "dashboard_show": "诊断",
    "tick_history_export": "导出近期调度记录",
    "dashboard_title": "WEScheduler 诊断",
    "dashboard_running": "运行中",
    "dashboard_paused": "已暂停",
    "dashboard_fullscreen": "全屏",
    "dashboard_waiting": "等待中...",
    "dashboard_no_data": "暂无数据",
    "dashboard_loading": "加载中...",
    "dashboard_similarity": "匹配度",
    "dashboard_gap": "置信度差值",
    "dashboard_magnitude": "信号强度",
    "dashboard_tags": "主要标签",
    "dashboard_context": "环境信息",
    "dashboard_active_window": "活动窗口",
    "dashboard_idle": "空闲",
    "dashboard_cpu": "CPU",
    "dashboard_connection_lost": "调度器连接丢失。窗口将在 {seconds} 秒后关闭。",
}

_EN: dict[str, str] = {
    "status_running": "Status: Running",
    "status_paused": "Status: Paused",
    "status_paused_remaining": "Status: Paused ({remaining} left)",
    "tray_active": "Active: {scene}",
    "tray_match": "Match: {scene}",
    "tray_outside_configured_scenes": "Outside configured scenes",
    "tray_no_schedulable_target": "No schedulable target found",
    "tray_apply_match": "Apply Match: {scene}",
    "scene_day_work": "Day Work",
    "scene_day_leisure": "Day Leisure",
    "scene_night_work": "Night Work",
    "scene_night_leisure": "Night Leisure",
    "scene_spring": "Spring",
    "scene_summer": "Summer",
    "scene_autumn": "Autumn",
    "scene_winter": "Winter",
    "scene_sunset": "Sunset",
    "scene_rain": "Rain",
    "tray_unavailable": "Unavailable",
    "resume": "Resume",
    "pause": "Pause...",
    "pause_indefinitely": "Indefinitely",
    "pause_30m": "30 Minutes",
    "pause_2h": "2 Hours",
    "pause_12h": "12 Hours",
    "pause_24h": "24 Hours",
    "pause_48h": "48 Hours",
    "pause_1w": "1 Week",
    "pause_custom": "Custom...",
    "apply_current_match_now": "Schedule From Current Context Now",
    "open_logs": "Open Logs",
    "about": "About",
    "about_title": "About WEScheduler",
    "about_body": "WEScheduler\nVersion: {version}",
    "exit": "Exit",
    "dialog_title": "Custom Pause Duration",
    "days": "Days:",
    "hours": "Hours:",
    "minutes": "Minutes:",
    "ok": "OK",
    "cancel": "Cancel",
    "startup_error_title": "Startup Failed",
    "startup_error_body": "Scheduler failed to start.\n\n{detail}\n\nCheck the log for details.",
    "dashboard_show": "Diagnostics",
    "tick_history_export": "Export recent schedule history",
    "dashboard_title": "WEScheduler Diagnostics",
    "dashboard_running": "Running",
    "dashboard_paused": "Paused",
    "dashboard_fullscreen": "Fullscreen",
    "dashboard_waiting": "Waiting...",
    "dashboard_no_data": "No data",
    "dashboard_loading": "Loading...",
    "dashboard_similarity": "Similarity",
    "dashboard_gap": "Confidence Gap",
    "dashboard_magnitude": "Signal Strength",
    "dashboard_tags": "Top Tags",
    "dashboard_context": "Context",
    "dashboard_active_window": "Active Window",
    "dashboard_idle": "Idle",
    "dashboard_cpu": "CPU",
    "dashboard_connection_lost": "Scheduler connection lost. This window will close in {seconds} seconds.",
}

_TRANSLATIONS: dict[Lang, dict[str, str]] = {
    "zh": _ZH,
    "en": _EN,
}


def _detect_lang() -> str:
    for var in ("LANGUAGE", "LANG", "LC_ALL", "LC_MESSAGES"):
        val = os.environ.get(var, "")
        if val:
            return "zh" if val.startswith("zh") else "en"

    try:
        locale.setlocale(locale.LC_ALL, "")
        loc, _ = locale.getlocale()
    except Exception:
        return "en"

    return "zh" if loc and (loc.startswith("zh") or "chinese" in loc.lower()) else "en"


def _validate_translations() -> None:
    en_keys = set(_EN)
    zh_keys = set(_ZH)

    missing_in_zh = en_keys - zh_keys
    extra_in_zh = zh_keys - en_keys

    if missing_in_zh:
        raise ValueError(f"Missing zh translations: {sorted(missing_in_zh)}")

    if extra_in_zh:
        raise ValueError(f"Extra zh translations: {sorted(extra_in_zh)}")


_validate_translations()

current_lang: str = _detect_lang()

logger.debug("Detected language = %s", current_lang)

_VALID_LANGS: set[str] = set(_TRANSLATIONS)


def set_language(lang: str | None) -> None:
    """Override the current language.``None`` keeps the auto-detected value.

    A non-null value set the global ``current_lang``.
    Raises: ValueError if the language is not supported.
    """
    global current_lang
    if lang is None:
        return
    if lang not in _VALID_LANGS:
        raise ValueError(f"Unsupported language {lang!r}; expected one of {sorted(_VALID_LANGS)}")
    current_lang = lang
    logger.info("Language overridden to: %s", lang)


def t(key: str, **kwargs) -> str:
    """
    Return the translated text for key.

    Raises:
        ValueError: If the current language or translation key is invalid.
        KeyError: If a required format placeholder is missing.
    """
    lang_table = _TRANSLATIONS.get(current_lang)

    if lang_table is None:
        raise ValueError("Unsupported language")

    text = lang_table.get(key)

    if text is None:
        logger.error("Invalid translation key : %s", key)
        raise ValueError(f"Invalid translation key {key}")

    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            logger.error("Fail to format translation key: %s", text)
            raise

    return text


def scene_name(scene_id: SceneId) -> str:
    return t(f"scene_{scene_id.value}")
