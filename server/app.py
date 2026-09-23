from __future__ import annotations

import json

import bottle

from core.runtime.profile_manager import ProfileManager
from core.state.tick_history import TickHistoryStore
from server.routes.profile import register_profile_routes
from server.routes.profile_support import register_profile_support_routes
from server.spa import register_spa_routes
from ui.tick_history import build_tick_window_response


def build_api_app(
    tick_history: TickHistoryStore,
    profile_manager: ProfileManager,
) -> bottle.Bottle:
    app = bottle.Bottle()

    @app.route("/api/tick-history")
    def api_tick_history_window():
        try:
            count = int(bottle.request.query.get("limit", "900"))
        except ValueError:
            count = 0
        if count <= 0:
            bottle.response.status = 422
            bottle.response.content_type = "application/json; charset=utf-8"
            return json.dumps({"error": "invalid_count"})

        window = tick_history.read_window(count)
        payload = build_tick_window_response(window)
        bottle.response.content_type = "application/json; charset=utf-8"
        return json.dumps(payload)

    @app.route("/api/health")
    def api_health():
        bottle.response.content_type = "application/json; charset=utf-8"
        return {"ok": True}

    register_profile_routes(app, profile_manager)
    register_profile_support_routes(app)

    @app.route("/api/<path:path>", method=("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"))
    def api_not_found(path: str):
        bottle.response.status = 404
        bottle.response.content_type = "application/json; charset=utf-8"
        return {"error": "not_found"}

    register_spa_routes(app)
    return app
