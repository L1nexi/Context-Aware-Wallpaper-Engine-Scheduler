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
from collections import deque
from typing import Dict, List, TYPE_CHECKING
from dataclasses import dataclass, field
import json

import bottle

from utils.app_context import get_app_root
from utils.i18n import _current_lang
from core.diagnostics import SchedulerTickTrace
from core.scheduler import WEScheduler
import getpass
from utils.config_loader import AppConfig

if TYPE_CHECKING:
    from core.event_logger import EventLogger

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
    last_event_id: int = 0
    top_matches: list = field(default_factory=list)  # [(name, score), ...] top 5


# ── StateStore ─────────────────────────────────────────────────────

class StateStore:
    """Thread-safe store for TickState snapshots with a ring buffer of recent ticks."""

    def __init__(self, tick_history: int = 300):
        self._lock = threading.Lock()
        self._state = TickState()
        self._ticks: deque[TickState] = deque(maxlen=tick_history)

    def update(self, state: TickState) -> None:
        with self._lock:
            self._state = state
            self._ticks.append(state)

    def read(self) -> TickState:
        with self._lock:
            return self._state

    def read_recent(self, count: int | None = None) -> list[dict]:
        with self._lock:
            items = list(self._ticks)
            if count is not None:
                items = items[-count:]
        return [dataclasses.asdict(s) for s in items]


# ── build_tick_state ──────────────────────────────────────────────

def build_tick_state(
    scheduler: WEScheduler,
    trace: SchedulerTickTrace,
) -> TickState:
    """Construct a TickState snapshot from the current scheduler tick."""
    tags = trace.match.raw_context_vector
    sorted_tags = sorted(tags.items(), key=lambda x: x[1], reverse=True)[:8]
    top_tags = [{"tag": t, "weight": round(w, 4)} for t, w in sorted_tags]

    active = trace.active_playlist_after
    display = scheduler.display_of.get(active, "") if active else ""

    return TickState(
        ts=trace.ts,
        current_playlist=active,
        current_playlist_display=display,
        similarity=round(trace.match.similarity, 4),
        similarity_gap=round(trace.match.similarity_gap, 4),
        max_policy_magnitude=round(trace.match.max_policy_magnitude, 4),
        top_tags=top_tags,
        paused=trace.paused,
        pause_until=trace.pause_until,
        active_window=trace.context.window.process or "N/A",
        idle_time=round(trace.context.idle, 1),
        cpu=round(trace.context.cpu, 1),
        fullscreen=trace.context.fullscreen,
        locale=_current_lang,
        last_event_id=scheduler.history_logger.last_event_id if scheduler.history_logger else 0,
        top_matches=[
            (scheduler.display_of.get(name, name), round(score, 4))
            for name, score in trace.match.playlist_matches[:5]
        ],
    )


def _flatten_errors(exc) -> list[dict]:
    """Flatten Pydantic ValidationError to [{field, message}]."""
    if not hasattr(exc, "errors"):
        return [{"field": "", "message": str(exc)}]
    errors: list[dict] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        errors.append({"field": loc, "message": err["msg"]})
    return errors


class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def _resolve_static_root() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, 'dashboard', 'dist')
    return os.path.join(get_app_root(), 'dashboard', 'dist')


def _build_app(
    state_store: StateStore,
    history_logger: EventLogger | None = None,
    config_path: str = "",
) -> bottle.Bottle:
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

    @app.route('/api/ticks')
    def api_ticks():
        count = int(bottle.request.query.get('count', 300))
        bottle.response.content_type = 'application/json; charset=utf-8'
        return json.dumps(state_store.read_recent(count))

    @app.route('/api/history')
    def api_history():
        """Events in [from, to], newest first, with has_more for pagination.

        Query: from=<ISO>  to=<ISO>  limit=<int, default 100, 0=unlimited>
        Response: {"events": [...], "has_more": bool}
        """
        bottle.response.content_type = 'application/json; charset=utf-8'
        if history_logger is None:
            return json.dumps({"events": [], "has_more": False})
        limit = int(bottle.request.query.get('limit', 100))
        from_ts = bottle.request.query.get('from')
        to_ts = bottle.request.query.get('to')

        return json.dumps(history_logger.read(limit=limit, from_ts=from_ts, to_ts=to_ts))

    @app.route('/api/history/aggregate')
    def api_history_aggregate():
        """Aggregated playlist duration ratios per time bucket.

        Query: from=<ISO>  to=<ISO>  bucket=<minutes, default 60>
        Response: {"buckets": [...], "total_seconds": int}
        """
        bottle.response.content_type = 'application/json; charset=utf-8'
        if history_logger is None:
            return json.dumps({"buckets": [], "total_seconds": 0})
        from_ts = bottle.request.query.get('from')
        to_ts = bottle.request.query.get('to')
        bucket_minutes = int(bottle.request.query.get('bucket', 60))

        return json.dumps(history_logger.aggregate(
            from_ts=from_ts, to_ts=to_ts, bucket_minutes=bucket_minutes,
        ))

    # ── Config API routes ──────────────────────────────────────

    @app.route('/api/config')
    def api_config():
        bottle.response.content_type = 'application/json; charset=utf-8'
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            AppConfig.model_validate(raw)
        except FileNotFoundError:
            bottle.response.status = 404
            return json.dumps({"error": "config_not_found"})
        except ValueError as e:
            bottle.response.status = 500
            return json.dumps({"error": "invalid_config", "details": str(e)})
        return json.dumps(raw)

    @app.route('/api/config', method='POST')
    def api_config_save():
        bottle.response.content_type = 'application/json; charset=utf-8'
        data = bottle.request.json
        if data is None:
            bottle.response.status = 400
            return json.dumps({"error": "no_json_body"})
        try:
            AppConfig.model_validate(data)
        except ValueError as e:
            bottle.response.status = 422
            return json.dumps({
                "error": "validation_failed",
                "details": _flatten_errors(e),
            })

        tmp = config_path + '.tmp'
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, config_path)
        except OSError as e:
            bottle.response.status = 500
            return json.dumps({"error": "write_failed", "details": str(e)})
        logger.info("Config saved via API")
        return json.dumps({"ok": True})

    @app.route('/api/tags/presets')
    def api_tags_presets():
        bottle.response.content_type = 'application/json; charset=utf-8'
        from core.policies import KNOWN_TAGS
        return json.dumps(KNOWN_TAGS)

    @app.route('/api/playlists/scan')
    def api_playlists_scan():
        bottle.response.content_type = 'application/json; charset=utf-8'
        wallpaper_engine_path = ""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            wallpaper_engine_path = raw.get("wallpaper_engine_path", "")
        except Exception as exc:
            logger.warning("Failed to read config for playlist scan: %s", exc)

        from utils.we_path import find_we_config_json
        we_config = find_we_config_json(wallpaper_engine_path)
        if we_config is None:
            return json.dumps({"playlists": [], "error": "we_config_not_found"})

        try:
            with open(we_config, 'r', encoding='utf-8') as f:
                we_data = json.load(f)
        except Exception:
            return json.dumps({"playlists": [], "error": "we_config_read_failed"})

        if not isinstance(we_data, dict):
            return json.dumps({"playlists": [], "error": "unexpected_we_config_format"})
        username = getpass.getuser()
        user_entry = we_data.get(username)
        if isinstance(user_entry, dict):
            general = user_entry.get("general", {})
            if isinstance(general, dict):
                playlists = general.get("playlists", [])
            else:
                playlists = []
        else:
            playlists = []
        names = [p["name"] for p in playlists if isinstance(p, dict) and "name" in p]
        return json.dumps({"playlists": names})

    @app.route('/api/we-path')
    def api_we_path():
        """Auto-detect Wallpaper Engine executable path."""
        bottle.response.content_type = 'application/json; charset=utf-8'
        wallpaper_engine_path = ""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            wallpaper_engine_path = raw.get("wallpaper_engine_path", "")
        except Exception:
            pass
        from utils.we_path import find_wallpaper_engine
        detected = find_wallpaper_engine(wallpaper_engine_path)
        return json.dumps({"path": detected, "valid": bool(detected)})

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

    def __init__(
        self,
        state_store: StateStore,
        history_logger: EventLogger | None = None,
        config_path: str = "",
    ):
        self._state_store = state_store
        self._history: EventLogger | None = history_logger
        self._config_path = config_path
        self._httpd: _ThreadingWSGIServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int = 0

    def start(self) -> None:
        os.makedirs(_resolve_static_root(), exist_ok=True)
        app = _build_app(self._state_store, self._history, self._config_path)

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
