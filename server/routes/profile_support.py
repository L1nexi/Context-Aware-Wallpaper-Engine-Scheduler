from __future__ import annotations

import json
import logging

import bottle
from pydantic import BaseModel, ConfigDict, ValidationError

from core.models.scene import SceneId
from core.runtime.we_config import WEConfigProber, WEConfigReadError
from core.runtime.we_path import resolve_wallpaper_engine_path
from integrations.ip_location import LocationDetectionUnavailable, detect_city_location

logger = logging.getLogger("WEScheduler.API")


class PlaylistScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wallpaper_engine_path: str = ""


def register_profile_support_routes(app: bottle.Bottle) -> None:
    @app.route("/api/scenes")
    def api_setup_scenes():
        bottle.response.content_type = "application/json; charset=utf-8"
        return {"scenes": [{"id": scene_id.value} for scene_id in SceneId]}

    @app.post("/api/location-estimates")
    def api_detect_setup_location():
        bottle.response.content_type = "application/json; charset=utf-8"
        logger.debug("Location estimate started")
        try:
            location = detect_city_location()
        except LocationDetectionUnavailable as exc:
            logger.warning("Location estimate unavailable: reason=%s http_status=%s", exc.reason, exc.http_status)
            bottle.response.status = 503
            payload: dict[str, object] = {"error": "location_detection_unavailable", "reason": exc.reason}
            if exc.http_status is not None:
                payload["http_status"] = exc.http_status
            return payload
        logger.debug("Location estimate succeeded")
        bottle.response.status = 201
        return {
            "location": {
                "name": location.name,
                "latitude": location.latitude,
                "longitude": location.longitude,
            }
        }

    @app.post("/api/wallpaper-engine/playlist-scans")
    def api_scan_wallpaper_engine_playlists():
        bottle.response.content_type = "application/json; charset=utf-8"
        if bottle.request.content_type != "application/json":
            bottle.response.status = 415
            return {"error": "unsupported_media_type"}

        try:
            payload = json.loads(bottle.request.body.read())
            if not isinstance(payload, dict):
                raise TypeError("request body must be a JSON object")
            scan_request = PlaylistScanRequest.model_validate(payload)
        except (ValidationError, ValueError, TypeError) as exc:
            bottle.response.status = 400 if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError)) else 422
            if isinstance(exc, ValidationError):
                issues = [{"path": list(issue["loc"]), "code": issue["type"], "message": issue["msg"]} for issue in exc.errors()]
            else:
                issues = [{"path": [], "code": "json_type", "message": str(exc)}]
            return {
                "error": "invalid_wallpaper_engine_request",
                "issues": issues,
            }

        executable = resolve_wallpaper_engine_path(scan_request.wallpaper_engine_path)
        if executable is None:
            bottle.response.status = 404
            return {"error": "wallpaper_engine_executable_not_found"}

        try:
            prober = WEConfigProber(executable)
            playlist_names = list(dict.fromkeys(prober.scan_playlist_names()))
            item_counts = prober.probe_item_counts()
        except WEConfigReadError as exc:
            bottle.response.status = 422
            return {"error": exc.code}

        bottle.response.status = 201
        return {
            "wallpaper_engine_path": executable,
            "playlists": [{"name": name, "item_count": item_counts.get(name, 0)} for name in playlist_names],
        }
