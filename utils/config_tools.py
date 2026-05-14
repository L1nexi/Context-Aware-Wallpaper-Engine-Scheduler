from __future__ import annotations

import getpass
import json
import os
import yaml
from dataclasses import dataclass, field

from utils.config_errors import ConfigIssue, ConfigLoadError
from utils.config_loader import ConfigLoader
from utils.we_path import find_we_config_json, resolve_wallpaper_engine_path


@dataclass
class ConfigSummary:
    config_dir: str
    resolved_we_path: str | None
    playlist_count: int
    enabled_policies: list[str]


@dataclass
class ConfigValidationResult:
    ok: bool
    issues: list[ConfigIssue] = field(default_factory=list)
    summary: ConfigSummary | None = None


@dataclass
class WEDetectionResult:
    configured_value: str | None = None
    configured_read_error: str | None = None
    resolved_executable: str | None = None
    we_config_json: str | None = None


@dataclass
class PlaylistScanResult:
    ok: bool
    we_config_json: str | None = None
    playlists: list[str] = field(default_factory=list)
    error: str | None = None


def validate_config(config_dir: str) -> ConfigValidationResult:
    loader = ConfigLoader(config_dir)
    try:
        config = loader.load_verified_config()
    except ConfigLoadError as exc:
        return ConfigValidationResult(ok=False, issues=exc.issues)
    except FileNotFoundError:
        return ConfigValidationResult(
            ok=False,
            issues=[
                ConfigIssue(
                    source_file="scheduler.yaml",
                    field_path=(),
                    message=f"Config directory not found: {config_dir}",
                    code="config_dir_not_found",
                )
            ],
        )

    enabled_policies = [
        name for name in type(config.policies).model_fields
        if getattr(config.policies, name).enabled
    ]

    return ConfigValidationResult(
        ok=True,
        summary=ConfigSummary(
            config_dir=os.path.abspath(config_dir),
            resolved_we_path=config.wallpaper_engine_path or None,
            playlist_count=len(config.playlists),
            enabled_policies=enabled_policies,
        ),
    )


def _detect_wallpaper_engine(config_dir: str) -> WEDetectionResult:
    configured_value: str | None = None
    configured_read_error: str | None = None

    try:
        configured_value = ConfigLoader.load_configured_wallpaper_engine_path(config_dir)
    except Exception as exc:
        configured_read_error = str(exc)

    if configured_read_error is not None:
        return WEDetectionResult(configured_read_error=configured_read_error)

    resolved = resolve_wallpaper_engine_path(configured_value or "")
    config_json = find_we_config_json(resolved)

    return WEDetectionResult(
        configured_value=configured_value,
        resolved_executable=resolved,
        we_config_json=config_json,
    )

def detect_wallpaper_engine(config_dir: str) -> WEDetectionResult:
    return _detect_wallpaper_engine(config_dir)

def scan_wallpaper_engine_playlists(config_dir: str) -> PlaylistScanResult:
    detection = _detect_wallpaper_engine(config_dir)

    if detection.configured_read_error is not None:
        return PlaylistScanResult(
            ok=False,
            we_config_json=None,
            error="configured_wallpaper_engine_path_read_failed",
        )

    if detection.resolved_executable is None:
        return PlaylistScanResult(
            ok=False,
            we_config_json=None,
            error="wallpaper_engine_executable_not_found",
        )

    config_json_path = detection.we_config_json
    if config_json_path is None:
        return PlaylistScanResult(
            ok=False,
            we_config_json=None,
            error="wallpaper_engine_config_not_found",
        )

    try:
        with open(config_json_path, "r", encoding="utf-8") as f:
            we_data = json.load(f)
    except Exception:
        return PlaylistScanResult(
            ok=False,
            we_config_json=config_json_path,
            error="wallpaper_engine_config_read_failed",
        )

    if not isinstance(we_data, dict):
        return PlaylistScanResult(
            ok=False,
            we_config_json=config_json_path,
            error="unexpected_wallpaper_engine_config_format",
        )

    username = getpass.getuser()
    user_entry = we_data.get(username)
    if isinstance(user_entry, dict):
        general = user_entry.get("general", {})
        playlists = general.get("playlists", []) if isinstance(general, dict) else []
    else:
        playlists = []

    names: list[str] = []
    for p in playlists:
        if isinstance(p, dict) and "name" in p and isinstance(p["name"], str):
            name = p["name"].strip()
            if name:
                names.append(name)

    return PlaylistScanResult(
        ok=True,
        we_config_json=config_json_path,
        playlists=names,
    )


def render_playlists_yaml_snippet(names: list[str]) -> str:
    if not names:
        return ""

    data = {
        "playlists": {
            name: {"tags": {}}
            for name in names
        }
    }
    return yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).rstrip()
