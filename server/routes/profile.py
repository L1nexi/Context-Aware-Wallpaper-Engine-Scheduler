from __future__ import annotations

import json
import logging

import bottle
from pydantic import BaseModel, ConfigDict, Field, ValidationError

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
WEATHER_KEY_TEST_LATITUDE = 51.5072
WEATHER_KEY_TEST_LONGITUDE = -0.1276


class WeatherKeyValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    api_key: str = Field(min_length=1)


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


def _weather_unavailable_response(exc: WeatherUnavailable) -> dict[str, object]:
    bottle.response.status = 503
    payload: dict[str, object] = {"error": "weather_validation_unavailable", "reason": exc.reason}
    if exc.http_status is not None:
        payload["http_status"] = exc.http_status
    return payload


def register_profile_routes(app: bottle.Bottle, profile_manager: ProfileManager) -> None:
    @app.post("/api/weather-key-validations")
    def api_validate_weather_key():
        bottle.response.content_type = "application/json; charset=utf-8"
        if bottle.request.content_type != "application/json":
            bottle.response.status = 415
            return {"error": "unsupported_media_type"}
        try:
            request = WeatherKeyValidationRequest.model_validate(_read_json_object())
        except (ValidationError, ValueError, TypeError) as exc:
            bottle.response.status = 400 if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError)) else 422
            return {"error": "invalid_weather_key_request", "issues": _request_validation_issues(exc)}

        try:
            logger.debug("Weather key test started")
            validate_weather_connection(request.api_key, WEATHER_KEY_TEST_LATITUDE, WEATHER_KEY_TEST_LONGITUDE)
        except WeatherRejected as exc:
            logger.warning("Weather key test rejected: reason=%s", exc.code)
            return _weather_rejection_response(exc)
        except WeatherUnavailable as exc:
            logger.warning("Weather key test unavailable: reason=%s http_status=%s", exc.reason, exc.http_status)
            return _weather_unavailable_response(exc)

        logger.debug("Weather key test succeeded")
        return {"status": "valid"}

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
            logger.debug("Weather validation started: operation=create")
            validate_weather_connection(draft.weather.api_key, location.latitude, location.longitude)
            logger.debug("Weather validation succeeded: operation=create")
            committed = profile_manager.create_initial_profile(draft)
        except ProfileAlreadyExists:
            bottle.response.status = 409
            return {"error": "profile_already_exists"}
        except WeatherRejected as exc:
            logger.warning("Weather validation rejected: operation=create reason=%s", exc.code)
            return _weather_rejection_response(exc)
        except WeatherUnavailable as exc:
            logger.warning(
                "Weather validation unavailable: operation=create reason=%s http_status=%s",
                exc.reason,
                exc.http_status,
            )
            return _weather_unavailable_response(exc)
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

        weather_changed = committed_profile.weather != draft.weather
        logger.debug("Profile replace requested: weather_changed=%s", weather_changed)
        if weather_changed:
            try:
                location = draft.weather.location
                logger.debug("Weather validation started: operation=replace")
                validate_weather_connection(draft.weather.api_key, location.latitude, location.longitude)
                logger.debug("Weather validation succeeded: operation=replace")
            except WeatherRejected as exc:
                logger.warning("Weather validation rejected: operation=replace reason=%s", exc.code)
                return _weather_rejection_response(exc)
            except WeatherUnavailable as exc:
                logger.warning(
                    "Weather validation unavailable: operation=replace reason=%s http_status=%s",
                    exc.reason,
                    exc.http_status,
                )
                return _weather_unavailable_response(exc)

        try:
            committed = profile_manager.apply_profile(
                draft,
                timeout=PROFILE_APPLY_TIMEOUT_SECONDS,
            )
        except ProfileApplyTimeout:
            logger.warning("Profile apply timed out")
            bottle.response.status = 503
            return {"error": "profile_apply_timeout"}
        except ProfileApplyUnavailable:
            logger.warning("Profile apply unavailable")
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
