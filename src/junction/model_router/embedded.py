"""Loopback model-catalog listener owned by Junction.

``junction up`` binds ``127.0.0.1`` and serves health plus the shipped
catalog. It does not forward provider traffic and does not start a
translation gateway. If the port is already taken, the existing listener
keeps it.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping

from junction import platform_compat
from junction.model_router.catalog import load_catalog
from junction.model_router.probe import HEALTH_PATH, LOOPBACK_HOST, resolve_router_port

logger = logging.getLogger(__name__)

SERVICE_NAME = "junction"
CATALOG_PATH = "/catalog"
CODE_NOT_FOUND = "model_router_not_found"
CODE_NO_FORWARD = "model_router_no_forward"
_MAX_BODY = 65536

_lock = threading.Lock()
_server: ThreadingHTTPServer | None = None


class _CatalogServer(ThreadingHTTPServer):
    """The catalog listener, bound so a busy port stays with its owner.

    ``HTTPServer`` turns on ``SO_REUSEADDR``. On POSIX that only lets a restart
    rebind a port still in ``TIME_WAIT``, but on Windows it lets a second socket
    bind a port another process is actively listening on, so the router would
    take over the port instead of leaving it alone. Windows binds with
    ``SO_EXCLUSIVEADDRUSE`` instead, which refuses the bind while the port is
    held and keeps a later process from taking this one.
    """

    allow_reuse_address = not platform_compat.IS_WINDOWS

    def server_bind(self) -> None:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if platform_compat.IS_WINDOWS and exclusive is not None:
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        super().server_bind()


@dataclass(frozen=True, slots=True)
class EmbeddedBind:
    """Result of trying to own the model-plane port."""

    host: str
    port: int
    owned: bool


class _Handler(BaseHTTPRequestHandler):
    """Health and catalog only. Completion routes are refused."""

    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == HEALTH_PATH:
            self._json(200, {"ok": True, "status": "ok", "service": SERVICE_NAME})
            return
        if path == CATALOG_PATH:
            self._json(200, load_catalog().to_dict())
            return
        self._json(404, {"ok": False, "code": CODE_NOT_FOUND})

    def do_POST(self) -> None:  # noqa: N802
        self._discard_body()
        self._json(501, {"ok": False, "code": CODE_NO_FORWARD})

    def do_PUT(self) -> None:  # noqa: N802
        self.do_POST()

    def do_PATCH(self) -> None:  # noqa: N802
        self.do_POST()

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _discard_body(self) -> None:
        raw = self.headers.get("Content-Length", "")
        try:
            length = int(raw)
        except ValueError:
            return
        if length > 0:
            self.rfile.read(min(length, _MAX_BODY))

    def _json(self, status: int, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def ensure_embedded_router(
    *,
    port: int | None = None,
    env: Mapping[str, str] | None = None,
) -> EmbeddedBind:
    """Bind the catalog listener, or leave a busy port to its owner.

    ``port=0`` asks the kernel for an ephemeral port (tests). Never raises.
    """
    global _server
    with _lock:
        if _server is not None:
            bound = int(_server.server_address[1])
            return EmbeddedBind(LOOPBACK_HOST, bound, True)
        if port == 0:
            resolved = 0
        else:
            try:
                resolved = resolve_router_port(port, env)
            except ValueError:
                logger.info("model plane skipped: invalid port")
                return EmbeddedBind(LOOPBACK_HOST, 0, False)
        try:
            server = _CatalogServer((LOOPBACK_HOST, resolved), _Handler)
        except OSError:
            logger.info("model plane port busy; leaving the existing listener")
            return EmbeddedBind(LOOPBACK_HOST, resolved, False)
        server.daemon_threads = True
        thread = threading.Thread(
            target=server.serve_forever,
            name="junction-model-plane",
            daemon=True,
        )
        thread.start()
        _server = server
        return EmbeddedBind(LOOPBACK_HOST, int(server.server_address[1]), True)


def stop_embedded_router() -> None:
    """Stop the listener this process started. Safe when none is running."""
    global _server
    with _lock:
        server = _server
        _server = None
    if server is None:
        return
    server.shutdown()
    server.server_close()
