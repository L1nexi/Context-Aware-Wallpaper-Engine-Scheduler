"""
Dashboard HTTP server — Bottle-based, serves static SPA + /api/* endpoints.

AnalysisStore is created by the host (main.py) and passed at construction
time. Routes are Bottle-decorated; the server runs on a threaded wsgiref
backend so the tray main thread is never blocked.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from collections.abc import Callable
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server
from typing import TYPE_CHECKING, Literal, TypedDict

import bottle
from pydantic import ValidationError

from ui.dashboard_analysis import (
    AnalysisStore,
    DashboardRuntimeMetadata,
    build_tick_window_response,
)
from utils.app_context import get_app_root
from utils.config_loader import AppConfig

if TYPE_CHECKING:
    from core.event_logger import EventLogger

logger = logging.getLogger("WEScheduler.Dashboard")

DASHBOARD_STATIC_APP_DIR = "dashboard"
DASHBOARD_STATIC_DIST_DIR = "dist"


ConfigSection = Literal["general", "scheduling", "playlists", "tags", "policies"]
ConfigPath = list[str | int]


class PolicyValidationScope(TypedDict):
    kind: Literal["policy"]
    key: str


class PlaylistValidationScope(TypedDict):
    kind: Literal["playlist"]
    index: int


class TagValidationScope(TypedDict):
    kind: Literal["tag"]
    key: str


ConfigValidationScope = PolicyValidationScope | PlaylistValidationScope | TagValidationScope


class ConfigValidationDetail(TypedDict):
    path: ConfigPath
    message: str
    code: str
    section: ConfigSection | None
    scope: ConfigValidationScope | None


def _derive_error_section(path: ConfigPath) -> ConfigSection | None:
    if not path:
        return None

    first = path[0]
    if first in {"wallpaper_engine_path", "language"}:
        return "general"
    if first in {"scheduling", "playlists", "tags", "policies"}:
        return str(first)
    return None


def _derive_error_scope(path: ConfigPath) -> ConfigValidationScope | None:
    if len(path) < 2:
        return None

    root = path[0]
    scope_key = path[1]
    if root == "policies" and isinstance(scope_key, str):
        return {"kind": "policy", "key": scope_key}
    if root == "playlists" and isinstance(scope_key, int):
        return {"kind": "playlist", "index": scope_key}
    if root == "tags" and isinstance(scope_key, str):
        return {"kind": "tag", "key": scope_key}
    return None


def _flatten_errors(exc: ValidationError | Exception) -> list[ConfigValidationDetail]:
    """Flatten Pydantic ValidationError into structured config field errors."""
    if not isinstance(exc, ValidationError):
        return [
            {
                "path": [],
                "message": str(exc),
                "code": "unknown_error",
                "section": None,
                "scope": None,
            }
        ]

    errors: list[ConfigValidationDetail] = []
    for err in exc.errors():
        path = list(err.get("loc", ()))
        errors.append(
            {
                "path": path,
                "message": err["msg"],
                "code": err.get("type", "unknown_error"),
                "section": _derive_error_section(path),
                "scope": _derive_error_scope(path),
            }
        )
    return errors


class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def _resolve_static_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, DASHBOARD_STATIC_APP_DIR, DASHBOARD_STATIC_DIST_DIR)
    return os.path.join(get_app_root(), DASHBOARD_STATIC_APP_DIR, DASHBOARD_STATIC_DIST_DIR)


def _parse_positive_count(raw_value: str) -> int:
    count = int(raw_value)
    if count <= 0:
        raise ValueError("count must be positive")
    return count


MetadataProvider = Callable[[], DashboardRuntimeMetadata]


def _empty_metadata() -> DashboardRuntimeMetadata:
    return DashboardRuntimeMetadata(display_of={}, color_of={})


def _build_app(
    analysis_store: AnalysisStore,
    history_logger: EventLogger | None = None,
    config_path: str = "",
    metadata_provider: MetadataProvider | None = None,
) -> bottle.Bottle:
    app = bottle.Bottle()
    resolve_metadata = metadata_provider or _empty_metadata

    @app.route("/api/analysis/window")
    def api_analysis_window():
        raw_count = bottle.request.query.get("count", "900")
        try:
            count = _parse_positive_count(raw_count)
        except (TypeError, ValueError):
            bottle.response.status = 400
            bottle.response.content_type = "application/json; charset=utf-8"
            return json.dumps({"error": "invalid_count"})

        window = analysis_store.read_window(count)
        payload = build_tick_window_response(window, resolve_metadata())
        bottle.response.content_type = "application/json; charset=utf-8"
        return json.dumps(payload)

    @app.route("/api/health")
    def api_health():
        bottle.response.content_type = "application/json; charset=utf-8"
        return {"ok": True}

    @app.route("/api/history")
    def api_history():
        """Events in [from, to], newest first, with has_more for pagination.

        Query: from=<ISO>  to=<ISO>  limit=<int, default 100, 0=unlimited>
        Response: {"events": [...], "has_more": bool}
        """
        bottle.response.content_type = "application/json; charset=utf-8"
        if history_logger is None:
            return json.dumps({"events": [], "has_more": False})
        limit = int(bottle.request.query.get("limit", 100))
        from_ts = bottle.request.query.get("from")
        to_ts = bottle.request.query.get("to")

        return json.dumps(history_logger.read(limit=limit, from_ts=from_ts, to_ts=to_ts))

    @app.route("/api/history/aggregate")
    def api_history_aggregate():
        """Aggregated playlist duration ratios per time bucket.

        Query: from=<ISO>  to=<ISO>  bucket=<minutes, default 60>
        Response: {"buckets": [...], "total_seconds": int}
        """
        bottle.response.content_type = "application/json; charset=utf-8"
        if history_logger is None:
            return json.dumps({"buckets": [], "total_seconds": 0})
        from_ts = bottle.request.query.get("from")
        to_ts = bottle.request.query.get("to")
        bucket_minutes = int(bottle.request.query.get("bucket", 60))

        return json.dumps(
            history_logger.aggregate(
                from_ts=from_ts,
                to_ts=to_ts,
                bucket_minutes=bucket_minutes,
            )
        )

    @app.route("/api/config")
    def api_config():
        bottle.response.content_type = "application/json; charset=utf-8"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            current = AppConfig.model_validate(raw)
            defaults = AppConfig()
        except FileNotFoundError:
            bottle.response.status = 404
            return json.dumps({"error": "config_not_found"})
        except ValueError as exc:
            bottle.response.status = 500
            return json.dumps({"error": "invalid_config", "details": str(exc)})
        return json.dumps(
            {
                "current": current.model_dump(mode="json"),
                "defaults": defaults.model_dump(mode="json"),
            }
        )

    @app.route("/api/config", method="POST")
    def api_config_save():
        bottle.response.content_type = "application/json; charset=utf-8"
        data = bottle.request.json
        if data is None:
            bottle.response.status = 400
            return json.dumps({"error": "no_json_body"})
        try:
            canonical_config = AppConfig.model_validate(data).model_dump(mode="json")
        except ValueError as exc:
            bottle.response.status = 422
            return json.dumps(
                {
                    "error": "validation_failed",
                    "details": _flatten_errors(exc),
                }
            )

        tmp = config_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(canonical_config, f, indent=2, ensure_ascii=False)
            os.replace(tmp, config_path)
        except OSError as exc:
            bottle.response.status = 500
            return json.dumps({"error": "write_failed", "details": str(exc)})
        logger.info("Config saved via API")
        return json.dumps({"ok": True})

    @app.route("/api/tags/presets")
    def api_tags_presets():
        bottle.response.content_type = "application/json; charset=utf-8"
        from core.policies import KNOWN_TAGS

        return json.dumps(KNOWN_TAGS)

    @app.route("/api/playlists/scan")
    def api_playlists_scan():
        bottle.response.content_type = "application/json; charset=utf-8"
        wallpaper_engine_path = ""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            wallpaper_engine_path = raw.get("wallpaper_engine_path", "")
        except Exception as exc:
            logger.warning("Failed to read config for playlist scan: %s", exc)

        from utils.we_path import find_we_config_json

        we_config = find_we_config_json(wallpaper_engine_path)
        if we_config is None:
            return json.dumps({"playlists": [], "error": "we_config_not_found"})

        try:
            with open(we_config, "r", encoding="utf-8") as f:
                we_data = json.load(f)
        except Exception:
            return json.dumps({"playlists": [], "error": "we_config_read_failed"})

        if not isinstance(we_data, dict):
            return json.dumps({"playlists": [], "error": "unexpected_we_config_format"})

        import getpass

        username = getpass.getuser()
        user_entry = we_data.get(username)
        if isinstance(user_entry, dict):
            general = user_entry.get("general", {})
            playlists = general.get("playlists", []) if isinstance(general, dict) else []
        else:
            playlists = []
        names = [p["name"] for p in playlists if isinstance(p, dict) and "name" in p]
        return json.dumps({"playlists": names})

    @app.route("/api/we-path")
    def api_we_path():
        bottle.response.content_type = "application/json; charset=utf-8"
        wallpaper_engine_path = ""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            wallpaper_engine_path = raw.get("wallpaper_engine_path", "")
        except Exception:
            pass

        from utils.we_path import find_wallpaper_engine

        detected = find_wallpaper_engine(wallpaper_engine_path)
        return json.dumps({"path": detected, "valid": bool(detected)})

    static_root = _resolve_static_root()

    @app.route("/")
    @app.route("/<path:path>")
    def serve_spa(path=""):
        file_path = os.path.normpath(os.path.join(static_root, path.lstrip("/")))
        if not file_path.startswith(os.path.normpath(static_root)):
            bottle.abort(403, "Forbidden")

        if os.path.isfile(file_path):
            return bottle.static_file(path, root=static_root)

        return bottle.static_file("index.html", root=static_root)

    return app


class DashboardHTTPServer:
    """Bottle-powered HTTP server for the dashboard SPA."""

    def __init__(
        self,
        analysis_store: AnalysisStore,
        history_logger: EventLogger | None = None,
        config_path: str = "",
        requested_port: int = 0,
        metadata_provider: MetadataProvider | None = None,
    ):
        """
        metadata_provider: callback to get metadata at request time, showing the latest metadata in case of hotreload
        """
        self._analysis_store = analysis_store
        self._history: EventLogger | None = history_logger
        self._config_path = config_path
        self._requested_port = requested_port
        self._metadata_provider = metadata_provider
        self._httpd: _ThreadingWSGIServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int = 0

    def start(self) -> None:
        os.makedirs(_resolve_static_root(), exist_ok=True)
        app = _build_app(
            self._analysis_store,
            self._history,
            self._config_path,
            self._metadata_provider,
        )

        try:
            self._httpd = make_server(
                "127.0.0.1",
                self._requested_port,
                app,
                server_class=_ThreadingWSGIServer,
            )
        except OSError as exc:
            if self._requested_port > 0:
                raise OSError(
                    f"Failed to bind dashboard API server to 127.0.0.1:{self._requested_port}"
                ) from exc
            raise

        self.port = self._httpd.server_address[1]

        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        logger.info("Dashboard HTTP server (bottle) on http://127.0.0.1:%d", self.port)

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None
        self._thread = None
