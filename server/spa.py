from __future__ import annotations

import os
import sys

import bottle

from app.context import get_app_root


def _serve_spa(static_root: str, path: str) -> bottle.HTTPResponse:
    """Serve one SPA asset or its index fallback.

    Raises:
        bottle.HTTPError: If the requested path escapes the static root.
    """

    file_path = os.path.normpath(os.path.join(static_root, path.lstrip("/")))
    try:
        common_path = os.path.commonpath((static_root, file_path))
    except ValueError:
        common_path = ""
    if common_path != os.path.normpath(static_root):
        bottle.abort(403, "Forbidden")

    if os.path.isfile(file_path):
        return bottle.static_file(path, root=static_root)

    return bottle.static_file("index.html", root=static_root)


def register_spa_routes(app: bottle.Bottle) -> None:
    app_root = sys._MEIPASS if getattr(sys, "frozen", False) else get_app_root()
    static_root = os.path.join(app_root, "frontend", "dist")

    @app.route("/setup")
    def redirect_setup() -> bottle.HTTPResponse:
        return bottle.redirect("/setup/")

    @app.route("/setup/")
    @app.route("/setup/<path:path>")
    def serve_setup_spa(path: str = "") -> bottle.HTTPResponse:
        return _serve_spa(static_root, path)

    @app.route("/")
    @app.route("/<path:path>")
    def serve_spa(path: str = "") -> bottle.HTTPResponse:
        return _serve_spa(static_root, path)
