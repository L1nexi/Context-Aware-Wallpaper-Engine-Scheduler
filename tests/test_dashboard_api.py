from __future__ import annotations

import getpass
import io
import json
import socket
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from configurations.profile import Profile
from configurations.profile_store import ProfileStore
from configurations.runtime_models import PlaylistConfig
from core.models.context import Context, WeatherData, WindowData
from core.models.playlist import Playlists
from core.models.trace import (
    Action,
    ActionResult,
    ActPlan,
    BlockerEvaluation,
    Decision,
    DecisionMode,
    Match,
    ScheduleTrace,
    TickTrace,
)
from core.runtime.engine import Engine
from core.runtime.profile_manager import ProfileManager
from core.state.tick_history import TickHistoryStore
from ui.dashboard import (
    DashboardHTTPServer,
    build_dashboard_app,
)


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
def tick_history():
    return TickHistoryStore(capacity=300)


@pytest.fixture(autouse=True)
def weather_api(monkeypatch):
    class Response:
        ok = True

        @staticmethod
        def json():
            return {
                "weather": [{"id": 800, "main": "Clear"}],
                "sys": {"sunrise": 1, "sunset": 2},
            }

    monkeypatch.setattr("core.sensors.weather.requests.get", lambda *_args, **_kwargs: Response())


def _wallpaper_engine_path(tmp_path: Path) -> str:
    executable = tmp_path / "wallpaper64.exe"
    executable.write_text("fake", encoding="utf-8")
    data = {
        getpass.getuser(): {
            "general": {
                "playlists": [
                    {"name": "WORK", "items": ["work-1"]},
                    {"name": "NEW", "items": ["new-1", "new-2"]},
                ]
            }
        }
    }
    (tmp_path / "config.json").write_text(json.dumps(data), encoding="utf-8")
    return str(executable)


@pytest.fixture
def profile_manager(tmp_path):
    manager = ProfileManager(str(tmp_path))
    ProfileStore(str(tmp_path)).commit(Profile.model_validate(_profile_payload(_wallpaper_engine_path(tmp_path))))
    engine = Engine.from_config(manager.load_initial_config())
    manager.accept_updates()
    stopped = threading.Event()

    def process_profile_updates() -> None:
        while not stopped.is_set():
            manager.process_pending(engine)
            stopped.wait(0.001)

    worker = threading.Thread(target=process_profile_updates, daemon=True)
    worker.start()
    yield manager
    stopped.set()
    worker.join(timeout=1)
    manager.reject_updates()


@pytest.fixture
def app(tick_history, profile_manager):
    return build_dashboard_app(tick_history, profile_manager)


def _make_wsgi_environ(method, path, query="", body=None, content_type="application/json"):
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
        env["CONTENT_TYPE"] = content_type
        env["CONTENT_LENGTH"] = str(len(body_bytes))
    return env


def wsgi_request(app, method, path, query="", body=None, content_type="application/json"):
    env = _make_wsgi_environ(method, path, query, body, content_type)
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


def _profile_payload(wallpaper_engine_path: str, *, playlist: str = "WORK") -> dict:
    return Profile.model_validate(
        {
            "wallpaper_engine_path": wallpaper_engine_path,
            "weather": {
                "api_key": "test-key",
                "location": {
                    "name": "上海",
                    "latitude": 31.2304,
                    "longitude": 121.4737,
                },
            },
            "scenes": {"day_work": playlist},
        }
    ).model_dump(mode="json")


def _profile_payload_for(manager: ProfileManager, *, playlist: str = "WORK") -> dict:
    profile = manager.get_profile()
    assert profile is not None
    return _profile_payload(profile.wallpaper_engine_path, playlist=playlist)


def _make_trace(
    *,
    tick_id: int = 1,
    paused: bool = False,
    active_playlist_before: str = "",
    matched_playlist: str | None = None,
    target_playlist: str | None = None,
    executed: bool = False,
    action_kind: Action = Action.HOLD,
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


def test_api_tick_history_window_empty(app):
    status, body = wsgi_get(app, "/api/tick-history/window")
    assert "200" in status
    assert body == {"liveTickId": None, "ticks": []}


def test_api_tick_history_window_returns_recent(tick_history, profile_manager):
    app = build_dashboard_app(tick_history, profile_manager)
    for tick_id in range(1, 5):
        tick_history.update(_make_trace(tick_id=tick_id))

    status, body = wsgi_request(app, "GET", "/api/tick-history/window", query="count=2")
    assert "200" in status
    assert body["liveTickId"] == 4
    assert [tick["summary"]["tickId"] for tick in body["ticks"]] == [3, 4]


def test_api_tick_history_window_projects_current_playlist_metadata(
    tick_history,
    profile_manager,
):
    Playlists.configure(
        {
            "focus": PlaylistConfig(display="Focus Flow", color="#F5C518", item_count=10),
            "rainy": PlaylistConfig(display="Rainy Mood", color="#4A90D9", item_count=5),
            "test_pl": PlaylistConfig(display="Test Playlist", color="#5BB8D4", item_count=1),
        }
    )
    app = build_dashboard_app(tick_history, profile_manager)
    tick_history.update(
        _make_trace(
            tick_id=1,
            active_playlist_before="test_pl",
            matched_playlist="missing_playlist",
            executed=False,
            action_kind=Action.HOLD,
        )
    )

    status, body = wsgi_get(app, "/api/tick-history/window")

    assert "200" in status
    tick = body["ticks"][0]
    assert tick["summary"]["activePlaylists"] == [
        {"name": "test_pl", "display": "Test Playlist", "color": "#5BB8D4"},
    ]
    assert tick["summary"]["matchedPlaylists"] == [
        {"name": "missing_playlist", "display": "missing_playlist", "color": None},
    ]
    assert tick["act"]["topMatches"][0]["playlist"] == {
        "name": "focus",
        "display": "Focus Flow",
        "color": "#F5C518",
    }


def test_api_tick_history_window_invalid_count(app):
    status, body = wsgi_request(app, "GET", "/api/tick-history/window", query="count=abc")
    assert "400" in status
    assert body["error"] == "invalid_count"

    status, body = wsgi_request(app, "GET", "/api/tick-history/window", query="count=0")
    assert "400" in status
    assert body["error"] == "invalid_count"


def test_api_profile_returns_current_committed_profile(tick_history, profile_manager):
    app = build_dashboard_app(tick_history, profile_manager)

    status, body = wsgi_get(app, "/api/profile")

    assert "200" in status
    assert "revision" not in body["profile"]
    assert body["profile"]["scenes"] == {"day_work": "WORK"}


def test_api_apply_profile_returns_normalized_committed_profile(tick_history, profile_manager):
    draft = _profile_payload_for(profile_manager, playlist="NEW")
    committed = Profile.model_validate(draft)
    app = build_dashboard_app(tick_history, profile_manager)

    status, body = wsgi_post(app, "/api/profile/apply", draft)

    assert "200" in status
    assert body == {
        "status": "applied",
        "profile": committed.model_dump(mode="json"),
    }

    profile_status, profile_body = wsgi_get(app, "/api/profile")
    assert "200" in profile_status
    assert profile_body["profile"]["scenes"] == {"day_work": "NEW"}


def test_api_apply_profile_rejects_invalid_payload(tick_history, profile_manager):
    app = build_dashboard_app(tick_history, profile_manager)
    payload = _profile_payload_for(profile_manager)
    payload["disturbance"]["avoid_fullscreen"] = False

    status, body = wsgi_post(app, "/api/profile/apply", payload)

    assert "400" in status
    assert body["error"] == "invalid_profile"
    assert body["issues"][0]["path"] == ["disturbance", "avoid_fullscreen"]
    assert profile_manager.get_profile().scenes == {"day_work": "WORK"}


def test_api_apply_profile_rejects_malformed_json(tick_history, profile_manager):
    app = build_dashboard_app(tick_history, profile_manager)

    status, body = wsgi_request(app, "POST", "/api/profile/apply", body=b"{invalid")

    assert "400" in status
    assert body["error"] == "invalid_profile"
    assert profile_manager.get_profile().scenes == {"day_work": "WORK"}


def test_api_apply_profile_rejects_non_json_content_type(tick_history, profile_manager):
    app = build_dashboard_app(tick_history, profile_manager)
    body_bytes = json.dumps(_profile_payload_for(profile_manager)).encode("utf-8")

    status, body = wsgi_request(
        app,
        "POST",
        "/api/profile/apply",
        body=body_bytes,
        content_type="text/plain",
    )

    assert "415" in status
    assert body == {"error": "unsupported_media_type"}
    assert profile_manager.get_profile().scenes == {"day_work": "WORK"}


def test_api_apply_profile_reports_failed_stage(tick_history, profile_manager):
    app = build_dashboard_app(tick_history, profile_manager)
    invalid_runtime = _profile_payload(r"Z:\missing\wallpaper64.exe", playlist="NEW")

    status, body = wsgi_post(app, "/api/profile/apply", invalid_runtime)

    assert "500" in status
    assert body == {
        "error": "profile_apply_failed",
        "stage": "compile",
        "detail": "wallpaper_engine_config_not_found",
    }


def test_dashboard_http_server_binds_requested_port(app):
    requested_port = _find_free_port()
    server = DashboardHTTPServer(
        app,
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
