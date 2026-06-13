from __future__ import annotations

import io
import json
import os
import socket
import time
import urllib.request

import pytest

from configurations.runtime_models import PlaylistConfig
from core.models.context import Context, WeatherData, WindowData
from core.models.playlist import Playlists
from core.models.trace import (
    Action,
    ActionResult,
    ActivityDetails,
    ActivityEvaluation,
    ActPlan,
    BlockerEvaluation,
    Decision,
    DecisionMode,
    Match,
    ScheduleTrace,
    TickTrace,
    WeatherDetails,
    WeatherEvaluation,
)
from ui.dto.diagnostic import build_tick_snapshot
from ui.frontend import (
    FRONTEND_STATIC_APP_DIR,
    FRONTEND_STATIC_DIST_DIR,
    FrontendHTTPServer,
    _build_app,
    _resolve_static_root,
)
from ui.tick_trace_store import TickTraceStore


@pytest.fixture(autouse=True)
def _configure_playlists():
    """Configure Playlists with test data for all tests."""
    Playlists.configure(
        {
            "focus": PlaylistConfig(display="Focus Flow", color="#F5C518", item_count=10),
            "rainy": PlaylistConfig(display="Rainy Mood", color="#4A90D9", item_count=5),
            "idle": PlaylistConfig(display="", color="#2E5F8A", item_count=3),
        }
    )
    yield
    Playlists.configure({})


@pytest.fixture
def tick_store():
    return TickTraceStore(tick_history=300)


@pytest.fixture
def app(tick_store):
    return _build_app(tick_store)


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


def _make_trace(
    *,
    tick_id: int = 1,
    paused: bool = False,
    active_playlist_before: str = "",
    matched_playlist: str | None = None,
    target_playlist: str | None = None,
    executed: bool = False,
    action_kind: Action = Action.HOLD,
    semantic_continuity: bool = False,
    evaluation: BlockerEvaluation | None = None,
    weather: WeatherData | None = None,
    policy_evaluations: list | None = None,
) -> TickTrace:
    current_time = time.localtime(1714800000)
    playlist_matches = [("focus", 0.91), ("rainy", 0.66)]
    best_playlists = Playlists([matched_playlist]) if matched_playlist else Playlists()
    plan_active = Playlists([active_playlist_before]) if active_playlist_before else Playlists()
    return TickTrace(
        tick_id=tick_id,
        ts=1714800000.0 + tick_id,
        paused=paused,
        pause_until=1714803600.0 if paused else 0.0,
        schedule=ScheduleTrace(
            context=Context(
                window=WindowData(process="chrome.exe", title="Code Review"),
                idle=12.5,
                cpu=27.25,
                fullscreen=False,
                weather=weather,
                time=current_time,
            ),
            match=Match(
                best_playlists=best_playlists,
                playlist_matches=playlist_matches,
                raw_context_vector={"focus": 0.8, "rain": 0.4},
                resolved_context_vector={"focus": 0.8, "rain": 0.4},
                fallback_expansions={"storm": {"rain": 0.25}},
                policy_evaluations=policy_evaluations or [],
                max_policy_magnitude=1.2,
            ),
            plan=ActPlan(mode=DecisionMode.NORMAL, active_playlists=plan_active),
            decision=Decision(
                action=action_kind,
                target=best_playlists,
                semantic_continuity=semantic_continuity,
                evaluation=evaluation,
            ),
            action=ActionResult(
                target_playlist=target_playlist,
                executed=executed,
            ),
        ),
    )


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_tick_trace_store_read_window_empty(tick_store):
    window = tick_store.read_window()

    assert window.live_tick_id is None
    assert window.traces == []


def test_tick_trace_store_read_window_returns_recent(tick_store):
    for tick_id in range(1, 6):
        tick_store.update(_make_trace(tick_id=tick_id))

    window = tick_store.read_window(2)

    assert window.live_tick_id == 5
    assert [trace.tick_id for trace in window.traces] == [4, 5]


def test_build_tick_snapshot_maps_diagnostic_fields():
    evaluation = BlockerEvaluation(
        blocked_by=[],
        cooldown_remaining=15.0,
        idle_seconds=12.5,
        idle_threshold=60.0,
        cpu_percent=27.25,
        cpu_threshold=85.0,
        fullscreen=False,
        force_after_remaining=120.0,
    )
    activity_policy = ActivityEvaluation(
        policy_id="activity",
        enabled=True,
        active=True,
        weight=1.0,
        salience=1.0,
        intensity=0.5,
        effective_magnitude=0.5,
        direction={"focus": 1.0},
        raw_contribution={"focus": 0.5},
        resolved_contribution={"focus": 0.5},
        dominant_tag="focus",
        details=ActivityDetails(
            match_source="title",
            matched_rule="code",
            matched_tag="focus",
            window_title="Code Review",
            process="chrome.exe",
            ema_active=True,
        ),
    )
    weather_policy = WeatherEvaluation(
        policy_id="weather",
        enabled=True,
        active=True,
        weight=1.0,
        salience=1.0,
        intensity=0.4,
        effective_magnitude=0.4,
        direction={"rain": 1.0},
        raw_contribution={"rain": 0.4},
        resolved_contribution={"rain": 0.4},
        dominant_tag="rain",
        details=WeatherDetails(
            weather_id=501,
            weather_main="Rain",
            available=True,
            mapped=True,
        ),
    )
    trace = _make_trace(
        tick_id=7,
        active_playlist_before="idle",
        matched_playlist="focus",
        executed=False,
        action_kind=Action.HOLD,
        semantic_continuity=True,
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

    snapshot = build_tick_snapshot(trace)

    assert snapshot["summary"]["tickId"] == 7
    assert snapshot["summary"]["activePlaylists"] == ["idle"]
    assert snapshot["summary"]["matchedPlaylists"] == ["focus"]
    assert "activePlaylistDisplay" not in snapshot["summary"]
    assert "activePlaylistColor" not in snapshot["summary"]
    assert "matchedPlaylistDisplay" not in snapshot["summary"]
    assert "matchedPlaylistColor" not in snapshot["summary"]
    assert "enabled" not in snapshot["sense"]["weather"]
    assert snapshot["sense"]["weather"]["available"] is True
    assert snapshot["sense"]["weather"]["stale"] is True
    assert "think" not in snapshot
    assert snapshot["match"]["fallbackExpansions"]["storm"][0]["resolvedTag"] == "rain"
    assert snapshot["match"]["policies"][0]["policyId"] == "activity"
    assert snapshot["match"]["policies"][1]["details"]["mapped"] is True
    assert snapshot["match"]["policies"] is not None
    assert snapshot["match"]["bestPlaylists"] == ["focus"]
    assert snapshot["match"]["topMatches"][0] == {"playlist": "focus", "score": 0.91}
    assert snapshot["match"]["topMatches"][1] == {"playlist": "rainy", "score": 0.66}
    assert snapshot["plan"] == {"mode": "normal", "activePlaylists": ["idle"]}
    assert snapshot["decide"]["targetPlaylists"] == ["focus"]
    assert snapshot["decide"]["semanticContinuity"] is True
    assert "semanticContinuity" not in snapshot["decide"]["evaluation"]
    assert snapshot["act"] == {"targetPlaylist": None, "executed": False}


def test_build_tick_snapshot_maps_target_playlist():
    trace = _make_trace(
        tick_id=10,
        active_playlist_before="idle",
        matched_playlist="focus",
        target_playlist="focus",
        executed=True,
        action_kind=Action.SWITCH,
    )

    snapshot = build_tick_snapshot(trace)

    assert snapshot["decide"]["targetPlaylists"] == ["focus"]
    assert snapshot["act"]["targetPlaylist"] == "focus"


def test_build_tick_snapshot_maps_paused_tick():
    trace = _make_trace(
        tick_id=8,
        paused=True,
        active_playlist_before="focus",
        matched_playlist="rainy",
        executed=False,
        action_kind=Action.PAUSE,
        evaluation=None,
        weather=None,
    )

    snapshot = build_tick_snapshot(trace)

    assert snapshot["summary"]["action"] == "pause"
    assert snapshot["summary"]["paused"] is True
    assert snapshot["summary"]["hasEvent"] is False
    assert snapshot["summary"]["activePlaylists"] == ["focus"]
    assert snapshot["summary"]["matchedPlaylists"] == ["rainy"]
    assert snapshot["sense"]["weather"]["available"] is False
    assert snapshot["decide"]["evaluation"] is None
    assert snapshot["decide"]["targetPlaylists"] == ["rainy"]
    assert snapshot["match"]["bestPlaylists"] == ["rainy"]


def test_build_tick_snapshot_maps_unknown_playlist_ref_with_null_color():
    trace = _make_trace(
        tick_id=9,
        active_playlist_before="unknown_active",
        matched_playlist="unknown_match",
        executed=False,
        action_kind=Action.HOLD,
        evaluation=None,
        weather=None,
    )

    snapshot = build_tick_snapshot(trace)

    assert snapshot["summary"]["activePlaylists"] == ["unknown_active"]
    assert snapshot["summary"]["matchedPlaylists"] == ["unknown_match"]
    assert snapshot["plan"]["activePlaylists"] == ["unknown_active"]


def test_api_tick_traces_window_empty(app):
    status, body = wsgi_get(app, "/api/tick-traces/window")
    assert "200" in status
    assert body == {
        "liveTickId": None,
        "catalog": {
            "playlists": [
                {"name": "focus", "display": "Focus Flow", "color": "#F5C518", "itemCount": 10},
                {"name": "rainy", "display": "Rainy Mood", "color": "#4A90D9", "itemCount": 5},
                {"name": "idle", "display": "idle", "color": "#2E5F8A", "itemCount": 3},
            ],
        },
        "ticks": [],
    }


def test_api_tick_traces_window_returns_recent(tick_store):
    app = _build_app(tick_store)
    for tick_id in range(1, 5):
        tick_store.update(_make_trace(tick_id=tick_id))

    status, body = wsgi_request(app, "GET", "/api/tick-traces/window", query="count=2")
    assert "200" in status
    assert body["liveTickId"] == 4
    assert [tick["summary"]["tickId"] for tick in body["ticks"]] == [3, 4]


def test_api_tick_traces_window_projects_traces_with_current_playlist_metadata(
    tick_store,
):
    Playlists.configure(
        {
            "focus": PlaylistConfig(display="Focus Flow", color="#F5C518", item_count=10),
            "rainy": PlaylistConfig(display="Rainy Mood", color="#4A90D9", item_count=5),
            "test_pl": PlaylistConfig(display="Test Playlist", color="#5BB8D4", item_count=1),
        }
    )
    app = _build_app(tick_store)
    tick_store.update(
        _make_trace(
            tick_id=1,
            active_playlist_before="test_pl",
            matched_playlist="missing_playlist",
            executed=False,
            action_kind=Action.HOLD,
        )
    )

    status, body = wsgi_get(app, "/api/tick-traces/window")

    assert "200" in status
    tick = body["ticks"][0]
    assert body["catalog"]["playlists"] == [
        {"name": "focus", "display": "Focus Flow", "color": "#F5C518", "itemCount": 10},
        {"name": "rainy", "display": "Rainy Mood", "color": "#4A90D9", "itemCount": 5},
        {"name": "test_pl", "display": "Test Playlist", "color": "#5BB8D4", "itemCount": 1},
    ]
    assert tick["summary"]["activePlaylists"] == ["test_pl"]
    assert tick["summary"]["matchedPlaylists"] == ["missing_playlist"]
    assert tick["match"]["topMatches"][0] == {"playlist": "focus", "score": 0.91}


def test_api_tick_traces_window_invalid_count(app):
    status, body = wsgi_request(app, "GET", "/api/tick-traces/window", query="count=abc")
    assert "400" in status
    assert body["error"] == "invalid_count"

    status, body = wsgi_request(app, "GET", "/api/tick-traces/window", query="count=0")
    assert "400" in status
    assert body["error"] == "invalid_count"


def test_api_health(app):
    status, body = wsgi_get(app, "/api/health")
    assert "200" in status
    assert body == {"ok": True}


def test_frontend_http_server_binds_requested_port(tick_store):
    requested_port = _find_free_port()
    server = FrontendHTTPServer(
        tick_store,
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


def test_parse_args_accepts_server_port(monkeypatch):
    from app.main import _parse_args

    monkeypatch.setattr("sys.argv", ["main.py", "--server-port", "38417"])

    args = _parse_args()

    assert args.server_port == 38417


def test_resolve_static_root_targets_frontend_dist():
    static_root = _resolve_static_root()
    assert static_root.endswith(os.path.join(FRONTEND_STATIC_APP_DIR, FRONTEND_STATIC_DIST_DIR))
