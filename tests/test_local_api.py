from __future__ import annotations

import getpass
import io
import json
import logging
import socket
import threading
import time
import urllib.request
from pathlib import Path

import pytest
import requests

from configurations.profile import Profile
from configurations.profile_store import ProfileStore
from configurations.runtime_models import SceneConfig
from core.models.context import Context, WeatherData, WindowData
from core.models.scene import SceneId, Scenes
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
from server.app import build_api_app
from server.host import APIServer


@pytest.fixture(autouse=True)
def _configure_scenes():
    """Configure Scenes with test data for all tests."""
    Scenes.configure(
        {
            SceneId.DAY_WORK: SceneConfig(playlist="focus", item_count=10),
            SceneId.RAIN: SceneConfig(playlist="rainy", item_count=5),
            SceneId.SUNSET: SceneConfig(playlist="idle", item_count=3),
        }
    )
    yield
    Scenes.configure({})


@pytest.fixture
def tick_history():
    return TickHistoryStore(capacity=300)


@pytest.fixture(autouse=True)
def weather_api(monkeypatch):
    class Response:
        status_code = 200

        @property
        def ok(self):
            return self.status_code == 200

        @staticmethod
        def json():
            return {
                "weather": [{"id": 800, "main": "Clear"}],
                "sys": {"sunrise": 1, "sunset": 2},
            }

    monkeypatch.setattr("integrations.openweather.requests.get", lambda *_args, **_kwargs: Response())


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
    manager.load_initial_profile()
    engine = Engine.from_config(manager.compile_initial_config())
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
    return build_api_app(tick_history, profile_manager)


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


def wsgi_put(app, path, data=None):
    body_bytes = json.dumps(data).encode("utf-8") if data is not None else None
    return wsgi_request(app, "PUT", path, body=body_bytes)


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
    active_scene_before: SceneId | None = None,
    matched_scene: SceneId | None = None,
    target_playlist: str | None = None,
    executed: bool = False,
    action_kind: Action = Action.HOLD,
    evaluation: BlockerEvaluation | None = None,
    weather: WeatherData | None = None,
    policy_evaluations: list | None = None,
) -> TickTrace:
    current_time = time.localtime(1714800000)
    scene_matches = [(SceneId.DAY_WORK, 0.91), (SceneId.RAIN, 0.66)]
    best_scenes = Scenes([matched_scene]) if matched_scene else Scenes()
    plan_active = Scenes([active_scene_before]) if active_scene_before else Scenes()
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
                best_scenes=best_scenes,
                scene_matches=scene_matches,
                raw_context_vector={"focus": 0.8, "rain": 0.4},
                resolved_context_vector={"focus": 0.8, "rain": 0.4},
                fallback_expansions={"storm": {"rain": 0.25}},
                policy_evaluations=policy_evaluations or [],
                max_policy_magnitude=1.2,
            ),
            plan=ActPlan(mode=DecisionMode.NORMAL, active_scenes=plan_active),
            decision=Decision(
                action=action_kind,
                target=best_scenes,
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
    status, body = wsgi_get(app, "/api/tick-history")
    assert "200" in status
    assert body == {"liveTickId": None, "ticks": []}


def test_api_tick_history_window_returns_recent(tick_history, profile_manager):
    app = build_api_app(tick_history, profile_manager)
    for tick_id in range(1, 5):
        tick_history.update(_make_trace(tick_id=tick_id))

    status, body = wsgi_request(app, "GET", "/api/tick-history", query="limit=2")
    assert "200" in status
    assert body["liveTickId"] == 4
    assert [tick["summary"]["tickId"] for tick in body["ticks"]] == [3, 4]


def test_api_tick_history_window_projects_scene_identity_and_target_playlist(
    tick_history,
    profile_manager,
):
    Scenes.configure(
        {
            SceneId.DAY_WORK: SceneConfig(playlist="focus", item_count=10),
            SceneId.RAIN: SceneConfig(playlist="rainy", item_count=5),
            SceneId.SUNSET: SceneConfig(playlist="test_pl", item_count=1),
        }
    )
    app = build_api_app(tick_history, profile_manager)
    tick_history.update(
        _make_trace(
            tick_id=1,
            active_scene_before=SceneId.DAY_WORK,
            matched_scene=SceneId.SUNSET,
            target_playlist="test_pl",
            executed=True,
            action_kind=Action.SWITCH,
        )
    )

    status, body = wsgi_get(app, "/api/tick-history")

    assert "200" in status
    tick = body["ticks"][0]
    assert tick["summary"]["activeScenes"] == [{"id": "sunset"}]
    assert tick["summary"]["matchedScenes"] == [{"id": "sunset"}]
    assert tick["think"]["decision"]["activeScenes"] == [{"id": "day_work"}]
    assert tick["think"]["decision"]["targetScenes"] == [{"id": "sunset"}]
    assert tick["think"]["decision"]["targetPlaylist"] == {"name": "test_pl"}
    assert tick["act"]["topMatches"][0]["scene"] == {"id": "day_work"}


def test_api_tick_history_window_invalid_count(app):
    status, body = wsgi_request(app, "GET", "/api/tick-history", query="limit=abc")
    assert "422" in status
    assert body["error"] == "invalid_count"

    status, body = wsgi_request(app, "GET", "/api/tick-history", query="limit=0")
    assert "422" in status
    assert body["error"] == "invalid_count"


def test_removed_setup_api_does_not_fall_through_to_spa(app):
    status, body = wsgi_get(app, "/api/setup/scenes")

    assert "404" in status
    assert body == {"error": "not_found"}


def test_removed_profile_create_api_returns_json_not_found(app):
    status, body = wsgi_post(app, "/api/profile/create", {"unused": True})

    assert "404" in status
    assert body == {"error": "not_found"}


def test_api_profile_returns_current_committed_profile(tick_history, profile_manager):
    app = build_api_app(tick_history, profile_manager)

    status, body = wsgi_get(app, "/api/profile")

    assert "200" in status
    assert "revision" not in body["profile"]
    assert body["profile"]["scenes"] == {"day_work": "WORK"}


def test_api_setup_scans_wallpaper_engine_playlists(tmp_path: Path, tick_history):
    executable = _wallpaper_engine_path(tmp_path)
    app = build_api_app(tick_history, ProfileManager(str(tmp_path / "profile")))

    status, body = wsgi_post(
        app,
        "/api/wallpaper-engine/playlist-scans",
        {"wallpaper_engine_path": executable},
    )

    assert "201" in status
    assert body == {
        "wallpaper_engine_path": executable,
        "playlists": [
            {"name": "WORK", "item_count": 1},
            {"name": "NEW", "item_count": 2},
        ],
    }


def test_api_setup_reports_missing_wallpaper_engine_executable(tmp_path: Path, tick_history):
    app = build_api_app(tick_history, ProfileManager(str(tmp_path / "profile")))

    status, body = wsgi_post(
        app,
        "/api/wallpaper-engine/playlist-scans",
        {"wallpaper_engine_path": str(tmp_path / "missing.exe")},
    )

    assert "404" in status
    assert body == {"error": "wallpaper_engine_executable_not_found"}


def test_api_setup_reports_unreadable_wallpaper_engine_config(tmp_path: Path, tick_history):
    executable = tmp_path / "wallpaper64.exe"
    executable.write_text("fake", encoding="utf-8")
    app = build_api_app(tick_history, ProfileManager(str(tmp_path / "profile")))

    status, body = wsgi_post(
        app,
        "/api/wallpaper-engine/playlist-scans",
        {"wallpaper_engine_path": str(executable)},
    )

    assert "422" in status
    assert body == {"error": "wallpaper_engine_config_not_found"}


def test_api_setup_detects_city_location_without_exposing_ip(app, monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "ip": "203.0.113.10",
                "city": "Shanghai",
                "region": "Shanghai",
                "country_name": "China",
                "latitude": 31.2304,
                "longitude": 121.4737,
            }

    monkeypatch.setattr("integrations.ip_location.requests.get", lambda *_args, **_kwargs: Response())

    status, body = wsgi_request(app, "POST", "/api/location-estimates")

    assert "201" in status
    assert body == {
        "location": {
            "name": "Shanghai, China",
            "latitude": 31.2304,
            "longitude": 121.4737,
        }
    }


def test_api_setup_reports_unavailable_location_detection(app, monkeypatch):
    class Response:
        status_code = 429

    monkeypatch.setattr("integrations.ip_location.requests.get", lambda *_args, **_kwargs: Response())

    status, body = wsgi_request(app, "POST", "/api/location-estimates")

    assert "503" in status
    assert body == {"error": "location_detection_unavailable"}


def test_api_setup_logs_safe_location_failure_reason(app, monkeypatch, caplog):
    def proxy_error(*_args, **_kwargs):
        raise requests.exceptions.ProxyError("proxy URL included private-token=fake-secret")

    monkeypatch.setattr("integrations.ip_location.requests.get", proxy_error)

    status, _body = wsgi_request(app, "POST", "/api/location-estimates")

    assert "503" in status
    warnings = [record.message for record in caplog.records if record.name == "WEScheduler.API"]
    assert any("Location estimate unavailable: reason=proxy_error" in message for message in warnings)
    assert all("fake-secret" not in message for message in warnings)


def test_api_create_profile_persists_first_profile(tmp_path: Path, tick_history):
    executable = _wallpaper_engine_path(tmp_path)
    config_dir = tmp_path / "profile"
    manager = ProfileManager(str(config_dir))
    app = build_api_app(tick_history, manager)
    draft = _profile_payload(executable)

    status, body = wsgi_post(app, "/api/profile", draft)

    assert "201" in status
    assert body == {"status": "created", "profile": draft}

    profile_status, profile_body = wsgi_get(app, "/api/profile")
    assert "200" in profile_status
    assert profile_body == {"profile": draft}


def test_api_create_profile_leaves_profile_absent_when_weather_key_is_rejected(
    tmp_path: Path,
    tick_history,
    monkeypatch,
    caplog,
):
    class Response:
        status_code = 401

    monkeypatch.setattr("integrations.openweather.requests.get", lambda *_args, **_kwargs: Response())
    executable = _wallpaper_engine_path(tmp_path)
    config_dir = tmp_path / "profile"
    manager = ProfileManager(str(config_dir))
    app = build_api_app(tick_history, manager)

    status, body = wsgi_post(app, "/api/profile", _profile_payload(executable))

    assert "422" in status
    assert body == {
        "error": "weather_validation_failed",
        "issues": [
            {
                "path": ["weather", "api_key"],
                "code": "weather_api_key_invalid",
                "message": "weather_api_key_invalid",
            }
        ],
    }

    profile_status, profile_body = wsgi_get(app, "/api/profile")
    assert "404" in profile_status
    assert profile_body == {"error": "profile_not_found"}
    assert any(
        "Weather validation rejected: operation=create reason=weather_api_key_invalid" in record.message
        for record in caplog.records
        if record.name == "WEScheduler.API"
    )


def test_api_create_profile_rejects_invalid_fields(tmp_path: Path, tick_history):
    app = build_api_app(tick_history, ProfileManager(str(tmp_path / "profile")))

    status, body = wsgi_post(app, "/api/profile", {"weather": {}})

    assert "422" in status
    assert body["error"] == "invalid_profile"
    assert body["issues"]


def test_api_create_profile_leaves_profile_absent_when_weather_validation_is_unavailable(
    tmp_path: Path,
    tick_history,
    monkeypatch,
):
    class Response:
        status_code = 500

    monkeypatch.setattr("integrations.openweather.requests.get", lambda *_args, **_kwargs: Response())
    executable = _wallpaper_engine_path(tmp_path)
    config_dir = tmp_path / "profile"
    manager = ProfileManager(str(config_dir))
    app = build_api_app(tick_history, manager)

    status, body = wsgi_post(app, "/api/profile", _profile_payload(executable))

    assert "503" in status
    assert body == {"error": "weather_validation_unavailable"}

    profile_status, profile_body = wsgi_get(app, "/api/profile")
    assert "404" in profile_status
    assert profile_body == {"error": "profile_not_found"}


def test_api_create_profile_logs_safe_weather_timeout_reason(tmp_path: Path, tick_history, monkeypatch, caplog):
    def timeout(*_args, **_kwargs):
        raise requests.Timeout("request URL contained appid=fake-secret")

    monkeypatch.setattr("integrations.openweather.requests.get", timeout)
    executable = _wallpaper_engine_path(tmp_path)
    app = build_api_app(tick_history, ProfileManager(str(tmp_path / "profile")))

    status, _body = wsgi_post(app, "/api/profile", _profile_payload(executable))

    assert "503" in status
    warnings = [record.message for record in caplog.records if record.name == "WEScheduler.API"]
    assert any("Weather validation unavailable: operation=create reason=timeout" in message for message in warnings)
    assert all("fake-secret" not in message for message in warnings)


def test_api_create_profile_rejects_incomplete_weather_response(tmp_path: Path, tick_history, monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"weather": []}

    monkeypatch.setattr("integrations.openweather.requests.get", lambda *_args, **_kwargs: Response())
    executable = _wallpaper_engine_path(tmp_path)
    app = build_api_app(tick_history, ProfileManager(str(tmp_path / "profile")))

    status, body = wsgi_post(app, "/api/profile", _profile_payload(executable))

    assert "503" in status
    assert body == {"error": "weather_validation_unavailable"}
    profile_status, profile_body = wsgi_get(app, "/api/profile")
    assert "404" in profile_status
    assert profile_body == {"error": "profile_not_found"}


def test_api_create_profile_rejects_existing_profile(tick_history, profile_manager):
    current = profile_manager.get_profile()
    assert current is not None
    app = build_api_app(tick_history, profile_manager)

    status, body = wsgi_post(
        app,
        "/api/profile",
        _profile_payload(current.wallpaper_engine_path, playlist="NEW"),
    )

    assert "409" in status
    assert body == {"error": "profile_already_exists"}


def test_api_create_profile_reports_conflict_during_weather_outage(tick_history, profile_manager, monkeypatch):
    class Response:
        status_code = 500

    monkeypatch.setattr("integrations.openweather.requests.get", lambda *_args, **_kwargs: Response())
    current = profile_manager.get_profile()
    assert current is not None
    app = build_api_app(tick_history, profile_manager)

    status, body = wsgi_post(app, "/api/profile", _profile_payload(current.wallpaper_engine_path))

    assert "409" in status
    assert body == {"error": "profile_already_exists"}


def test_api_create_profile_reports_conflict_before_startup_load(tmp_path: Path, tick_history, monkeypatch):
    class Response:
        status_code = 500

    monkeypatch.setattr("integrations.openweather.requests.get", lambda *_args, **_kwargs: Response())
    executable = _wallpaper_engine_path(tmp_path)
    config_dir = tmp_path / "profile"
    draft = Profile.model_validate(_profile_payload(executable))
    ProfileStore(str(config_dir)).commit(draft)
    app = build_api_app(tick_history, ProfileManager(str(config_dir)))

    status, body = wsgi_post(app, "/api/profile", draft.model_dump(mode="json"))

    assert "409" in status
    assert body == {"error": "profile_already_exists"}


def test_api_create_profile_reports_failed_stage(tmp_path: Path, tick_history):
    manager = ProfileManager(str(tmp_path / "profile"))
    app = build_api_app(tick_history, manager)
    invalid_runtime = _profile_payload(r"Z:\missing\wallpaper64.exe")

    status, body = wsgi_post(app, "/api/profile", invalid_runtime)

    assert "500" in status
    assert body == {
        "error": "profile_create_failed",
        "stage": "compile",
        "detail": "wallpaper_engine_config_not_found",
    }


def test_setup_route_serves_frontend_spa(tmp_path: Path, monkeypatch, tick_history, profile_manager):
    frontend_dist = tmp_path / "frontend" / "dist"
    frontend_dist.mkdir(parents=True)
    (frontend_dist / "index.html").write_text("<main>setup frontend</main>", encoding="utf-8")
    monkeypatch.setattr("server.spa.get_app_root", lambda: str(tmp_path))
    app = build_api_app(tick_history, profile_manager)

    status, body = wsgi_get(app, "/setup/")

    assert "200" in status
    assert body == "<main>setup frontend</main>"


def test_api_apply_profile_returns_normalized_committed_profile(tick_history, profile_manager):
    draft = _profile_payload_for(profile_manager, playlist="NEW")
    committed = Profile.model_validate(draft)
    app = build_api_app(tick_history, profile_manager)

    status, body = wsgi_put(app, "/api/profile", draft)

    assert "200" in status
    assert body == {
        "status": "applied",
        "profile": committed.model_dump(mode="json"),
    }

    profile_status, profile_body = wsgi_get(app, "/api/profile")
    assert "200" in profile_status
    assert profile_body["profile"]["scenes"] == {"day_work": "NEW"}


def test_profile_apply_log_distinguishes_weather_change(tick_history, profile_manager, caplog):
    caplog.set_level(logging.INFO, logger="WEScheduler.Profile")
    app = build_api_app(tick_history, profile_manager)
    scene_draft = _profile_payload_for(profile_manager, playlist="NEW")

    scene_status, _scene_body = wsgi_put(app, "/api/profile", scene_draft)

    weather_draft = _profile_payload_for(profile_manager, playlist="NEW")
    weather_draft["weather"]["api_key"] = "fake-new-key"
    weather_status, _weather_body = wsgi_put(app, "/api/profile", weather_draft)

    assert "200" in scene_status
    assert "200" in weather_status
    messages = [record.message for record in caplog.records if record.name == "WEScheduler.Profile"]
    assert any("weather_changed=False" in message for message in messages)
    assert any("weather_changed=True" in message for message in messages)
    assert all("fake-new-key" not in message for message in messages)


def test_api_replace_profile_requires_existing_resource(tmp_path: Path, tick_history):
    executable = _wallpaper_engine_path(tmp_path)
    app = build_api_app(tick_history, ProfileManager(str(tmp_path / "profile")))

    status, body = wsgi_put(app, "/api/profile", _profile_payload(executable))

    assert "404" in status
    assert body == {"error": "profile_not_found"}


def test_api_apply_profile_succeeds_during_weather_outage_when_weather_is_unchanged(
    tick_history,
    profile_manager,
    monkeypatch,
):
    class Response:
        status_code = 500

    monkeypatch.setattr("integrations.openweather.requests.get", lambda *_args, **_kwargs: Response())
    app = build_api_app(tick_history, profile_manager)
    draft = _profile_payload_for(profile_manager, playlist="NEW")

    status, body = wsgi_put(app, "/api/profile", draft)

    assert "200" in status
    assert body["status"] == "applied"


def test_api_apply_profile_maps_rejected_location_to_weather_location_field(
    tick_history,
    profile_manager,
    monkeypatch,
):
    class Response:
        status_code = 404

    monkeypatch.setattr("integrations.openweather.requests.get", lambda *_args, **_kwargs: Response())
    app = build_api_app(tick_history, profile_manager)
    draft = _profile_payload_for(profile_manager)
    draft["weather"]["location"]["latitude"] = 30.0

    status, body = wsgi_put(app, "/api/profile", draft)

    assert "422" in status
    assert body["issues"] == [
        {
            "path": ["weather", "location"],
            "code": "weather_location_invalid",
            "message": "weather_location_invalid",
        }
    ]


def test_api_apply_profile_rejects_invalid_payload(tick_history, profile_manager):
    app = build_api_app(tick_history, profile_manager)
    payload = _profile_payload_for(profile_manager)
    payload["disturbance"]["avoid_fullscreen"] = False

    status, body = wsgi_put(app, "/api/profile", payload)

    assert "422" in status
    assert body["error"] == "invalid_profile"
    assert body["issues"][0]["path"] == ["disturbance", "avoid_fullscreen"]
    assert profile_manager.get_profile().scenes == {"day_work": "WORK"}


def test_api_apply_profile_rejects_malformed_json(tick_history, profile_manager):
    app = build_api_app(tick_history, profile_manager)

    status, body = wsgi_request(app, "PUT", "/api/profile", body=b"{invalid")

    assert "400" in status
    assert body["error"] == "invalid_profile"
    assert profile_manager.get_profile().scenes == {"day_work": "WORK"}


def test_api_apply_profile_rejects_non_json_content_type(tick_history, profile_manager):
    app = build_api_app(tick_history, profile_manager)
    body_bytes = json.dumps(_profile_payload_for(profile_manager)).encode("utf-8")

    status, body = wsgi_request(
        app,
        "PUT",
        "/api/profile",
        body=body_bytes,
        content_type="text/plain",
    )

    assert "415" in status
    assert body == {"error": "unsupported_media_type"}
    assert profile_manager.get_profile().scenes == {"day_work": "WORK"}


def test_api_apply_profile_reports_failed_stage(tick_history, profile_manager):
    app = build_api_app(tick_history, profile_manager)
    invalid_runtime = _profile_payload(r"Z:\missing\wallpaper64.exe", playlist="NEW")

    status, body = wsgi_put(app, "/api/profile", invalid_runtime)

    assert "500" in status
    assert body == {
        "error": "profile_apply_failed",
        "stage": "compile",
        "detail": "wallpaper_engine_config_not_found",
    }


def test_api_server_binds_requested_port(app):
    requested_port = _find_free_port()
    server = APIServer(
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
