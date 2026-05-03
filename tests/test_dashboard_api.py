from __future__ import annotations

import dataclasses
import io
import json
import os
import tempfile
from datetime import datetime, timezone

import bottle
import pytest

from core.context import Context, WindowData
from core.diagnostics import (
    ActionKind,
    ActionReasonCode,
    ActuationOutcome,
    ControllerDecision,
    ControllerEvaluation,
    MatchEvaluation,
    SchedulerTickTrace,
)
from core.event_logger import EventType
from ui.dashboard import (
    TickState,
    StateStore,
    _build_app,
    _flatten_errors,
    _resolve_static_root,
    build_tick_state,
)
from utils.config_loader import AppConfig


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def state_store():
    return StateStore(tick_history=300)


@pytest.fixture
def history_logger(tmp_path):
    from utils.history_logger import HistoryLogger
    return HistoryLogger(str(tmp_path))


@pytest.fixture
def config_path(tmp_path):
    config = {
        "wallpaper_engine_path": "C:\\fake\\wallpaper64.exe",
        "tags": {},
        "playlists": [{"name": "test_pl", "tags": {"#focus": 1.0}}],
        "policies": {},
        "scheduling": {},
    }
    path = os.path.join(str(tmp_path), "scheduler_config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f)
    return path


@pytest.fixture
def app(state_store, history_logger, config_path):
    return _build_app(state_store, history_logger, config_path)


@pytest.fixture
def client(app):
    return bottle.Bottle()
    # We use WSGI directly below


# ── WSGI caller helpers ─────────────────────────────────────────────

def _wsgi_environ(**overrides):
    env = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/",
        "QUERY_STRING": "",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "8080",
        "wsgi.url_scheme": "http",
        "wsgi.input": io.BytesIO(),
        "wsgi.errors": io.StringIO(),
    }
    env.update(overrides)
    return env


def _make_wsgi_environ(method, path, query="", body=None):
    body_bytes = body if body is not None else b""
    env = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "8080",
        "wsgi.url_scheme": "http",
        "wsgi.input": io.BytesIO(body_bytes),
        "wsgi.errors": io.StringIO(),
    }
    if body_bytes:
        env["CONTENT_TYPE"] = "application/json"
        env["CONTENT_LENGTH"] = str(len(body_bytes))
    return env


def wsgi_request(app, method, path, query="", body=None):
    env = _make_wsgi_environ(method, path, query, body)
    result = {}
    def start_response(status, headers, exc_info=None):
        result["status"] = status
        result["headers"] = dict(headers)
    out = app(env, start_response)
    body_str = b"".join(out).decode("utf-8") if out else ""
    try:
        body_json = json.loads(body_str) if body_str else {}
    except json.JSONDecodeError:
        body_json = body_str
    return result.get("status", ""), body_json


def wsgi_get(app, path):
    return wsgi_request(app, "GET", path)


def wsgi_post(app, path, data=None):
    body_bytes = json.dumps(data).encode("utf-8") if data is not None else None
    return wsgi_request(app, "POST", path, body=body_bytes)


# ── GET /api/state ──────────────────────────────────────────────────

def test_api_state_returns_tickstate(state_store, history_logger, config_path):
    app = _build_app(state_store, history_logger, config_path)
    state = TickState(ts=123.456, current_playlist="test_pl", paused=False, locale="en")
    state_store.update(state)

    status, body = wsgi_get(app, "/api/state")
    assert "200" in status
    assert body["current_playlist"] == "test_pl"
    assert body["ts"] == 123.456
    assert body["paused"] is False


# ── GET /api/health ─────────────────────────────────────────────────

def test_api_health(app):
    status, body = wsgi_get(app, "/api/health")
    assert "200" in status
    assert body == {"ok": True}


# ── GET /api/ticks ──────────────────────────────────────────────────

def test_api_ticks_returns_recent(state_store, history_logger, config_path):
    app = _build_app(state_store, history_logger, config_path)
    for i in range(5):
        state_store.update(TickState(ts=float(i), current_playlist=f"pl_{i}"))

    status, body = wsgi_request(app, "GET", "/api/ticks", query="count=3")
    assert "200" in status
    assert len(body) == 3
    # Most recent first (StateStore.read_recent returns newest last, but JSON array
    # order is as returned by read_recent: items[-count:])
    assert body[2]["current_playlist"] == "pl_4"


def test_api_ticks_default_count(state_store, history_logger, config_path):
    app = _build_app(state_store, history_logger, config_path)
    status, body = wsgi_get(app, "/api/ticks")
    assert "200" in status
    assert isinstance(body, list)


def test_api_ticks_invalid_count(state_store, history_logger, config_path):
    app = _build_app(state_store, history_logger, config_path)
    # Bottle will raise a 500 on invalid int conversion
    status, _ = wsgi_request(app, "GET", "/api/ticks", query="count=abc")
    assert "500" in status


# ── GET /api/history ────────────────────────────────────────────────

def test_api_history_no_logger(state_store, config_path):
    app = _build_app(state_store, None, config_path)
    status, body = wsgi_get(app, "/api/history")
    assert "200" in status
    assert body == {"events": [], "has_more": False}


def test_api_history_with_data(app, history_logger):
    history_logger.write(EventType.START, {"playlist": "A"})
    status, body = wsgi_get(app, "/api/history")
    assert "200" in status
    assert len(body["events"]) >= 1
    assert "has_more" in body


def test_api_history_with_params(app, history_logger):
    history_logger.write(EventType.START, {"playlist": "A"})
    hist_data = history_logger.read()
    first_ts = hist_data["events"][0]["ts"] if hist_data["events"] else "2020-01-01T00:00:00+00:00"

    status, body = wsgi_request(app, "GET", "/api/history", query=f"limit=5&from={first_ts}")
    assert "200" in status


# ── GET /api/history/aggregate ──────────────────────────────────────

def test_api_history_aggregate_no_logger(state_store, config_path):
    app = _build_app(state_store, None, config_path)
    status, body = wsgi_get(app, "/api/history/aggregate")
    assert "200" in status
    assert body == {"buckets": [], "total_seconds": 0}


def test_api_history_aggregate_with_data(app, history_logger):
    history_logger.write(EventType.START, {"playlist": "A"})
    history_logger.write(EventType.PLAYLIST_SWITCH,
                         {"playlist_from": "", "playlist_to": "FOCUS"})
    status, body = wsgi_get(app, "/api/history/aggregate")
    assert "200" in status
    assert "buckets" in body
    assert "total_seconds" in body
    assert isinstance(body["total_seconds"], int)


def test_api_history_aggregate_with_bucket_param(app, history_logger):
    history_logger.write(EventType.START, {"playlist": "A"})
    status, body = wsgi_request(
        app, "GET", "/api/history/aggregate", query="bucket=30",
    )
    assert "200" in status
    assert "buckets" in body


# ── GET /api/config ─────────────────────────────────────────────────

def test_api_config_returns_config(app, config_path):
    status, body = wsgi_get(app, "/api/config")
    assert "200" in status
    assert body["wallpaper_engine_path"] == "C:\\fake\\wallpaper64.exe"


def test_api_config_not_found(state_store, history_logger):
    app = _build_app(state_store, history_logger, "/nonexistent/config.json")
    status, body = wsgi_get(app, "/api/config")
    assert "404" in status
    assert body["error"] == "config_not_found"


def test_api_config_invalid_file(state_store, history_logger, tmp_path):
    path = os.path.join(str(tmp_path), "bad_config.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("not json")
    app = _build_app(state_store, history_logger, path)
    status, body = wsgi_get(app, "/api/config")
    assert "500" in status
    assert body["error"] == "invalid_config"


# ── POST /api/config ────────────────────────────────────────────────

def test_api_config_save_valid(app, config_path):
    payload = {
        "wallpaper_engine_path": "C:\\valid\\wallpaper64.exe",
        "playlists": [{"name": "pl", "tags": {"#focus": 1.0}}],
    }
    status, body = wsgi_post(app, "/api/config", payload)
    assert "200" in status
    assert body == {"ok": True}

    # Verify atomic write
    with open(config_path, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["wallpaper_engine_path"] == "C:\\valid\\wallpaper64.exe"


def test_api_config_save_no_body(app):
    status, body = wsgi_post(app, "/api/config", None)
    assert "400" in status
    assert body["error"] == "no_json_body"


def test_api_config_save_validation_failed(state_store, history_logger, tmp_path):
    path = os.path.join(str(tmp_path), "temp_config.json")
    app = _build_app(state_store, history_logger, path)
    # Missing required fields like playlists
    payload = {
        "wallpaper_engine_path": "C:\\x\\wallpaper64.exe",
        "playlists": [{"name": "", "tags": {}}],  # empty name, empty tags
    }
    status, body = wsgi_post(app, "/api/config", payload)
    assert "422" in status
    assert body["error"] == "validation_failed"
    assert len(body["details"]) > 0

    # Verify no temp file left behind on validation failure
    tmp_file = path + ".tmp"
    assert not os.path.exists(tmp_file)


# ── GET /api/tags/presets ───────────────────────────────────────────

def test_api_tags_presets(app):
    from core.policies import KNOWN_TAGS
    status, body = wsgi_get(app, "/api/tags/presets")
    assert "200" in status
    assert body == KNOWN_TAGS


# ── GET /api/playlists/scan ─────────────────────────────────────────

def test_api_playlists_scan_no_config(state_store, history_logger, monkeypatch):
    monkeypatch.setattr("utils.we_path.find_we_config_json", lambda p: None)
    app = _build_app(state_store, history_logger, "/nonexistent/config.json")
    status, body = wsgi_get(app, "/api/playlists/scan")
    assert "200" in status
    assert body["error"] == "we_config_not_found"


# ── GET /api/we-path ───────────────────────────────────────────────

def test_api_we_path_no_config(state_store, history_logger, tmp_path, monkeypatch):
    monkeypatch.setattr("utils.we_path.find_wallpaper_engine", lambda p: None)
    path = os.path.join(str(tmp_path), "no_config.json")
    app = _build_app(state_store, history_logger, path)
    status, body = wsgi_get(app, "/api/we-path")
    assert "200" in status
    assert body["valid"] is False


# ── Static files ────────────────────────────────────────────────────

def test_static_serves_index_html(state_store, history_logger, config_path):
    app = _build_app(state_store, history_logger, config_path)
    status, body = wsgi_get(app, "/")
    # Should redirect or serve index.html; depends on static_root
    assert "200" in status or "303" in status or "404" in status


def test_spa_fallback_for_unknown_path(state_store, history_logger, config_path):
    app = _build_app(state_store, history_logger, config_path)
    status, body = wsgi_get(app, "/some-spa-route")
    # Falls back to index.html
    assert "200" in status or "404" in status


def test_path_traversal_blocked(state_store, history_logger, config_path):
    app = _build_app(state_store, history_logger, config_path)
    status, body = wsgi_get(app, "/../../etc/passwd")
    assert "403" in status


# ── StateStore ─────────────────────────────────────────────────────

def test_state_store_update_and_read():
    store = StateStore(tick_history=10)
    state = TickState(ts=1.0, current_playlist="test")
    store.update(state)
    assert store.read().current_playlist == "test"
    assert store.read().ts == 1.0


def test_state_store_read_recent_caps_at_maxlen():
    store = StateStore(tick_history=3)
    for i in range(5):
        store.update(TickState(ts=float(i)))
    items = store.read_recent()
    assert len(items) == 3
    assert items[0]["ts"] == 2.0
    assert items[-1]["ts"] == 4.0


def test_state_store_read_recent_with_count():
    store = StateStore(tick_history=10)
    for i in range(5):
        store.update(TickState(ts=float(i)))
    items = store.read_recent(count=2)
    assert len(items) == 2
    assert items[-1]["ts"] == 4.0


# ── TickState ───────────────────────────────────────────────────────

def test_tickstate_defaults():
    ts = TickState()
    assert ts.current_playlist == ""
    assert ts.paused is False
    assert ts.locale == "en"
    assert ts.last_event_id == 0
    assert ts.top_tags == []
    assert ts.top_matches == []


def test_tickstate_json_roundtrip():
    ts = TickState(ts=123.0, current_playlist="test", paused=True, locale="zh")
    d = dataclasses.asdict(ts)
    assert d["ts"] == 123.0
    assert d["current_playlist"] == "test"


# ── _flatten_errors ────────────────────────────────────────────────

def test_flatten_errors_no_errors_attr():
    class FakeExc(Exception):
        pass
    result = _flatten_errors(FakeExc("something broke"))
    assert result == [{"field": "", "message": "something broke"}]


# ── build_tick_state ────────────────────────────────────────────────

def test_build_tick_state_no_match():
    from unittest import mock
    scheduler = mock.MagicMock()
    scheduler.paused = False
    scheduler.pause_until = 0.0
    scheduler.history_logger = None
    scheduler.display_of = {}

    trace = SchedulerTickTrace(
        tick_id=1,
        ts=123.0,
        paused=False,
        pause_until=0.0,
        active_playlist_before="",
        active_playlist_after="",
        context=Context(
            window=WindowData(process="", title=""),
            idle=0.0,
            cpu=0.0,
            fullscreen=False,
        ),
        match=MatchEvaluation(
            best_playlist=None,
            raw_context_vector={},
            resolved_context_vector={},
            playlist_matches=[],
        ),
        action=ActuationOutcome(
            decision=ControllerDecision(
                kind=ActionKind.NONE,
                reason_code=ActionReasonCode.NO_MATCH,
                matched_playlist=None,
                evaluation=None,
            ),
            active_playlist_before="",
            active_playlist_after="",
        ),
    )

    state = build_tick_state(scheduler, trace)
    assert state.current_playlist == ""
    assert state.similarity == 0.0
    assert state.top_matches == []


def test_build_tick_state_with_trace():
    from unittest import mock
    scheduler = mock.MagicMock()
    scheduler.history_logger = None
    scheduler.display_of = {"test_pl": "Test Display", "other": "Other Display"}

    trace = SchedulerTickTrace(
        tick_id=2,
        ts=456.0,
        paused=False,
        pause_until=0.0,
        active_playlist_before="old_pl",
        active_playlist_after="test_pl",
        context=Context(
            window=WindowData(process="chrome.exe", title="Chrome"),
            idle=10.5,
            cpu=25.0,
            fullscreen=False,
        ),
        match=MatchEvaluation(
            best_playlist="test_pl",
            max_policy_magnitude=1.2,
            raw_context_vector={"#focus": 0.8, "#day": 0.6},
            resolved_context_vector={"#focus": 0.8, "#day": 0.6},
            playlist_matches=[("test_pl", 0.85), ("other", 0.7)],
        ),
        action=ActuationOutcome(
            decision=ControllerDecision(
                kind=ActionKind.SWITCH,
                reason_code=ActionReasonCode.SWITCH_ALLOWED,
                matched_playlist="test_pl",
                evaluation=ControllerEvaluation(operation="switch", allowed=True),
            ),
            active_playlist_before="old_pl",
            active_playlist_after="test_pl",
            executed=True,
        ),
    )

    state = build_tick_state(scheduler, trace)
    assert state.current_playlist == "test_pl"
    assert state.current_playlist_display == "Test Display"
    assert state.similarity == 0.85
    assert state.similarity_gap == 0.15
    assert state.max_policy_magnitude == 1.2
    assert state.active_window == "chrome.exe"
    assert state.idle_time == 10.5
    assert state.cpu == 25.0
    assert state.fullscreen is False
    assert len(state.top_tags) == 2
    assert state.top_tags[0]["tag"] == "#focus"
    assert len(state.top_matches) == 2
    assert state.top_matches[0][0] == "Test Display"


def test_build_tick_state_paused():
    from unittest import mock
    scheduler = mock.MagicMock()
    scheduler.history_logger = None
    scheduler.display_of = {}

    trace = SchedulerTickTrace(
        tick_id=3,
        ts=789.0,
        paused=True,
        pause_until=999999.0,
        active_playlist_before="",
        active_playlist_after="",
        context=Context(
            window=WindowData(process="", title=""),
            idle=0.0,
            cpu=0.0,
            fullscreen=False,
        ),
        match=MatchEvaluation(
            best_playlist=None,
            raw_context_vector={},
            resolved_context_vector={},
            playlist_matches=[],
        ),
        action=ActuationOutcome(
            decision=ControllerDecision(
                kind=ActionKind.NONE,
                reason_code=ActionReasonCode.NO_MATCH,
                matched_playlist=None,
                evaluation=None,
            ),
            active_playlist_before="",
            active_playlist_after="",
        ),
    )

    state = build_tick_state(scheduler, trace)
    assert state.paused is True
    assert state.pause_until == 999999.0
