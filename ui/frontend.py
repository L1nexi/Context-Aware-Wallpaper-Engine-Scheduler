from __future__ import annotations

import json
import logging
import os
import sys
import threading
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

import bottle

from app.context import get_app_root
from ui.dto.diagnostic import build_tick_window_response
from ui.tick_trace_store import TickTraceStore

logger = logging.getLogger("WEScheduler.Frontend")

FRONTEND_STATIC_APP_DIR = "frontend"
FRONTEND_STATIC_DIST_DIR = "dist"


class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def _resolve_static_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, FRONTEND_STATIC_APP_DIR, FRONTEND_STATIC_DIST_DIR)
    return os.path.join(get_app_root(), FRONTEND_STATIC_APP_DIR, FRONTEND_STATIC_DIST_DIR)


def _parse_positive_count(raw_value: str) -> int:
    count = int(raw_value)
    if count <= 0:
        raise ValueError("count must be positive")
    return count


def _build_app(tick_store: TickTraceStore) -> bottle.Bottle:
    app = bottle.Bottle()

    @app.route("/api/tick-traces/window")
    def api_tick_traces_window():
        raw_count = bottle.request.query.get("count", "900")
        try:
            count = _parse_positive_count(raw_count)
        except (TypeError, ValueError):
            bottle.response.status = 400
            bottle.response.content_type = "application/json; charset=utf-8"
            return json.dumps({"error": "invalid_count"})

        window = tick_store.read_window(count)
        payload = build_tick_window_response(window)
        bottle.response.content_type = "application/json; charset=utf-8"
        return json.dumps(payload)

    @app.route("/api/health")
    def api_health():
        bottle.response.content_type = "application/json; charset=utf-8"
        return {"ok": True}

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


class FrontendHTTPServer:
    """Bottle-powered HTTP server for the frontend SPA."""

    def __init__(
        self,
        tick_store: TickTraceStore,
        requested_port: int = 0,
    ):
        self._tick_store = tick_store
        self._requested_port = requested_port
        self._httpd: _ThreadingWSGIServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int = 0

    def start(self) -> None:
        os.makedirs(_resolve_static_root(), exist_ok=True)
        app = _build_app(self._tick_store)

        try:
            self._httpd = make_server(
                "127.0.0.1",
                self._requested_port,
                app,
                server_class=_ThreadingWSGIServer,
            )
        except OSError as exc:
            if self._requested_port > 0:
                raise OSError(f"Failed to bind frontend API server to 127.0.0.1:{self._requested_port}") from exc
            raise

        self.port = self._httpd.server_address[1]

        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        logger.info("Frontend HTTP server (bottle) on http://127.0.0.1:%d", self.port)

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None
        self._thread = None
