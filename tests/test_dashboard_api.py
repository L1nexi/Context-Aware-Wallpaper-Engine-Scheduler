from __future__ import annotations

import io
import json
import os
import socket
import time
import urllib.request
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

import pytest

from core.context import Context, WeatherData, WindowData
from core.diagnostics import (
    ActionKind,
    ActionReasonCode,
    ActivityPolicyDetails,
    ActivityPolicyEvaluation,
    ActuationOutcome,
    ControllerDecision,
    ControllerEvaluation,
    MatchEvaluation,
    SchedulerTickTrace,
    WeatherPolicyDetails,
    WeatherPolicyEvaluation,
)
from core.event_logger import EventType
from ui.dashboard import (
    DASHBOARD_STATIC_APP_DIR,
    DASHBOARD_STATIC_DIST_DIR,
    DashboardHTTPServer,
    _build_app,
    _flatten_errors,
    _resolve_static_root,
)
from ui.dashboard_analysis import AnalysisStore, DashboardRuntimeMetadata, build_tick_snapshot


@pytest.fixture
def analysis_store():
    return AnalysisStore(tick_history=300)


@pytest.fixture
def history_logger(tmp_path):
    from utils.history_logger import HistoryLogger

    return HistoryLogger(str(tmp_path))


@pytest.fixture
def config_path(tmp_path):
    config = {
        "wallpaper_engine_path": "C:\\fake\\wallpaper64.exe",
        "tags": {},
        "playlists": [
            {
                "name": "test_pl",
                "display": "Test Playlist",
                "color": "#5BB8D4",
                "tags": {"#focus": 1.0},
            }
        ],
        "policies": {},
        "scheduling": {},
    }
    path = os.path.join(str(tmp_path), "scheduler_config.json")
    with open(path, "w", encoding="utf-8") as file:
        json.dump(config, file)
    return path


@pytest.fixture
def app(analysis_store, history_logger, config_path):
    return _build_app(analysis_store, history_logger, config_path)


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


def _make_scheduler(
    *,
    weather_enabled: bool = True,
    display_of: dict[str, str] | None = None,
    color_of: dict[str, str] | None = None,
):
    scheduler = mock.MagicMock()
    scheduler.display_of = display_of or {}
    scheduler.color_of = color_of or {}
    weather_cfg = SimpleNamespace(enabled=weather_enabled) if weather_enabled else None
    scheduler.config_loader = SimpleNamespace(
        config=SimpleNamespace(
            policies=SimpleNamespace(weather=weather_cfg),
        )
    )
    return scheduler


def _make_trace(
    *,
    tick_id: int = 1,
    paused: bool = False,
    active_playlist_before: str = "",
    active_playlist_after: str = "",
    matched_playlist: str | None = None,
    executed: bool = False,
    action_kind: ActionKind = ActionKind.HOLD,
    reason_code: ActionReasonCode = ActionReasonCode.NO_MATCH,
    evaluation: ControllerEvaluation | None = None,
    weather: WeatherData | None = None,
    policy_evaluations: list | None = None,
) -> SchedulerTickTrace:
    current_time = time.localtime(1714800000)
    return SchedulerTickTrace(
        tick_id=tick_id,
        ts=1714800000.0 + tick_id,
        paused=paused,
        pause_until=1714803600.0 if paused else 0.0,
        active_playlist_before=active_playlist_before,
        active_playlist_after=active_playlist_after,
        context=Context(
            window=WindowData(process="chrome.exe", title="Code Review"),
            idle=12.5,
            cpu=27.25,
            fullscreen=False,
            weather=weather,
            time=current_time,
        ),
        match=MatchEvaluation(
            best_playlist=matched_playlist,
            playlist_matches=[("focus", 0.91), ("rainy", 0.66)],
            raw_context_vector={"#focus": 0.8, "#rain": 0.4},
            resolved_context_vector={"#focus": 0.8, "#rain": 0.4},
            fallback_expansions={"#storm": {"#rain": 0.25}},
            policy_evaluations=policy_evaluations or [],
            max_policy_magnitude=1.2,
        ),
        action=ActuationOutcome(
            decision=ControllerDecision(
                kind=action_kind,
                reason_code=reason_code,
                matched_playlist=matched_playlist,
                evaluation=evaluation,
            ),
            active_playlist_before=active_playlist_before,
            active_playlist_after=active_playlist_after,
            executed=executed,
        ),
    )


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_analysis_store_read_window_empty(analysis_store):
    window = analysis_store.read_window()

    assert window.live_tick_id is None
    assert window.traces == []


def test_analysis_store_read_window_returns_recent(analysis_store):
    for tick_id in range(1, 6):
        analysis_store.update(_make_trace(tick_id=tick_id))

    window = analysis_store.read_window(2)

    assert window.live_tick_id == 5
    assert [trace.tick_id for trace in window.traces] == [4, 5]


def test_build_tick_snapshot_maps_analysis_fields():
    scheduler = _make_scheduler(
        weather_enabled=True,
        display_of={"focus": "Focus Flow", "rainy": "Rainy Mood"},
        color_of={"focus": "#F5C518", "rainy": "#4A90D9", "idle": "#2E5F8A"},
    )
    evaluation = ControllerEvaluation(
        operation="switch",
        allowed=False,
        blocked_by=[],
        cooldown_remaining=15.0,
        idle_seconds=12.5,
        idle_threshold=60.0,
        cpu_percent=27.25,
        cpu_threshold=85.0,
        fullscreen=False,
        force_after_remaining=120.0,
    )
    activity_policy = ActivityPolicyEvaluation(
        policy_id="activity",
        enabled=True,
        active=True,
        weight_scale=1.0,
        salience=1.0,
        intensity=0.5,
        effective_magnitude=0.5,
        direction={"#focus": 1.0},
        raw_contribution={"#focus": 0.5},
        resolved_contribution={"#focus": 0.5},
        dominant_tag="#focus",
        details=ActivityPolicyDetails(
            match_source="title",
            matched_rule="code",
            matched_tag="#focus",
            window_title="Code Review",
            process="chrome.exe",
            ema_active=True,
        ),
    )
    weather_policy = WeatherPolicyEvaluation(
        policy_id="weather",
        enabled=True,
        active=True,
        weight_scale=1.0,
        salience=1.0,
        intensity=0.4,
        effective_magnitude=0.4,
        direction={"#rain": 1.0},
        raw_contribution={"#rain": 0.4},
        resolved_contribution={"#rain": 0.4},
        dominant_tag="#rain",
        details=WeatherPolicyDetails(
            weather_id=501,
            weather_main="Rain",
            available=True,
            mapped=True,
        ),
    )
    trace = _make_trace(
        tick_id=7,
        active_playlist_before="idle",
        active_playlist_after="idle",
        matched_playlist="focus",
        executed=False,
        action_kind=ActionKind.HOLD,
        reason_code=ActionReasonCode.SWITCH_BLOCKED_COOLDOWN,
        evaluation=evaluation,
        weather=WeatherData(
            id=501,
            main="Rain",
            sunrise=1714770000,
            sunset=1714820000,
            fetched_at=1714799400.0,
            stale=True,
        ),
        policy_evaluations=[activity_policy, weather_policy],
    )

    snapshot = build_tick_snapshot(scheduler, trace)

    assert snapshot["summary"]["tickId"] == 7
    assert snapshot["summary"]["activePlaylist"] == {
        "name": "idle",
        "display": "idle",
        "color": "#2E5F8A",
    }
    assert snapshot["summary"]["matchedPlaylist"] == {
        "name": "focus",
        "display": "Focus Flow",
        "color": "#F5C518",
    }
    assert "activePlaylistDisplay" not in snapshot["summary"]
    assert "activePlaylistColor" not in snapshot["summary"]
    assert "matchedPlaylistDisplay" not in snapshot["summary"]
    assert "matchedPlaylistColor" not in snapshot["summary"]
    assert "enabled" not in snapshot["sense"]["weather"]
    assert snapshot["sense"]["weather"]["available"] is True
    assert snapshot["sense"]["weather"]["stale"] is True
    assert snapshot["think"]["fallbackExpansions"]["#storm"][0]["resolvedTag"] == "#rain"
    assert snapshot["think"]["policies"][0]["policyId"] == "activity"
    assert snapshot["think"]["policies"][1]["details"]["mapped"] is True
    assert snapshot["act"]["topMatches"][0]["playlist"] == {
        "name": "focus",
        "display": "Focus Flow",
        "color": "#F5C518",
    }
    assert snapshot["act"]["topMatches"][0]["score"] == 0.91
    assert snapshot["act"]["topMatches"][1]["playlist"] == {
        "name": "rainy",
        "display": "Rainy Mood",
        "color": "#4A90D9",
    }
    assert snapshot["act"]["controller"]["evaluation"]["operation"] == "switch"
    assert snapshot["act"]["decision"]["reasonCode"] == "switch_blocked_cooldown"
    assert snapshot["act"]["decision"]["activePlaylistBefore"] == {
        "name": "idle",
        "display": "idle",
        "color": "#2E5F8A",
    }
    assert snapshot["act"]["decision"]["activePlaylistAfter"] == {
        "name": "idle",
        "display": "idle",
        "color": "#2E5F8A",
    }
    assert snapshot["act"]["decision"]["matchedPlaylist"] == {
        "name": "focus",
        "display": "Focus Flow",
        "color": "#F5C518",
    }


def test_build_tick_snapshot_maps_paused_tick():
    scheduler = _make_scheduler(
        weather_enabled=False,
        color_of={"focus": "#F5C518", "rainy": "#4A90D9"},
    )
    trace = _make_trace(
        tick_id=8,
        paused=True,
        active_playlist_before="focus",
        active_playlist_after="focus",
        matched_playlist="rainy",
        executed=False,
        action_kind=ActionKind.PAUSE,
        reason_code=ActionReasonCode.SCHEDULER_PAUSED,
        evaluation=None,
        weather=None,
    )

    snapshot = build_tick_snapshot(scheduler, trace)

    assert snapshot["summary"]["actionKind"] == "pause"
    assert snapshot["summary"]["paused"] is True
    assert snapshot["summary"]["hasEvent"] is False
    assert snapshot["summary"]["activePlaylist"] == {
        "name": "focus",
        "display": "focus",
        "color": "#F5C518",
    }
    assert snapshot["summary"]["matchedPlaylist"] == {
        "name": "rainy",
        "display": "rainy",
        "color": "#4A90D9",
    }
    assert snapshot["sense"]["weather"]["available"] is False
    assert snapshot["act"]["controller"]["evaluation"] is None
    assert snapshot["act"]["decision"]["activePlaylistAfter"] == {
        "name": "focus",
        "display": "focus",
        "color": "#F5C518",
    }
    assert snapshot["act"]["decision"]["matchedPlaylist"] == {
        "name": "rainy",
        "display": "rainy",
        "color": "#4A90D9",
    }


def test_build_tick_snapshot_maps_unknown_playlist_ref_with_null_color():
    scheduler = _make_scheduler()
    trace = _make_trace(
        tick_id=9,
        active_playlist_before="",
        active_playlist_after="unknown_active",
        matched_playlist="unknown_match",
        executed=False,
        action_kind=ActionKind.HOLD,
        reason_code=ActionReasonCode.HOLD_SAME_PLAYLIST,
        evaluation=None,
        weather=None,
    )

    snapshot = build_tick_snapshot(scheduler, trace)

    assert snapshot["summary"]["activePlaylist"] == {
        "name": "unknown_active",
        "display": "unknown_active",
        "color": None,
    }
    assert snapshot["summary"]["matchedPlaylist"] == {
        "name": "unknown_match",
        "display": "unknown_match",
        "color": None,
    }
    assert snapshot["act"]["decision"]["activePlaylistBefore"] is None


def test_api_analysis_window_empty(app):
    status, body = wsgi_get(app, "/api/analysis/window")
    assert "200" in status
    assert body == {"liveTickId": None, "ticks": []}


def test_api_analysis_window_returns_recent(analysis_store, history_logger, config_path):
    app = _build_app(analysis_store, history_logger, config_path)
    for tick_id in range(1, 5):
        analysis_store.update(_make_trace(tick_id=tick_id))

    status, body = wsgi_request(app, "GET", "/api/analysis/window", query="count=2")
    assert "200" in status
    assert body["liveTickId"] == 4
    assert [tick["summary"]["tickId"] for tick in body["ticks"]] == [3, 4]


def test_api_analysis_window_projects_traces_with_current_playlist_metadata(
    analysis_store,
    history_logger,
    config_path,
):
    metadata = DashboardRuntimeMetadata(
        display_of={"test_pl": "Test Playlist"},
        color_of={"test_pl": "#5BB8D4"},
    )
    app = _build_app(
        analysis_store,
        history_logger,
        config_path,
        metadata_provider=lambda: metadata,
    )
    analysis_store.update(
        _make_trace(
            tick_id=1,
            active_playlist_before="test_pl",
            active_playlist_after="test_pl",
            matched_playlist="missing_playlist",
            executed=False,
            action_kind=ActionKind.HOLD,
            reason_code=ActionReasonCode.HOLD_SAME_PLAYLIST,
        )
    )

    status, body = wsgi_get(app, "/api/analysis/window")

    assert "200" in status
    tick = body["ticks"][0]
    assert tick["summary"]["activePlaylist"] == {
        "name": "test_pl",
        "display": "Test Playlist",
        "color": "#5BB8D4",
    }
    assert tick["summary"]["matchedPlaylist"] == {
        "name": "missing_playlist",
        "display": "missing_playlist",
        "color": None,
    }
    assert tick["act"]["topMatches"][0]["playlist"] == {
        "name": "focus",
        "display": "focus",
        "color": None,
    }


def test_api_analysis_window_invalid_count(app):
    status, body = wsgi_request(app, "GET", "/api/analysis/window", query="count=abc")
    assert "400" in status
    assert body["error"] == "invalid_count"

    status, body = wsgi_request(app, "GET", "/api/analysis/window", query="count=0")
    assert "400" in status
    assert body["error"] == "invalid_count"


def test_api_health(app):
    status, body = wsgi_get(app, "/api/health")
    assert "200" in status
    assert body == {"ok": True}


def test_dashboard_http_server_binds_requested_port(analysis_store, history_logger, config_path):
    requested_port = _find_free_port()
    server = DashboardHTTPServer(
        analysis_store,
        history_logger,
        config_path,
        requested_port=requested_port,
    )

    try:
        server.start()

        assert server.port == requested_port

        with urllib.request.urlopen(f"http://127.0.0.1:{requested_port}/api/health", timeout=5) as response:
            assert response.status == 200
            assert json.loads(response.read().decode("utf-8")) == {"ok": True}
    finally:
        server.stop()


def test_parse_args_accepts_dashboard_api_port(monkeypatch):
    import main

    monkeypatch.setattr("sys.argv", ["main.py", "--dashboard-api-port", "38417"])

    args = main._parse_args()

    assert args.dashboard_api_port == 38417


def test_resolve_static_root_targets_dashboard_v2():
    static_root = _resolve_static_root()
    assert static_root.endswith(os.path.join(DASHBOARD_STATIC_APP_DIR, DASHBOARD_STATIC_DIST_DIR))


def test_api_history_no_logger(analysis_store, config_path):
    app = _build_app(analysis_store, None, config_path)
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

    status, _ = wsgi_request(app, "GET", "/api/history", query=f"limit=5&from={first_ts}")
    assert "200" in status


def test_api_history_aggregate_no_logger(analysis_store, config_path):
    app = _build_app(analysis_store, None, config_path)
    status, body = wsgi_get(app, "/api/history/aggregate")
    assert "200" in status
    assert body == {"buckets": [], "total_seconds": 0}


def test_api_history_aggregate_with_data(app, history_logger):
    history_logger.write(EventType.START, {"playlist": "A"})
    history_logger.write(
        EventType.PLAYLIST_SWITCH,
        {"playlist_from": "", "playlist_to": "FOCUS"},
    )
    status, body = wsgi_get(app, "/api/history/aggregate")
    assert "200" in status
    assert "buckets" in body
    assert "total_seconds" in body


def test_api_history_aggregate_with_bucket_param(app, history_logger):
    history_logger.write(EventType.START, {"playlist": "A"})
    status, body = wsgi_request(app, "GET", "/api/history/aggregate", query="bucket=30")
    assert "200" in status
    assert "buckets" in body


def test_api_config_returns_config(app):
    status, body = wsgi_get(app, "/api/config")
    assert "200" in status
    assert body["wallpaper_engine_path"] == "C:\\fake\\wallpaper64.exe"
    assert body["playlists"][0]["color"] == "#5BB8D4"


def test_api_config_not_found(analysis_store, history_logger):
    app = _build_app(analysis_store, history_logger, "/nonexistent/config.json")
    status, body = wsgi_get(app, "/api/config")
    assert "404" in status
    assert body["error"] == "config_not_found"


def test_api_config_invalid_file(analysis_store, history_logger, tmp_path):
    path = os.path.join(str(tmp_path), "bad_config.json")
    with open(path, "w", encoding="utf-8") as file:
        file.write("not json")
    app = _build_app(analysis_store, history_logger, path)
    status, body = wsgi_get(app, "/api/config")
    assert "500" in status
    assert body["error"] == "invalid_config"


def test_api_config_save_valid(app, config_path):
    payload = {
        "wallpaper_engine_path": "C:\\valid\\wallpaper64.exe",
        "playlists": [{"name": "pl", "color": "#F5C518", "tags": {"#focus": 1.0}}],
    }
    status, body = wsgi_post(app, "/api/config", payload)
    assert "200" in status
    assert body == {"ok": True}

    with open(config_path, "r", encoding="utf-8") as file:
        saved = json.load(file)
    assert saved["wallpaper_engine_path"] == "C:\\valid\\wallpaper64.exe"
    assert saved["playlists"][0]["color"] == "#F5C518"


def test_api_config_save_no_body(app):
    status, body = wsgi_post(app, "/api/config", None)
    assert "400" in status
    assert body["error"] == "no_json_body"


def test_api_config_save_validation_failed(analysis_store, history_logger, tmp_path):
    path = os.path.join(str(tmp_path), "temp_config.json")
    app = _build_app(analysis_store, history_logger, path)
    payload = {
        "wallpaper_engine_path": "C:\\x\\wallpaper64.exe",
        "playlists": [{"name": "", "color": "#FFF", "tags": {}}],
    }
    status, body = wsgi_post(app, "/api/config", payload)
    assert "422" in status
    assert body["error"] == "validation_failed"
    assert len(body["details"]) > 0
    assert any(detail["field"] == "playlists.0.color" for detail in body["details"])
    assert not os.path.exists(path + ".tmp")


def test_api_tags_presets(app):
    from core.policies import KNOWN_TAGS

    status, body = wsgi_get(app, "/api/tags/presets")
    assert "200" in status
    assert body == KNOWN_TAGS


def test_api_playlists_scan_no_config(analysis_store, history_logger, monkeypatch):
    monkeypatch.setattr("utils.we_path.find_we_config_json", lambda path: None)
    app = _build_app(analysis_store, history_logger, "/nonexistent/config.json")
    status, body = wsgi_get(app, "/api/playlists/scan")
    assert "200" in status
    assert body["error"] == "we_config_not_found"


def test_api_we_path_no_config(analysis_store, history_logger, tmp_path, monkeypatch):
    monkeypatch.setattr("utils.we_path.find_wallpaper_engine", lambda path: None)
    path = os.path.join(str(tmp_path), "no_config.json")
    app = _build_app(analysis_store, history_logger, path)
    status, body = wsgi_get(app, "/api/we-path")
    assert "200" in status
    assert body["valid"] is False


def test_flatten_errors_no_errors_attr():
    class FakeExc(Exception):
        pass

    result = _flatten_errors(FakeExc("something broke"))
    assert result == [{"field": "", "message": "something broke"}]
