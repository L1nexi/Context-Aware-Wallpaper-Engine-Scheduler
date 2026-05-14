from __future__ import annotations

from utils.config_tools import (
    ConfigSummary,
    ConfigValidationResult,
    PlaylistScanResult,
    detect_wallpaper_engine,
    render_playlists_yaml_snippet,
    scan_wallpaper_engine_playlists,
    validate_config,
)
from utils.i18n import t


def run_config_tools_tui(config_dir: str) -> int:
    while True:
        _print_menu()
        try:
            choice = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if choice in ("q", "Q"):
            return 0
        if choice == "1":
            _run_validate(config_dir)
        elif choice == "2":
            _run_detect(config_dir)
        elif choice == "3":
            _run_scan(config_dir)
        elif choice == "":
            continue
        else:
            print(t("config_tools_unknown_option"))


def _print_menu() -> None:
    print()
    print(t("config_tools_title"))
    print("------------------------")
    print(f"1. {t('config_tools_validate')}")
    print(f"2. {t('config_tools_detect_we')}")
    print(f"3. {t('config_tools_scan_playlists')}")
    print(f"q. {t('config_tools_exit')}")

def _run_validate(config_dir: str) -> None:
    result = validate_config(config_dir)
    print()

    if result.ok and result.summary is not None:
        _print_validation_success(result.summary)
    else:
        _print_validation_failure(result)

def _print_validation_success(summary: ConfigSummary) -> None:
    we_path_str = summary.resolved_we_path or t("config_tools_unresolved")
    policies_str = (
        ", ".join(summary.enabled_policies)
        if summary.enabled_policies
        else t("config_tools_none")
    )

    print(t("config_tools_ok"))
    print()
    print(t("config_tools_config_folder"))
    print(f"  {summary.config_dir}")
    print()
    print(t("config_tools_resolved_we"))
    print(f"  {we_path_str}")
    print()
    print(t("config_tools_playlists"))
    print(f"  {summary.playlist_count}")
    print()
    print(t("config_tools_enabled_policies"))
    print(f"  {policies_str}")

def _print_validation_failure(result: ConfigValidationResult) -> None:
    print(t("config_tools_failed"))
    if not result.issues:
        return

    print()
    for issue in result.issues:
        print(issue.render())
        print(f"  {t('config_tools_code')}: {issue.code}")
        print()

def _run_detect(config_dir: str) -> None:
    result = detect_wallpaper_engine(config_dir)
    print()

    if result.configured_read_error is not None:
        print(
            t(
                "config_tools_read_configured_value_failed",
                detail=result.configured_read_error,
            )
        )
        return

    configured_display = result.configured_value or t("config_tools_auto")
    print(t("config_tools_configured_value"))
    print(f"  {configured_display}")
    print()

    resolved_display = result.resolved_executable or t("config_tools_not_found")
    print(t("config_tools_resolved_executable"))
    print(f"  {resolved_display}")
    print()

    config_json_display = result.we_config_json or t("config_tools_not_found")
    print(t("config_tools_we_config_json"))
    print(f"  {config_json_display}")

def _run_scan(config_dir: str) -> None:
    result = scan_wallpaper_engine_playlists(config_dir)
    print()

    if not result.ok:
        _print_scan_error(result)
        return

    if not result.playlists:
        print(t("config_tools_no_playlists_found"))
        return

    print(t("config_tools_playlists_count", count=len(result.playlists)))
    for name in result.playlists:
        print(f"  - {name}")

    snippet = render_playlists_yaml_snippet(result.playlists)
    print()
    print(t("config_tools_copy_ready_snippet"))
    print()
    print(snippet)

def _print_scan_error(result: PlaylistScanResult) -> None:
    error = result.error or "unknown error"

    if error == "configured_wallpaper_engine_path_read_failed":
        print(t("config_tools_error_configured_path_read_failed"))
    elif error == "wallpaper_engine_executable_not_found":
        print(t("config_tools_error_we_exe_not_found"))
        print()
        print(t("config_tools_error_we_exe_hint"))
    elif error == "wallpaper_engine_config_not_found":
        print(t("config_tools_error_we_config_not_found"))
        print()
        print(t("config_tools_error_we_config_hint"))
    elif error == "wallpaper_engine_config_read_failed":
        print(t("config_tools_error_we_config_read_failed"))
        print(f"  {result.we_config_json or t('config_tools_not_found')}")
    elif error == "unexpected_wallpaper_engine_config_format":
        print(t("config_tools_error_we_config_unexpected_format"))
        print(f"  {result.we_config_json or t('config_tools_not_found')}")
    else:
        print(t("config_tools_error_unknown", error=error))