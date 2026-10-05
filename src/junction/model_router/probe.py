"""Loopback health probe for the model catalog.

``junction up`` binds the catalog on ``127.0.0.1`` (default 4202). This
probe also asks the translation port (default 4200), which Junction does
not start. Port environment variables match the catalog this snapshot
came from. The probe never leaves loopback and never forwards an
arbitrary health JSON blob — credentials have shown up in adjacent
documents, and a status line is not a dump.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping

from junction.loopback_http import loopback_urlopen

logger = logging.getLogger(__name__)

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_ROUTER_PORT = 4202
DEFAULT_GATEWAY_PORT = 4200
HEALTH_PATH = "/health"
GATEWAY_HEALTH_PATH = "/health/liveliness"
PROBE_TIMEOUT_SECS = 2.0

# Codex Router's paths.mjs: MODEL_ROUTER_PORT, then CODEX_ROUTER_PORT, then 4202.
_ROUTER_PORT_ENV = ("MODEL_ROUTER_PORT", "CODEX_ROUTER_PORT")
_GATEWAY_PORT_ENV = ("MODEL_ROUTER_GATEWAY_PORT", "CODEX_ROUTER_GATEWAY_PORT")

# Health JSON keys that cannot reasonably be secrets and are useful in status.
_HEALTH_ALLOWLIST = frozenset({"ok", "status", "version", "service", "name"})
_MAX_HEALTH_STRING = 64

CODE_UNREACHABLE = "model_router_unreachable"
CODE_GATEWAY_UNREACHABLE = "model_router_gateway_unreachable"
CODE_INVALID_PORT = "model_router_invalid_port"
CODE_REFUSED_NON_LOOPBACK = "model_router_refused_non_loopback"
CODE_OK = "ok"


@dataclass(frozen=True, slots=True)
class EndpointStatus:
    """One loopback health URL."""

    url: str
    ok: bool
    code: str
    detail: str = ""
    health: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RouterStatus:
    """Catalog reachability. ``reachable`` is the catalog plane, not the translation port."""

    reachable: bool
    degraded: bool
    router: EndpointStatus
    gateway: EndpointStatus

    def to_dict(self) -> dict[str, Any]:
        plane = self.plane_status
        return {
            "status": plane,
            "reachable": self.reachable,
            "degraded": self.degraded,
            "code": CODE_OK if plane == "healthy" else self.router.code,
            "router": {
                "url": self.router.url,
                "ok": self.router.ok,
                "code": self.router.code,
                "detail": self.router.detail,
                "health": dict(self.router.health),
            },
            "gateway": {
                "url": self.gateway.url,
                "ok": self.gateway.ok,
                "code": self.gateway.code,
                "detail": self.gateway.detail,
                "health": dict(self.gateway.health),
            },
        }

    @property
    def plane_status(self) -> str:
        if self.router.ok and self.gateway.ok:
            return "healthy"
        if self.router.ok or self.gateway.ok:
            return "degraded"
        return "unreachable"


def resolve_router_port(explicit: int | None = None, env: Mapping[str, str] | None = None) -> int:
    return _resolve_port(explicit, _ROUTER_PORT_ENV, DEFAULT_ROUTER_PORT, env)


def resolve_gateway_port(explicit: int | None = None, env: Mapping[str, str] | None = None) -> int:
    return _resolve_port(explicit, _GATEWAY_PORT_ENV, DEFAULT_GATEWAY_PORT, env)


def _resolve_port(
    explicit: int | None,
    names: tuple[str, ...],
    default: int,
    env: Mapping[str, str] | None,
) -> int:
    if explicit is not None:
        if not _valid_port(explicit):
            raise ValueError(CODE_INVALID_PORT)
        return explicit
    environ = os.environ if env is None else env
    for name in names:
        raw = environ.get(name, "").strip()
        if not raw:
            continue
        try:
            value = int(raw)
        except ValueError:
            logger.warning("ignoring non-integer %s", name)
            continue
        if not _valid_port(value):
            logger.warning("ignoring out-of-range %s", name)
            continue
        return value
    return default


def _valid_port(value: int) -> bool:
    return 1 <= value <= 65535


def probe_status(
    *,
    router_port: int | None = None,
    gateway_port: int | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = PROBE_TIMEOUT_SECS,
) -> RouterStatus:
    """Probe loopback health URLs. Never raises for an unreachable sidecar."""
    try:
        r_port = resolve_router_port(router_port, env)
        g_port = resolve_gateway_port(gateway_port, env)
    except ValueError:
        bad = EndpointStatus(
            url="",
            ok=False,
            code=CODE_INVALID_PORT,
            detail="port must be an integer 1..65535",
        )
        return RouterStatus(reachable=False, degraded=True, router=bad, gateway=bad)

    router = _probe_url(f"http://{LOOPBACK_HOST}:{r_port}{HEALTH_PATH}", timeout, CODE_UNREACHABLE)
    gateway = _probe_url(
        f"http://{LOOPBACK_HOST}:{g_port}{GATEWAY_HEALTH_PATH}",
        timeout,
        CODE_GATEWAY_UNREACHABLE,
    )
    reachable = router.ok
    return RouterStatus(
        reachable=reachable,
        degraded=not (router.ok and gateway.ok),
        router=router,
        gateway=gateway,
    )


def _probe_url(url: str, timeout: float, unreachable_code: str) -> EndpointStatus:
    req = urllib.request.Request(url, method="GET")
    try:
        with loopback_urlopen(req, timeout=timeout) as resp:
            raw = resp.read(4096)
            http_ok = 200 <= getattr(resp, "status", 200) < 300
    except urllib.error.HTTPError as exc:
        logger.info("model-router probe HTTP %s", exc.code)
        return EndpointStatus(url=url, ok=False, code=unreachable_code, detail=f"HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # Do not interpolate exc: some OSError strings embed paths.
        logger.info("model-router probe unreachable")
        return EndpointStatus(
            url=url,
            ok=False,
            code=unreachable_code,
            detail=type(exc).__name__,
        )
    health = _sanitize_health(raw)
    ok = http_ok and _health_reports_ok(health)
    return EndpointStatus(
        url=url,
        ok=ok,
        code=CODE_OK if ok else unreachable_code,
        detail="" if ok else "health not ok",
        health=health,
    )


def _sanitize_health(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if key not in _HEALTH_ALLOWLIST:
            continue
        if isinstance(value, bool) or isinstance(value, int) and not isinstance(value, bool):
            cleaned[key] = value
        elif isinstance(value, str) and len(value) <= _MAX_HEALTH_STRING:
            cleaned[key] = value
    return cleaned


def _health_reports_ok(health: Mapping[str, Any]) -> bool:
    if not health:
        # Empty body with HTTP 2xx still means something answered on the port.
        return True
    if "ok" in health:
        return bool(health["ok"])
    status = health.get("status")
    if isinstance(status, str):
        return status.lower() in {"ok", "up", "healthy", "ready"}
    return True
