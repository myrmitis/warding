"""The harness-routing tool: what the router would pick, and why.

``route_task`` is read-only. It asks the gateway (which owns the routing
ledger) to rank every lane for one task kind and returns the ranking with each
lane's remaining window and any cooldown. Dispatch itself is ``spawn_run``
with ``harness="route"`` (or a pinned lane), so this tool never starts work.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

from junction import mcp_core
from junction.harness_router.kinds import KIND_DESCRIPTIONS, TASK_KINDS
from junction.validation import ROUTE_TASK_SCHEMA, validate_tool_args


def schemas() -> list[dict[str, Any]]:
    return [
        {
            "name": "route_task",
            "description": (
                "Show which coding-agent harness (Claude Code, Codex, Cursor, Grok, "
                "OpenCode/OpenRouter, …) Warding's harness router would pick for a kind "
                "of work, with every lane ranked: affinity for the kind, remaining "
                "usage window, billing (subscription before metered), and lanes resting "
                "after a usage limit. Read-only. To dispatch, call spawn_run with "
                "harness='route' and the same kind (or harness='<lane>' to pin). Use it "
                "when splitting a plan so each step lands on the subscription best "
                "suited to it and quota is spread across plans."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": list(TASK_KINDS),
                        "description": "; ".join(
                            f"{k} = {v}" for k, v in KIND_DESCRIPTIONS.items()
                        ),
                    },
                    "prefer": {
                        "type": "string",
                        "description": (
                            "Optional lane id or harness name to favor slightly "
                            "(e.g. the harness that already holds related context)."
                        ),
                    },
                },
                "required": ["kind"],
            },
        }
    ]


def _fmt_rest(until: float) -> str:
    left = max(0, int(until - time.time()))
    hours, rem = divmod(left, 3600)
    return f"{hours}h{rem // 60:02d}m" if hours else f"{rem // 60}m"


def route_task(name: str, args: dict[str, Any]) -> str:
    args = validate_tool_args(args, ROUTE_TASK_SCHEMA)
    query = {"kind": args.get("kind") or ""}
    if args.get("prefer"):
        query["prefer"] = args["prefer"]
    d = mcp_core._get("/api/routing/decide?" + urlencode(query))
    if d.get("error"):
        return f"Error: {d['error']}"
    lines: list[str] = []
    if d.get("code") == "ok":
        lines.append(
            f"Pick for {d.get('kind')}: lane '{d.get('lane')}' "
            f"(harness {d.get('harness')}{', model ' + d['model'] if d.get('model') else ''})."
        )
        lines.append(f"Why: {d.get('reason')}")
    else:
        lines.append(f"No lane available for {d.get('kind')}: {d.get('reason')}")
    lines.append("")
    lines.append("Lanes (best first):")
    for row in d.get("candidates") or []:
        status = "ok"
        if row.get("excluded") == "cooldown":
            status = (
                f"resting {_fmt_rest(float(row.get('cooldown_until') or 0))} ({row.get('note')})"
            )
        elif row.get("excluded"):
            status = str(row.get("excluded"))
        lines.append(
            f"  {row.get('lane')} [{row.get('harness')}, {row.get('billing')}] "
            f"score {row.get('score')} affinity {row.get('affinity')} "
            f"window {row.get('window_used')}/{row.get('window_capacity')} — {status}"
        )
    if d.get("code") == "ok":
        lines.append("")
        lines.append(
            f"Dispatch: spawn_run(task=..., harness='route', kind='{d.get('kind')}') "
            f"or pin with harness='{d.get('lane')}'."
        )
    return "\n".join(lines)


HANDLERS: dict[str, Callable[[str, dict[str, Any]], str]] = {
    "route_task": route_task,
}
