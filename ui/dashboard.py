from __future__ import annotations

import json
import logging
import os
import sys
import threading
from collections.abc import Callable
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

import bottle
from pydantic import BaseModel, ConfigDict, ValidationError

from app.context import get_app_root
from configurations.profile import Profile
from core.models.scene import SceneId
from core.runtime.profile_manager import (
    ProfileAlreadyExists,
    ProfileApplyFailed,
    ProfileApplyTimeout,
    ProfileApplyUnavailable,
    ProfileManager,
)
from core.runtime.we_config import WEConfigProber, WEConfigReadError
from core.runtime.we_path import resolve_wallpaper_engine_path
from core.state.tick_history import TickHistoryStore
from ui.tick_history import build_tick_window_response

logger = logging.getLogger("WEScheduler.Dashboard")

DASHBOARD_STATIC_APP_DIR = "dashboard"
DASHBOARD_STATIC_DIST_DIR = "dist"
SETUP_STATIC_APP_DIR = "frontend"
PROFILE_APPLY_TIMEOUT_SECONDS = 2.0


class PlaylistScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wallpaper_engine_path: str = ""


class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def _resolve_static_root(app_dir: str) -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, app_dir, DASHBOARD_STATIC_DIST_DIR)
    return os.path.join(get_app_root(), app_dir, DASHBOARD_STATIC_DIST_DIR)


def _serve_spa(static_root: str, path: str) -> bottle.HTTPResponse:
    """Serve one SPA asset or its index fallback.

    Raises:
        bottle.HTTPError: If the requested path escapes the static root.
    """

    file_path = os.path.normpath(os.path.join(static_root, path.lstrip("/")))
    try:
        common_path = os.path.commonpath((static_root, file_path))
    except ValueError:
        common_path = ""
    if common_path != os.path.normpath(static_root):
        bottle.abort(403, "Forbidden")

    if os.path.isfile(file_path):
        return bottle.static_file(path, root=static_root)

    return bottle.static_file("index.html", root=static_root)


def _parse_positive_count(raw_value: str) -> int:
    count = int(raw_value)
    if count <= 0:
        raise ValueError("count must be positive")
    return count


def _profile_validation_issues(exc: ValidationError) -> list[dict[str, object]]:
    return [
        {
            "path": list(issue["loc"]),
            "code": issue["type"],
            "message": issue["msg"],
        }
        for issue in exc.errors()
    ]


def _read_json_object() -> dict[str, object]:
    payload = json.loads(bottle.request.body.read())
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    return payload


def _request_validation_issues(exc: ValidationError | ValueError) -> list[dict[str, object]]:
    if isinstance(exc, ValidationError):
        return _profile_validation_issues(exc)
    return [{"path": [], "code": "json_type", "message": str(exc)}]


def build_dashboard_app(
    tick_history: TickHistoryStore,
    profile_manager: ProfileManager,
    *,
    on_initial_profile_created: Callable[[], None] | None = None,
) -> bottle.Bottle:
    app = bottle.Bottle()

    @app.route("/api/tick-history/window")
    def api_tick_history_window():
        raw_count = bottle.request.query.get("count", "900")
        try:
            count = _parse_positive_count(raw_count)
        except (TypeError, ValueError):
            bottle.response.status = 400
            bottle.response.content_type = "application/json; charset=utf-8"
            return json.dumps({"error": "invalid_count"})

        window = tick_history.read_window(count)
        payload = build_tick_window_response(window)
        bottle.response.content_type = "application/json; charset=utf-8"
        return json.dumps(payload)

    @app.route("/api/health")
    def api_health():
        bottle.response.content_type = "application/json; charset=utf-8"
        return {"ok": True}

    @app.route("/api/profile")
    def api_profile():
        bottle.response.content_type = "application/json; charset=utf-8"
        profile = profile_manager.get_profile()
        if profile is None:
            bottle.response.status = 404
            return {"error": "profile_not_found"}
        return {"profile": profile.model_dump(mode="json")}

    @app.route("/api/setup/scenes")
    def api_setup_scenes():
        bottle.response.content_type = "application/json; charset=utf-8"
        return {"scenes": [{"id": scene_id.value} for scene_id in SceneId]}

    @app.post("/api/setup/wallpaper-engine/playlists")
    def api_scan_wallpaper_engine_playlists():
        bottle.response.content_type = "application/json; charset=utf-8"
        if bottle.request.content_type != "application/json":
            bottle.response.status = 415
            return {"error": "unsupported_media_type"}

        try:
            scan_request = PlaylistScanRequest.model_validate(_read_json_object())
        except (ValidationError, ValueError) as exc:
            bottle.response.status = 400
            return {
                "error": "invalid_wallpaper_engine_request",
                "issues": _request_validation_issues(exc),
            }

        executable = resolve_wallpaper_engine_path(scan_request.wallpaper_engine_path)
        if executable is None:
            bottle.response.status = 404
            return {"error": "wallpaper_engine_executable_not_found"}

        try:
            prober = WEConfigProber(executable)
            playlist_names = list(dict.fromkeys(prober.scan_playlist_names()))
            item_counts = prober.probe_item_counts()
        except WEConfigReadError as exc:
            bottle.response.status = 422
            return {"error": exc.code}

        return {
            "wallpaper_engine_path": executable,
            "playlists": [{"name": name, "item_count": item_counts.get(name, 0)} for name in playlist_names],
        }

    @app.post("/api/profile/create")
    def api_create_profile():
        bottle.response.content_type = "application/json; charset=utf-8"
        if bottle.request.content_type != "application/json":
            bottle.response.status = 415
            return {"error": "unsupported_media_type"}

        try:
            draft = Profile.model_validate(_read_json_object())
        except (ValidationError, ValueError) as exc:
            bottle.response.status = 400
            return {
                "error": "invalid_profile",
                "issues": _request_validation_issues(exc),
            }

        try:
            committed = profile_manager.create_initial_profile(draft)
        except ProfileAlreadyExists:
            bottle.response.status = 409
            return {"error": "profile_already_exists"}
        except ProfileApplyFailed as exc:
            logger.exception("Initial Profile creation failed during %s", exc.stage)
            bottle.response.status = 500
            return {
                "error": "profile_create_failed",
                "stage": exc.stage,
                "detail": str(exc),
            }
        except Exception as exc:
            logger.exception("Initial Profile creation failed")
            bottle.response.status = 500
            return {"error": "profile_create_failed", "detail": str(exc)}

        bottle.response.status = 201
        if on_initial_profile_created is not None:
            try:
                on_initial_profile_created()
            except Exception:
                logger.exception("Initial Profile creation callback failed")
        return {
            "status": "created",
            "profile": committed.model_dump(mode="json"),
        }

    @app.post("/api/profile/apply")
    def api_apply_profile():
        bottle.response.content_type = "application/json; charset=utf-8"
        if bottle.request.content_type != "application/json":
            bottle.response.status = 415
            return {"error": "unsupported_media_type"}

        try:
            draft = Profile.model_validate(_read_json_object())
        except (ValidationError, ValueError) as exc:
            bottle.response.status = 400
            return {
                "error": "invalid_profile",
                "issues": _request_validation_issues(exc),
            }

        try:
            committed = profile_manager.apply_profile(
                draft,
                timeout=PROFILE_APPLY_TIMEOUT_SECONDS,
            )
        except ProfileApplyTimeout:
            bottle.response.status = 503
            return {"error": "profile_apply_timeout"}
        except ProfileApplyUnavailable:
            bottle.response.status = 503
            return {"error": "profile_apply_unavailable"}
        except ProfileApplyFailed as exc:
            logger.exception("Profile apply failed during %s", exc.stage)
            bottle.response.status = 500
            return {
                "error": "profile_apply_failed",
                "stage": exc.stage,
                "detail": str(exc),
            }
        except Exception as exc:
            logger.exception("Profile apply failed")
            bottle.response.status = 500
            return {"error": "profile_apply_failed", "detail": str(exc)}

        return {
            "status": "applied",
            "profile": committed.model_dump(mode="json"),
        }

    dashboard_static_root = _resolve_static_root(DASHBOARD_STATIC_APP_DIR)
    setup_static_root = _resolve_static_root(SETUP_STATIC_APP_DIR)

    @app.route("/setup")
    def redirect_setup() -> bottle.HTTPResponse:
        return bottle.redirect("/setup/")

    @app.route("/setup/")
    @app.route("/setup/<path:path>")
    def serve_setup_spa(path: str = "") -> bottle.HTTPResponse:
        return _serve_spa(setup_static_root, path)

    @app.route("/")
    @app.route("/<path:path>")
    def serve_spa(path: str = "") -> bottle.HTTPResponse:
        return _serve_spa(dashboard_static_root, path)

    return app


class DashboardHTTPServer:
    """Host a prepared Bottle dashboard app on the loopback interface."""

    def __init__(
        self,
        app: bottle.Bottle,
        requested_port: int = 0,
    ):
        self._app = app
        self._requested_port = requested_port
        self._httpd: _ThreadingWSGIServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int = 0

    def start(self) -> None:
        try:
            self._httpd = make_server(
                "127.0.0.1",
                self._requested_port,
                self._app,
                server_class=_ThreadingWSGIServer,
            )
        except OSError as exc:
            if self._requested_port > 0:
                raise OSError(f"Failed to bind dashboard API server to 127.0.0.1:{self._requested_port}") from exc
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
