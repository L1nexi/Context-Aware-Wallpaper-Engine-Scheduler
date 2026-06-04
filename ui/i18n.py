import locale
import logging
from typing import Literal

logger = logging.getLogger("WEScheduler.I18n")

type Lang = Literal["zh", "en"]

_ZH: dict[str, str] = {
    "status_running": "调度状态: 运行中",
    "status_paused": "调度状态: 已暂停",
    "status_paused_remaining": "调度状态: 已暂停 (剩余 {remaining})",
    "tray_active": "当前活跃: {playlist}",
    "tray_match": "当前匹配: {playlist}",
    "tray_outside_configured_playlists": "不在已配置播单中",
    "tray_no_schedulable_target": "无可调度目标",
    "tray_apply_match": "应用匹配: {playlist}",
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
    "open_config": "打开配置",
    "open_logs": "打开日志",
    "exit": "退出",
    "dialog_title": "自定义暂停时长",
    "days": "天:",
    "hours": "小时:",
    "minutes": "分钟:",
    "ok": "确定",
    "cancel": "取消",
    "startup_error_title": "启动失败",
    "startup_error_body": "调度器启动失败。\n\n{detail}\n\n请查看日志获取详情。",
    "reload_error_title": "配置重载失败",
    "reload_error_body": "更新后的配置无效。\n\n{detail}\n\n调度器将继续使用上一份有效的运行时配置。",
    "dashboard_show": "诊断",
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
    "config_tools_title": "WEScheduler 配置工具",
    "config_tools_validate": "验证配置",
    "config_tools_detect_we": "检测 Wallpaper Engine",
    "config_tools_scan_playlists": "扫描 Wallpaper Engine 播放列表",
    "config_tools_exit": "退出",
    "config_tools_unknown_option": "未知选项。请输入 1、2、3 或 q。",
    "config_tools_ok": "OK",
    "config_tools_failed": "失败",
    "config_tools_code": "错误码",
    "config_tools_config_folder": "配置目录:",
    "config_tools_resolved_we": "已解析的 Wallpaper Engine:",
    "config_tools_playlists": "播放列表:",
    "config_tools_playlists_count": "播放列表 ({count}):",
    "config_tools_enabled_policies": "启用的策略:",
    "config_tools_none": "无",
    "config_tools_auto": "<自动>",
    "config_tools_not_found": "<未找到>",
    "config_tools_unresolved": "<未解析>",
    "config_tools_configured_value": "配置值:",
    "config_tools_resolved_executable": "已解析的可执行文件:",
    "config_tools_we_config_json": "Wallpaper Engine config.json:",
    "config_tools_read_configured_value_failed": "读取配置值失败: {detail}",
    "config_tools_no_playlists_found": "未在 Wallpaper Engine 中找到播放列表。",
    "config_tools_copy_ready_snippet": "可复制的 playlists.yaml 片段:",
    "config_tools_error_configured_path_read_failed": "无法从 scheduler.yaml 读取 Wallpaper Engine 路径配置。",
    "config_tools_error_we_exe_not_found": "未找到 Wallpaper Engine 可执行文件。",
    "config_tools_error_we_exe_hint": "请在 scheduler.yaml 中设置 runtime.wallpaper_engine_path，或确认可通过 Steam 自动检测 Wallpaper Engine。",
    "config_tools_error_we_config_not_found": "未找到 Wallpaper Engine config.json。",
    "config_tools_error_we_config_hint": "请确认 Wallpaper Engine 至少已启动过一次。",
    "config_tools_error_we_config_read_failed": "读取 Wallpaper Engine config.json 失败:",
    "config_tools_error_we_config_unexpected_format": "Wallpaper Engine config.json 格式不符合预期。",
    "config_tools_error_unknown": "错误: {error}",
}

_EN: dict[str, str] = {
    "status_running": "Status: Running",
    "status_paused": "Status: Paused",
    "status_paused_remaining": "Status: Paused ({remaining} left)",
    "tray_active": "Active: {playlist}",
    "tray_match": "Match: {playlist}",
    "tray_outside_configured_playlists": "Outside configured playlists",
    "tray_no_schedulable_target": "No schedulable target found",
    "tray_apply_match": "Apply Match: {playlist}",
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
    "open_config": "Open Config",
    "open_logs": "Open Logs",
    "exit": "Exit",
    "dialog_title": "Custom Pause Duration",
    "days": "Days:",
    "hours": "Hours:",
    "minutes": "Minutes:",
    "ok": "OK",
    "cancel": "Cancel",
    "startup_error_title": "Startup Failed",
    "startup_error_body": "Scheduler failed to start.\n\n{detail}\n\nCheck the log for details.",
    "reload_error_title": "Config Reload Failed",
    "reload_error_body": "The updated config is invalid.\n\n{detail}\n\nThe scheduler will continue using the previous valid runtime.",
    "dashboard_show": "Diagnostics",
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
    "config_tools_title": "WEScheduler Config Tools",
    "config_tools_validate": "Validate config",
    "config_tools_detect_we": "Detect Wallpaper Engine",
    "config_tools_scan_playlists": "Scan Wallpaper Engine playlists",
    "config_tools_exit": "Exit",
    "config_tools_unknown_option": "Unknown option. Enter 1, 2, 3, or q.",
    "config_tools_ok": "OK",
    "config_tools_failed": "FAILED",
    "config_tools_code": "code",
    "config_tools_config_folder": "Config folder:",
    "config_tools_resolved_we": "Resolved Wallpaper Engine:",
    "config_tools_playlists": "Playlists:",
    "config_tools_playlists_count": "Playlists ({count}):",
    "config_tools_enabled_policies": "Enabled policies:",
    "config_tools_none": "none",
    "config_tools_auto": "<auto>",
    "config_tools_not_found": "<not found>",
    "config_tools_unresolved": "<unresolved>",
    "config_tools_configured_value": "Configured value:",
    "config_tools_resolved_executable": "Resolved executable:",
    "config_tools_we_config_json": "Wallpaper Engine config.json:",
    "config_tools_read_configured_value_failed": "Failed to read configured value: {detail}",
    "config_tools_no_playlists_found": "No playlists found in Wallpaper Engine.",
    "config_tools_copy_ready_snippet": "Copy-ready playlists.yaml snippet:",
    "config_tools_error_configured_path_read_failed": "Failed to read configured Wallpaper Engine path from scheduler.yaml.",
    "config_tools_error_we_exe_not_found": "Wallpaper Engine executable not found.",
    "config_tools_error_we_exe_hint": "Set runtime.wallpaper_engine_path in scheduler.yaml, or make sure Wallpaper Engine "
    "can be auto-detected from Steam.",
    "config_tools_error_we_config_not_found": "Wallpaper Engine config.json not found.",
    "config_tools_error_we_config_hint": "Make sure Wallpaper Engine has been launched at least once.",
    "config_tools_error_we_config_read_failed": "Failed to read Wallpaper Engine config.json:",
    "config_tools_error_we_config_unexpected_format": "Wallpaper Engine config.json has an unexpected format.",
    "config_tools_error_unknown": "Error: {error}",
}

_TRANSLATIONS: dict[Lang, dict[str, str]] = {
    "zh": _ZH,
    "en": _EN,
}


def _detect_lang() -> str:
    try:
        loc, _ = locale.getlocale()
    except Exception:
        return "en"

    return "zh" if loc and loc.startswith("zh") else "en"


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
