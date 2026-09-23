from __future__ import annotations

import logging
import threading
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

import bottle

logger = logging.getLogger("WEScheduler.API")


class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class APIServer:
    """Host a prepared Bottle app on the loopback interface."""

    def __init__(
        self,
        app: bottle.Bottle,
        requested_port: int = 0,
    ):
        self._app = app
        self._requested_port = requested_port
        self._httpd: _ThreadingWSGIServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int = 0

    def start(self) -> None:
        try:
            self._httpd = make_server(
                "127.0.0.1",
                self._requested_port,
                self._app,
                server_class=_ThreadingWSGIServer,
            )
        except OSError as exc:
            if self._requested_port > 0:
                raise OSError(f"Failed to bind local API server to 127.0.0.1:{self._requested_port}") from exc
            raise

        self.port = self._httpd.server_address[1]

        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        logger.info("Local HTTP server (bottle) on http://127.0.0.1:%d", self.port)

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None
        self._thread = None
