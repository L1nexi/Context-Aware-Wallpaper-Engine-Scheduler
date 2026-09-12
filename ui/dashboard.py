from __future__ import annotations

import json
import logging
import os
import sys
import threading
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

import bottle
from pydantic import ValidationError

from app.context import get_app_root
from configurations.profile import Profile
from core.runtime.profile_manager import (
    ProfileApplyFailed,
    ProfileApplyTimeout,
    ProfileApplyUnavailable,
    ProfileManager,
)
from core.state.tick_history import TickHistoryStore
from ui.tick_history import build_tick_window_response

logger = logging.getLogger("WEScheduler.Dashboard")

DASHBOARD_STATIC_APP_DIR = "dashboard"
DASHBOARD_STATIC_DIST_DIR = "dist"
PROFILE_APPLY_TIMEOUT_SECONDS = 2.0


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


def _profile_validation_issues(exc: ValidationError) -> list[dict[str, object]]:
    return [
        {
            "path": list(issue["loc"]),
            "code": issue["type"],
            "message": issue["msg"],
        }
        for issue in exc.errors()
    ]


def build_dashboard_app(
    tick_history: TickHistoryStore,
    profile_manager: ProfileManager,
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

    @app.post("/api/profile/apply")
    def api_apply_profile():
        bottle.response.content_type = "application/json; charset=utf-8"
        if bottle.request.content_type != "application/json":
            bottle.response.status = 415
            return {"error": "unsupported_media_type"}

        try:
            payload = json.loads(bottle.request.body.read())
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            draft = Profile.model_validate(payload)
        except (ValidationError, ValueError) as exc:
            bottle.response.status = 400
            if isinstance(exc, ValidationError):
                issues = _profile_validation_issues(exc)
            else:
                issues = [{"path": [], "code": "json_type", "message": str(exc)}]
            return {"error": "invalid_profile", "issues": issues}

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
