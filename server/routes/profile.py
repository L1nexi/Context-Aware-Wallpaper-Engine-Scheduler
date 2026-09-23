from __future__ import annotations

import json
import logging

import bottle
from pydantic import ValidationError

from configurations.profile import Profile
from configurations.profile_store import ProfileStoreError
from core.runtime.profile_manager import (
    ProfileAlreadyExists,
    ProfileApplyFailed,
    ProfileApplyTimeout,
    ProfileApplyUnavailable,
    ProfileManager,
)
from integrations.openweather import WeatherRejected, WeatherUnavailable, validate_weather_connection

logger = logging.getLogger("WEScheduler.API")
PROFILE_APPLY_TIMEOUT_SECONDS = 2.0


def _read_json_object() -> dict[str, object]:
    payload = json.loads(bottle.request.body.read())
    if not isinstance(payload, dict):
        raise TypeError("request body must be a JSON object")
    return payload


def _request_validation_issues(exc: ValidationError | ValueError | TypeError) -> list[dict[str, object]]:
    if isinstance(exc, ValidationError):
        return [{"path": list(issue["loc"]), "code": issue["type"], "message": issue["msg"]} for issue in exc.errors()]
    return [{"path": [], "code": "json_type", "message": str(exc)}]


def _weather_rejection_response(exc: WeatherRejected) -> dict[str, object]:
    bottle.response.status = 422
    return {
        "error": "weather_validation_failed",
        "issues": [
            {
                "path": list(exc.path),
                "code": exc.code,
                "message": exc.code,
            }
        ],
    }


def register_profile_routes(app: bottle.Bottle, profile_manager: ProfileManager) -> None:
    @app.route("/api/profile")
    def api_profile():
        bottle.response.content_type = "application/json; charset=utf-8"
        profile = profile_manager.get_profile()
        if profile is None:
            bottle.response.status = 404
            return {"error": "profile_not_found"}
        return {"profile": profile.model_dump(mode="json")}

    @app.post("/api/profile")
    def api_create_profile():
        bottle.response.content_type = "application/json; charset=utf-8"
        if bottle.request.content_type != "application/json":
            bottle.response.status = 415
            return {"error": "unsupported_media_type"}

        try:
            draft = Profile.model_validate(_read_json_object())
        except (ValidationError, ValueError, TypeError) as exc:
            bottle.response.status = 400 if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError)) else 422
            return {
                "error": "invalid_profile",
                "issues": _request_validation_issues(exc),
            }

        try:
            if profile_manager.has_committed_profile():
                raise ProfileAlreadyExists("profile is already committed")
            location = draft.weather.location
            validate_weather_connection(draft.weather.api_key, location.latitude, location.longitude)
            committed = profile_manager.create_initial_profile(draft)
        except ProfileAlreadyExists:
            bottle.response.status = 409
            return {"error": "profile_already_exists"}
        except WeatherRejected as exc:
            return _weather_rejection_response(exc)
        except WeatherUnavailable:
            bottle.response.status = 503
            return {"error": "weather_validation_unavailable"}
        except ProfileApplyFailed as exc:
            logger.exception("Initial Profile creation failed during %s", exc.stage)
            bottle.response.status = 500
            return {
                "error": "profile_create_failed",
                "stage": exc.stage,
                "detail": str(exc),
            }
        except ProfileStoreError as exc:
            logger.exception("Initial Profile creation failed")
            bottle.response.status = 500
            return {"error": "profile_create_failed", "detail": str(exc)}

        bottle.response.status = 201
        return {
            "status": "created",
            "profile": committed.model_dump(mode="json"),
        }

    @app.put("/api/profile")
    def api_apply_profile():
        bottle.response.content_type = "application/json; charset=utf-8"
        if bottle.request.content_type != "application/json":
            bottle.response.status = 415
            return {"error": "unsupported_media_type"}

        try:
            draft = Profile.model_validate(_read_json_object())
        except (ValidationError, ValueError, TypeError) as exc:
            bottle.response.status = 400 if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError)) else 422
            return {
                "error": "invalid_profile",
                "issues": _request_validation_issues(exc),
            }

        committed_profile = profile_manager.get_profile()
        if committed_profile is None:
            bottle.response.status = 404
            return {"error": "profile_not_found"}

        if committed_profile.weather != draft.weather:
            try:
                location = draft.weather.location
                validate_weather_connection(draft.weather.api_key, location.latitude, location.longitude)
            except WeatherRejected as exc:
                return _weather_rejection_response(exc)
            except WeatherUnavailable:
                bottle.response.status = 503
                return {"error": "weather_validation_unavailable"}

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
        return {
            "status": "applied",
            "profile": committed.model_dump(mode="json"),
        }
