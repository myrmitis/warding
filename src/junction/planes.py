"""Compose harness + model plane status into one Junction snapshot.

The two planes already have owners (``acp.runtimes`` and ``model_router``).
This module does not spawn agents, probe non-loopback hosts, or change the
Kiro harness path. It is a read-only join so CLI, doctor, and the dashboard
share one payload: harness inventory, model-plane health, and the role DAG.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Mapping
from typing import Any, TextIO

from aiohttp import web

from junction.acp.runtimes import (
    AUTO_PREFERENCE,
    RuntimeNotFoundError,
    builtin_specs,
    runtime_available,
    select_runtime,
)
from junction.acp.types import ACP_BACKEND_AUTO, ACP_BACKEND_KIRO
from junction.constants import CLI_BIN, PRODUCT_NAME
from junction.model_router.probe import probe_status
from junction.model_router.routing import (
    ROLE_EXECUTION,
    ROLE_ORCHESTRATION,
    ROLE_PLANNING,
    build_plan,
)

_DAG_ROLES = (ROLE_ORCHESTRATION, ROLE_PLANNING, ROLE_EXECUTION)

logger = logging.getLogger(__name__)

CODE_OK = "ok"


def runtime_label(runtime_id: str) -> str:
    """Stable JSON id. The Kiro harness is spelled ``""`` on the wire (H7)."""
    if runtime_id == ACP_BACKEND_KIRO:
        return "kiro-cli"
    return runtime_id


def harness_inventory(
    *,
    which: Any = None,
    env: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Installed-or-not rows for every registry id, kiro-cli last and optional."""
    specs = builtin_specs(which=which, env=env)
    rows: list[dict[str, Any]] = []
    for runtime_id in AUTO_PREFERENCE:
        spec = specs[runtime_id]
        rows.append(
            {
                "id": runtime_label(spec.id),
                "available": runtime_available(spec, which=which, env=env),
                "protocol": spec.protocol,
                "optional": spec.id == ACP_BACKEND_KIRO,
            }
        )
    return rows


def snapshot_planes(
    *,
    which: Any = None,
    env: Mapping[str, str] | None = None,
    router_port: int | None = None,
    gateway_port: int | None = None,
) -> dict[str, Any]:
    """Harness inventory + model-plane health + role DAG. Never crashes the gateway."""
    inventory = harness_inventory(which=which, env=env)
    selected = ""
    try:
        spec = select_runtime(ACP_BACKEND_AUTO, which=which, env=env)
        selected = runtime_label(spec.id)
    except RuntimeNotFoundError:
        selected = ""
    model = probe_status(router_port=router_port, gateway_port=gateway_port)
    # Empty pins: this snapshot is compose, not apply. ``junction router plan``
    # is the pin-aware view. Inventory already marks the Kiro harness optional,
    # so this payload does not carry a dedicated vendor-cli key.
    plan = build_plan(pins=None, advertised=None)
    return {
        "product": PRODUCT_NAME,
        "cli": CLI_BIN,
        "harness": {
            "default": ACP_BACKEND_AUTO,
            "selected": selected,
            "runtimes": inventory,
        },
        "model": model.to_dict(),
        "roles": plan.to_dict(),
        "gateway": {"status": "ok", "code": CODE_OK},
        "code": CODE_OK,
    }


def format_human_planes(snap: Mapping[str, Any], *, heading: str) -> str:
    """One human screen for planes, doctor, and ``junction up``.

    Shared so the three surfaces cannot drift: harness default + selected,
    model-plane health, role DAG, docked runtimes, and the no-keys rule.
    """
    harness = snap["harness"]
    model = snap["model"]
    selected = harness.get("selected") or "none installed"
    lines = [
        heading,
        (f"  harness: {harness['default']} " f"(selected={selected}; vendor CLI optional)"),
        _model_line(model),
    ]
    role_bits = " ".join(
        f"{row['role']}={row['cost_class']}"
        for row in snap.get("roles", {}).get("roles", [])
        if row.get("role") in _DAG_ROLES
    )
    if role_bits:
        lines.append(f"  roles:   {role_bits}")
    available = [row["id"] for row in harness.get("runtimes", []) if row.get("available")]
    if available:
        lines.append(f"  docked:  {', '.join(available)}")
    lines.append("never paste provider keys into chat.")
    return "\n".join(lines)


def _model_line(model: Mapping[str, Any]) -> str:
    """One status line. The built-in catalog is up when its health names us."""
    health: Mapping[str, Any] = {}
    router = model.get("router")
    if isinstance(router, Mapping):
        raw = router.get("health")
        if isinstance(raw, Mapping):
            health = raw
    if health.get("service") == "junction" and model.get("status") != "healthy":
        return "  model:   built-in catalog (provider translation is not bundled)"
    status = model.get("status")
    if status == "healthy":
        return "  model:   healthy"
    if status == "unreachable":
        return "  model:   down (starts with junction up; gateway still works)"
    return "  model:   degraded (gateway still works)"


def print_compose_banner(*, stream: TextIO | None = None) -> None:
    """Foreground start floor: compose both planes before the server binds.

    Writes to stderr so ``--json-ready`` stdout stays a single READY line.
    A probe failure never blocks start.
    """
    if stream is None:
        stream = sys.stderr
    try:
        snap = snapshot_planes()
        print(format_human_planes(snap, heading=f"{PRODUCT_NAME} compose"), file=stream)
    except Exception:
        logger.debug("compose banner skipped", exc_info=True)


def run_planes_command(args: argparse.Namespace) -> None:
    """``junction planes`` — one screen for both planes.

    Human text is the default. ``--json`` is the machine form so scripts do not
    have to peel a dump off the last line of operator copy.
    """
    snap = snapshot_planes(router_port=getattr(args, "router_port", None))
    if getattr(args, "as_json", False):
        print(json.dumps(snap, separators=(",", ":")))
        return
    print(format_human_planes(snap, heading=f"{PRODUCT_NAME} planes"))


async def api_planes(request: web.Request) -> web.Response:
    """GET /api/planes — composed harness + model status. Always 200."""
    payload = await asyncio.to_thread(snapshot_planes)
    logger.info(
        "planes snapshot harness_selected=%s model=%s",
        payload["harness"]["selected"],
        payload["model"]["status"],
    )
    return web.json_response(payload)
