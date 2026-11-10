"""Dashboard JSON for the loopback model catalog."""

from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from warding.model_router.probe import probe_status
from warding.model_router.routing import annotated_catalog, build_plan, load_role_pins

logger = logging.getLogger(__name__)


async def api_status(request: web.Request) -> web.Response:
    """GET /api/model-router/status — sidecar health. Always loopback."""
    status = await asyncio.to_thread(probe_status)
    payload = status.to_dict()
    # Unreachable sidecar is degraded, not a request error. 200 lets the UI
    # render "optional plane down" without treating it as an API failure.
    logger.info("model-router status reachable=%s", status.reachable)
    return web.json_response(payload)


async def api_catalog(request: web.Request) -> web.Response:
    """GET /api/model-router/catalog — namespaced model choices. No secrets."""
    return web.json_response(annotated_catalog())


async def api_plan(request: web.Request) -> web.Response:
    """GET /api/model-router/plan — role DAG + token-efficient picks."""
    advertised = request.rel_url.query.get("advertised", "").split(",")
    pins = await asyncio.to_thread(load_role_pins)
    plan = build_plan(pins=pins, advertised=advertised)
    payload = plan.to_dict()
    payload["sidecar"] = (await asyncio.to_thread(probe_status)).to_dict()
    return web.json_response(payload)
