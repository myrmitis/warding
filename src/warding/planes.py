"""Compose harness + model plane status into one Warding snapshot.

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

from warding.acp.runtimes import (
    AUTO_PREFERENCE,
    RuntimeNotFoundError,
    builtin_specs,
    runtime_available,
    select_runtime,
)
from warding.acp.types import ACP_BACKEND_AUTO, ACP_BACKEND_KIRO
from warding.constants import CLI_BIN, PRODUCT_NAME
from warding.model_router.probe import probe_status
from warding.model_router.routing import (
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


def configured_backend() -> str:
    """``agent.acp_backend`` as persisted; ``auto`` when the config cannot be read.

    Read fresh on every call: the gateway adopts a changed value for its next
    new session, so a snapshot that reused a boot-time copy would describe a
    harness chat no longer runs.
    """
    # Deferred: warding.config.loader imports most of the package, and this
    # module is imported by the CLI before the compose banner prints.
    from warding.config import WardingConfig

    try:
        return WardingConfig.load().agent.acp_backend
    except Exception:
        logger.debug("planes: config unreadable; reporting auto", exc_info=True)
        return ACP_BACKEND_AUTO


def harness_snapshot(
    *,
    configured: str | None = None,
    which: Any = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """The harness a NEW session runs, by the provider factory's own rule.

    ``configured`` is ``agent.acp_backend`` (read from config when omitted).
    ``auto`` resolves to the first installed runtime, ``""`` when none is. An
    explicit harness is selected as configured whether or not it is installed,
    because that is what the factory spawns; ``selected_available`` says which,
    so a missing harness is reported instead of being replaced by whatever
    ``auto`` would have picked. ``None`` there means this host cannot tell (a
    harness outside the auto registry, such as KAS).
    """
    if configured is None:
        configured = configured_backend()
    inventory = harness_inventory(which=which, env=env)
    if configured == ACP_BACKEND_AUTO:
        try:
            spec = select_runtime(ACP_BACKEND_AUTO, which=which, env=env)
            selected = runtime_label(spec.id)
        except RuntimeNotFoundError:
            selected = ""
    else:
        selected = runtime_label(configured)
    available: bool | None = False
    if selected:
        available = next((row["available"] for row in inventory if row["id"] == selected), None)
    return {
        "default": ACP_BACKEND_AUTO,
        "configured": runtime_label(configured),
        "selected": selected,
        "selected_available": available,
        "runtimes": inventory,
    }


def snapshot_planes(
    *,
    which: Any = None,
    env: Mapping[str, str] | None = None,
    router_port: int | None = None,
    gateway_port: int | None = None,
    configured: str | None = None,
) -> dict[str, Any]:
    """Harness inventory + model-plane health + role DAG. Never crashes the gateway."""
    harness = harness_snapshot(configured=configured, which=which, env=env)
    model = probe_status(router_port=router_port, gateway_port=gateway_port)
    # Empty pins: this snapshot is compose, not apply. ``warding router plan``
    # is the pin-aware view. Inventory already marks the Kiro harness optional,
    # so this payload does not carry a dedicated vendor-cli key.
    plan = build_plan(pins=None, advertised=None)
    return {
        "product": PRODUCT_NAME,
        "cli": CLI_BIN,
        "harness": harness,
        "model": model.to_dict(),
        "roles": plan.to_dict(),
        "gateway": {"status": "ok", "code": CODE_OK},
        "code": CODE_OK,
    }


def format_human_planes(snap: Mapping[str, Any], *, heading: str) -> str:
    """One human screen for planes, doctor, and ``warding up``.

    Shared so the three surfaces cannot drift: configured harness + selected,
    model-plane health, role DAG, docked runtimes, and the no-keys rule.
    """
    harness = snap["harness"]
    model = snap["model"]
    lines = [
        heading,
        format_harness_line(harness),
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


def format_harness_line(harness: Mapping[str, Any]) -> str:
    """``  harness: <configured> (selected=<what a new session runs>; ...)``.

    Also printed by ``config set agent.acp_backend``, so the confirmation and
    the planes screen say the same thing about the same setting.
    """
    configured = harness.get("configured") or harness["default"]
    selected = harness.get("selected") or "none installed"
    if harness.get("selected") and harness.get("selected_available") is False:
        selected = f"{selected}, not installed"
    return f"  harness: {configured} (selected={selected}; vendor CLI optional)"


def _model_line(model: Mapping[str, Any]) -> str:
    """One status line. The built-in catalog is up when its health names us."""
    health: Mapping[str, Any] = {}
    router = model.get("router")
    if isinstance(router, Mapping):
        raw = router.get("health")
        if isinstance(raw, Mapping):
            health = raw
    if health.get("service") == "warding" and model.get("status") != "healthy":
        return "  model:   built-in catalog (provider translation is not bundled)"
    status = model.get("status")
    if status == "healthy":
        return "  model:   healthy"
    if status == "unreachable":
        return f"  model:   down (starts with {CLI_BIN} up; gateway still works)"
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
    """``warding planes`` — one screen for both planes.

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
        "planes snapshot harness_configured=%s harness_selected=%s model=%s",
        payload["harness"]["configured"],
        payload["harness"]["selected"],
        payload["model"]["status"],
    )
    return web.json_response(payload)
