"""``junction router`` — catalog status, model list, and role plan."""

from __future__ import annotations

import argparse
import json
import sys

from junction.model_router.probe import RouterStatus, probe_status
from junction.model_router.routing import annotated_catalog, build_plan


def run_router_command(args: argparse.Namespace) -> None:
    action = getattr(args, "router_action", None) or "status"
    if action == "status":
        status = probe_status(router_port=getattr(args, "router_port", None))
        _print_status(status)
        return
    if action == "catalog":
        _print_catalog(
            provider=getattr(args, "provider", "") or "",
            cost_class=getattr(args, "cost_class", "") or "",
        )
        return
    if action == "plan":
        _print_plan(getattr(args, "advertised", "") or "")
        return
    print(f"unknown router action: {action}", file=sys.stderr)
    raise SystemExit(2)


def _print_status(status: RouterStatus) -> None:
    plane = status.plane_status
    note = ""
    if plane != "healthy":
        note = " (gateway still works)"
    print(f"model plane: {plane}{note}")
    print(f"  router:  {status.router.url}  {status.router.code}")
    print(f"  gateway: {status.gateway.url}  {status.gateway.code}")
    print("never paste provider keys into chat.")
    print(json.dumps(status.to_dict(), separators=(",", ":")))


def _print_catalog(*, provider: str, cost_class: str) -> None:
    if cost_class and cost_class not in {"economy", "standard", "capable"}:
        print(f"unknown cost class: {cost_class}", file=sys.stderr)
        raise SystemExit(2)
    payload = annotated_catalog()
    models = list(payload["models"])
    if provider:
        models = [row for row in models if row.get("provider") == provider]
    if cost_class:
        models = [row for row in models if row.get("cost_class") == cost_class]
    payload["models"] = models
    payload["model_count"] = len(models)
    print(
        f"model-router catalog: {payload['provider_count']} providers, "
        f"{len(models)} models (no credentials in this snapshot)"
    )
    print(json.dumps(payload, separators=(",", ":")))


def _print_plan(advertised_raw: str) -> None:
    advertised = [part.strip() for part in advertised_raw.split(",") if part.strip()]
    pins: dict[str, str] = {}
    try:
        from junction.config.loader import JunctionConfig

        pins = dict(JunctionConfig.load().agent.role_models)
    except Exception:
        pins = {}
    plan = build_plan(pins=pins, advertised=advertised)
    print("model-router plan: orchestration → planning → execution → subagent")
    for row in plan.roles:
        print(
            f"  {row.role}: class={row.cost_class} wire={row.wire_id} "
            f"suggest={row.suggestion or '-'} ({row.reason})"
        )
    print("never paste provider keys into chat.")
    print(json.dumps(plan.to_dict(), separators=(",", ":")))
