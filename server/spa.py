from __future__ import annotations

import os
import sys

import bottle

from app.context import get_app_root

STATIC_APP_DIR = "frontend"
STATIC_DIST_DIR = "dist"


def _resolve_static_root(app_dir: str) -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, app_dir, STATIC_DIST_DIR)
    return os.path.join(get_app_root(), app_dir, STATIC_DIST_DIR)


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
    static_root = _resolve_static_root(STATIC_APP_DIR)

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
