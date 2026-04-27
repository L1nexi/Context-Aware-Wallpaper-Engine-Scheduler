"""
Dashboard HTTP server — Bottle-based, serves static SPA + /api/* endpoints.

StateStore is created by the host (main.py) and passed at construction time.
Routes are Bottle-decorated; the server runs on a threaded wsgiref backend
so the tray main thread is never blocked.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import sys
import threading
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import time

import bottle

from utils.app_context import get_app_root
from utils.i18n import _current_lang
from core.scheduler import WEScheduler, Context, MatchResult

logger = logging.getLogger("WEScheduler.Dashboard")



# ── TickState ──────────────────────────────────────────────────────

@dataclass
class TickState:
    ts: float = 0.0
    current_playlist: str = ""
    current_playlist_display: str = ""
    similarity: float = 0.0
    similarity_gap: float = 0.0
    max_policy_magnitude: float = 0.0
    top_tags: List[Dict[str, float]] = field(default_factory=list)
    paused: bool = False
    pause_until: float = 0.0
    active_window: str = ""
    idle_time: float = 0.0
    cpu: float = 0.0
    fullscreen: bool = False
    locale: str = "en"


# ── StateStore ─────────────────────────────────────────────────────

class StateStore:
    """Thread-safe store for the most recent TickState."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = TickState()

    def update(self, state: TickState) -> None:
        with self._lock:
            self._state = state

    def read(self) -> TickState:
        with self._lock:
            return self._state


# ── build_tick_state ──────────────────────────────────────────────

def build_tick_state(
    scheduler: WEScheduler,
    context: Context,
    result: Optional[MatchResult],
) -> TickState:
    """Construct a TickState snapshot from the current scheduler tick."""
    tags = result.aggregated_tags if result is not None else {}
    sorted_tags = sorted(tags.items(), key=lambda x: x[1], reverse=True)[:8]
    top_tags = [{"tag": t, "weight": round(w, 4)} for t, w in sorted_tags]

    best = result.best_playlist if result is not None else ""
    display = scheduler.display_of.get(best, "") if best else ""

    return TickState(
        ts=time.time(),
        current_playlist=best,
        current_playlist_display=display,
        similarity=round(result.similarity, 4) if result is not None else 0.0,
        similarity_gap=round(result.similarity_gap, 4) if result is not None else 0.0,
        max_policy_magnitude=round(result.max_policy_magnitude, 4) if result is not None else 0.0,
        top_tags=top_tags,
        paused=scheduler.paused,
        pause_until=scheduler.pause_until,
        active_window=context.window.process or "N/A",
        idle_time=round(context.idle, 1),
        cpu=round(context.cpu, 1),
        fullscreen=context.fullscreen,
        locale=_current_lang,
    )


class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def _resolve_static_root() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, 'dashboard', 'dist')
    return os.path.join(get_app_root(), 'dashboard', 'dist')


def _build_app(state_store: StateStore) -> bottle.Bottle:
    app = bottle.Bottle()

    # ── API routes ──────────────────────────────────────────────

    @app.route('/api/state')
    def api_state():
        bottle.response.content_type = 'application/json; charset=utf-8'
        return dataclasses.asdict(state_store.read())

    @app.route('/api/health')
    def api_health():
        bottle.response.content_type = 'application/json; charset=utf-8'
        return {"ok": True}

    # ── Static / SPA routes ─────────────────────────────────────

    static_root = _resolve_static_root()

    @app.route('/')
    @app.route('/<path:path>')
    def serve_spa(path=''):
        # Normalize and security check
        file_path = os.path.normpath(
            os.path.join(static_root, path.lstrip('/'))
        )
        if not file_path.startswith(os.path.normpath(static_root)):
            bottle.abort(403, "Forbidden")

        if os.path.isfile(file_path):
            return bottle.static_file(path, root=static_root)

        # SPA fallback
        return bottle.static_file('index.html', root=static_root)

    return app


class DashboardHTTPServer:
    """Bottle-powered HTTP server for the dashboard SPA.

    Binds to 127.0.0.1:0 (OS-assigned free port).  The chosen port is
    available via ``.port`` after ``start()``.
    """

    def __init__(self, state_store: StateStore):
        self._state_store = state_store
        self._httpd: _ThreadingWSGIServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int = 0

    def start(self) -> None:
        os.makedirs(_resolve_static_root(), exist_ok=True)
        app = _build_app(self._state_store)

        self._httpd = make_server("127.0.0.1", 0, app, server_class=_ThreadingWSGIServer)
        self.port = self._httpd.server_address[1]

        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        logger.info("Dashboard HTTP server (bottle) on http://127.0.0.1:%d", self.port)

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None
        self._thread = None
