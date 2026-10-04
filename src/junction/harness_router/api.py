"""Dashboard / MCP JSON for the harness router.

Every handler does its file I/O (``routing.json``, the ledger, a ``PATH``
walk) off the event loop. Non-2xx bodies carry a machine-readable ``code``.
"""

from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from junction.harness_router.lanes import (
    LANE_ID_PATTERN,
    RoutingConfigError,
    is_routable_harness,
    save_lane_edit,
    save_settings_edit,
)
from junction.harness_router.service import check_harness, get_router

logger = logging.getLogger(__name__)


def _ids(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


async def api_status(request: web.Request) -> web.Response:
    """GET /api/routing/status — lanes, usage windows, cooldowns, per-kind picks."""
    payload = await asyncio.to_thread(get_router().status)
    return web.json_response(payload)


async def api_decide(request: web.Request) -> web.Response:
    """GET /api/routing/decide?kind=&role=&prefer=&exclude= — rank lanes for a kind."""
    query = request.rel_url.query
    router = get_router()
    decision = await asyncio.to_thread(
        router.decide,
        query.get("kind") or None,
        role=query.get("role") or None,
        prefer=_ids(query.get("prefer")),
        exclude=_ids(query.get("exclude")),
    )
    # "no lane" is an answer, not a request error: 200 with its own code.
    return web.json_response(decision.to_dict())


async def api_clear_cooldown(request: web.Request) -> web.Response:
    """POST /api/routing/cooldown/clear {lane?} — lift a lane's rest early."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    lane = str((body or {}).get("lane") or "").strip().lower() or None
    if lane is not None and not LANE_ID_PATTERN.match(lane):
        return web.json_response({"error": "invalid lane id", "code": "invalid_lane"}, status=400)
    cleared = await asyncio.to_thread(get_router().ledger.clear_cooldown, lane)
    logger.info("routing cooldown cleared: %s", ",".join(cleared) or "-")
    return web.json_response({"code": "ok", "cleared": cleared})


def _harness_param(request: web.Request) -> str | None:
    name = request.match_info.get("harness", "").strip().lower()
    return name if is_routable_harness(name) else None


async def api_harnesses(request: web.Request) -> web.Response:
    """GET /api/routing/harnesses — connectable harnesses, probes, lanes, picks."""
    payload = await asyncio.to_thread(get_router().harnesses_view)
    return web.json_response(payload)


async def api_check_harness(request: web.Request) -> web.Response:
    """POST /api/routing/harnesses/{harness}/check — start it once and record the result."""
    harness = _harness_param(request)
    if harness is None:
        return web.json_response(
            {"error": "unknown harness", "code": "unknown_harness"}, status=404
        )
    result = await check_harness(harness, router=get_router())
    return web.json_response({"code": "ok", "harness": harness, "probe": result.to_dict()})


async def api_edit_lane(request: web.Request) -> web.Response:
    """PUT /api/routing/harnesses/{harness}/lane — change a lane in routing.json."""
    harness = _harness_param(request)
    if harness is None:
        return web.json_response(
            {"error": "unknown harness", "code": "unknown_harness"}, status=404
        )
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON", "code": "invalid_json"}, status=400)
    if not isinstance(body, dict) or not body:
        return web.json_response(
            {"error": "expected an object of lane fields", "code": "invalid_lane_edit"}, status=400
        )
    router = get_router()
    try:
        lane = await asyncio.to_thread(save_lane_edit, harness, body, home=router.home)
    except RoutingConfigError as exc:
        return web.json_response({"error": str(exc), "code": "invalid_lane_edit"}, status=400)
    logger.info("routing lane edited: %s (%s)", harness, ",".join(sorted(body)))
    return web.json_response({"code": "ok", "lane": lane})


async def api_edit_settings(request: web.Request) -> web.Response:
    """PUT /api/routing/settings — change routing.json switches (``route_tasks``)."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON", "code": "invalid_json"}, status=400)
    if not isinstance(body, dict):
        return web.json_response(
            {"error": "expected an object of settings", "code": "invalid_settings_edit"},
            status=400,
        )
    router = get_router()
    try:
        saved = await asyncio.to_thread(save_settings_edit, body, home=router.home)
    except RoutingConfigError as exc:
        return web.json_response({"error": str(exc), "code": "invalid_settings_edit"}, status=400)
    logger.info("routing settings edited: %s", ",".join(sorted(body)))
    return web.json_response({"code": "ok", "settings": saved})


def register(app: web.Application) -> None:
    app.router.add_get("/api/routing/status", api_status)
    app.router.add_get("/api/routing/decide", api_decide)
    app.router.add_post("/api/routing/cooldown/clear", api_clear_cooldown)
    app.router.add_get("/api/routing/harnesses", api_harnesses)
    app.router.add_post("/api/routing/harnesses/{harness}/check", api_check_harness)
    app.router.add_put("/api/routing/harnesses/{harness}/lane", api_edit_lane)
    app.router.add_put("/api/routing/settings", api_edit_settings)
