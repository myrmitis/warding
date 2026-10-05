"""Role DAG and token-efficient model selection.

Junction routes work through named roles. Each role has a cost class so
orchestration and background stay cheap, planning spends on capability, and
execution sits in the middle — maximizing useful work per token.

Pins in ``agent.role_models`` always win. Unpinned roles resolve to ``"auto"``
unless the caller supplies an advertised id set; then the pick is the first
advertised id in that role's cost class. Concrete model ids are never hardcoded
as defaults.

Cost class is inferred from slug tokens (``flash``, ``opus``, …), never from a
pinned flagship id. An empty advertised set means entitlement is unknown, so the
wire id stays ``"auto"`` (inherit the session default).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from junction.model_router.catalog import CatalogModel, load_catalog

logger = logging.getLogger(__name__)

# Task-class roles operators can pin. background/subagent already existed;
# orchestration/planning/execution are the DAG stages for a run.
ROLE_ORCHESTRATION = "orchestration"
ROLE_PLANNING = "planning"
ROLE_EXECUTION = "execution"
ROLE_BACKGROUND = "background"
ROLE_SUBAGENT = "subagent"

ROUTE_ROLE_KEYS: tuple[str, ...] = (
    ROLE_ORCHESTRATION,
    ROLE_PLANNING,
    ROLE_EXECUTION,
    ROLE_BACKGROUND,
    ROLE_SUBAGENT,
)

COST_ECONOMY = "economy"
COST_STANDARD = "standard"
COST_CAPABLE = "capable"
COST_CLASSES: tuple[str, ...] = (COST_ECONOMY, COST_STANDARD, COST_CAPABLE)

# Cheapest class that still does the job. Orchestration is control traffic;
# planning is rare and high-leverage; execution is the bulk of coding tokens.
ROLE_COST_CLASS: dict[str, str] = {
    ROLE_ORCHESTRATION: COST_ECONOMY,
    ROLE_PLANNING: COST_CAPABLE,
    ROLE_EXECUTION: COST_STANDARD,
    ROLE_BACKGROUND: COST_ECONOMY,
    ROLE_SUBAGENT: COST_STANDARD,
}

# Directed edges: orchestration fans into planning, planning into execution,
# execution may fan out to subagents. background is a side node (heartbeat),
# not on the run path.
ROLE_DAG_EDGES: tuple[tuple[str, str], ...] = (
    (ROLE_ORCHESTRATION, ROLE_PLANNING),
    (ROLE_PLANNING, ROLE_EXECUTION),
    (ROLE_EXECUTION, ROLE_SUBAGENT),
)

# Token sets on the leaf (after the last ``/``). ``mini`` is omitted because it
# false-hits MiniMax. ``pro`` is a whole token so ``contributor`` stays standard.
# ``turbo`` is economy only when the slug is not already a capable family
# (``glm-5-turbo`` is capable; ``llama-3-turbo`` is economy).
_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")
_CHEAP_SIZE_TOKENS = frozenset({"flash", "haiku", "highspeed", "free", "tiny", "lite", "nano"})
_ECONOMY_TURBO = "turbo"
_CAPABLE_TOKENS = frozenset({"opus", "pro", "max", "ultra", "fable", "k3", "sol", "terra"})
_CAPABLE_LEAVES = frozenset({"grok-4.5", "grok-4.6", "kimi-k3", "k3"})
_CAPABLE_FAMILIES = ("gpt-5", "glm-5", "grok-4", "kimi-k3", "claude-opus")
_CLASS_RANK = {COST_ECONOMY: 0, COST_STANDARD: 1, COST_CAPABLE: 2}

DEFAULT_MODEL = "auto"


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    """One role's pin, cost class, wire id, and catalog suggestion."""

    role: str
    cost_class: str
    pin: str
    wire_id: str
    suggestion: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "cost_class": self.cost_class,
            "pin": self.pin,
            "wire_id": self.wire_id,
            "suggestion": self.suggestion,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class RoutingPlan:
    """Full DAG with per-role assignments."""

    roles: tuple[RoleAssignment, ...]
    edges: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "roles": [row.to_dict() for row in self.roles],
            "dag": [{"from": src, "to": dst} for src, dst in self.edges],
            "code": "ok",
        }

    def assignment(self, role: str) -> RoleAssignment | None:
        for row in self.roles:
            if row.role == role:
                return row
        return None


def classify_cost(model_id: str) -> str:
    """Map a slug or advertised id onto a cost class. Default is standard."""
    raw = (model_id or "").strip().lower()
    if not raw:
        return COST_STANDARD
    leaf = raw.rsplit("/", 1)[-1]
    tokens = {tok for tok in _TOKEN_SPLIT.split(leaf) if tok}
    if tokens & _CHEAP_SIZE_TOKENS or leaf.endswith("-free") or leaf.endswith(":free"):
        return COST_ECONOMY
    if leaf in _CAPABLE_LEAVES or raw in _CAPABLE_LEAVES or _family_is_capable(raw, leaf):
        return COST_CAPABLE
    if tokens & _CAPABLE_TOKENS:
        return COST_CAPABLE
    if _ECONOMY_TURBO in tokens:
        return COST_ECONOMY
    return COST_STANDARD


def _family_is_capable(raw: str, leaf: str) -> bool:
    for family in _CAPABLE_FAMILIES:
        if leaf.startswith(family) or raw.startswith(family):
            return True
    return False


def annotated_catalog() -> dict[str, Any]:
    """Catalog JSON with a cost_class on every model row.

    The snapshot stays free of baked-in class labels so a token-set change
    reclassifies without rewriting catalog.json.
    """
    payload = load_catalog().to_dict()
    for row in payload["models"]:
        row["cost_class"] = classify_cost(str(row.get("slug") or ""))
    return payload


def build_plan(
    *,
    pins: Mapping[str, str] | None = None,
    advertised: Sequence[str] | None = None,
) -> RoutingPlan:
    """Build the role DAG. Pins win; advertised ids bound the wire pick."""
    pin_map = {key: (pins.get(key) or "").strip() for key in ROUTE_ROLE_KEYS} if pins else {}
    advertised_ids = _clean_ids(advertised)
    catalog = load_catalog()
    listed = tuple(row for row in catalog.models if row.listed)
    roles: list[RoleAssignment] = []
    for role in ROUTE_ROLE_KEYS:
        cost = ROLE_COST_CLASS[role]
        pin = pin_map.get(role, "")
        suggestion = _suggest_catalog_slug(cost, listed)
        if pin:
            wire = pin
            reason = "operator pin"
        elif advertised_ids:
            wire = _pick_advertised(cost, advertised_ids)
            if wire != DEFAULT_MODEL and classify_cost(wire) == cost:
                reason = "advertised cost-class match"
            elif wire != DEFAULT_MODEL:
                reason = "advertised cheapest fallback"
            else:
                reason = "no advertised id in cost class; inherit"
        else:
            wire = DEFAULT_MODEL
            reason = "no advertised set; inherit session default"
        roles.append(
            RoleAssignment(
                role=role,
                cost_class=cost,
                pin=pin,
                wire_id=wire or DEFAULT_MODEL,
                suggestion=suggestion,
                reason=reason,
            )
        )
    return RoutingPlan(roles=tuple(roles), edges=ROLE_DAG_EDGES)


def resolve_wire_id(
    role: str,
    *,
    pins: Mapping[str, str] | None = None,
    advertised: Sequence[str] | None = None,
) -> str:
    """Id to send on the wire for *role*, or ``auto`` to inherit."""
    plan = build_plan(pins=pins, advertised=advertised)
    row = plan.assignment(role)
    if row is None:
        return DEFAULT_MODEL
    return row.wire_id or DEFAULT_MODEL


def orchestrator_turn_role(*, in_stage: bool, synthetic: bool) -> str:
    """Pick the DAG role for one orchestrator chat turn.

    Stage execution is the bulk of coding tokens. Synthetic coordinator
    turns (subagent synthesis, recovery continuations) are control traffic
    and stay economy. The remaining unpinned turn is plan
    decomposition and spends on capability.
    """
    if in_stage:
        return ROLE_EXECUTION
    if synthetic:
        return ROLE_ORCHESTRATION
    return ROLE_PLANNING


async def apply_role_model(client: Any, role: str) -> str:
    """Best-effort ``set_model`` for a task-class role. Never raises.

    A namespaced pin may be a native id for an adapted harness. Apply it only
    when explicitly pinned and advertised by this client. Catalog-only slugs
    and unpinned namespaced suggestions stay unapplied; their returned id is a
    plan value, not proof of execution. No provider forwarding happens here.
    """
    if role not in ROUTE_ROLE_KEYS:
        return DEFAULT_MODEL
    pins = _load_pins()
    advertised = _advertised_from_client(client)
    wire = resolve_wire_id(role, pins=pins, advertised=advertised)
    if not wire or wire == DEFAULT_MODEL:
        return DEFAULT_MODEL
    namespaced = not _is_harness_wire_id(wire)
    pinned = (pins.get(role) or "").strip() == wire
    if namespaced:
        from junction.acp.client import model_is_unusable

        # An empty advertisement means unknown to the shared predicate. It
        # must not activate a catalog slug, nor may a suggestion enable a
        # provider the operator did not explicitly select for this role.
        if not pinned or not advertised or model_is_unusable(wire, advertised):
            logger.info("model-router role %s skip set_model for sidecar slug", role)
            return wire
    setter = getattr(client, "set_model", None)
    if setter is None and namespaced:
        # ``AcpProvider`` wraps the live client without re-exporting
        # ``set_model``. Reach it through the wrapper so an admitted
        # namespaced pin is not dropped on spec-family harness sessions.
        from junction.llm_helpers import resolve_substitute_set_model

        setter = resolve_substitute_set_model(client)
    if setter is None:
        return DEFAULT_MODEL
    try:
        await setter(wire)
    except Exception as exc:
        # An explicit operator pin that could not be applied must be visible;
        # the session still proceeds on the backend default (best effort).
        log = logger.warning if pinned else logger.info
        log("model-router role %s apply skipped (%s)", role, type(exc).__name__)
        return DEFAULT_MODEL
    return wire


def _load_pins() -> dict[str, str]:
    try:
        from junction.config.loader import JunctionConfig

        return dict(JunctionConfig.load().agent.role_models)
    except Exception:
        return {}


def _advertised_from_client(client: Any) -> list[str]:
    handle = getattr(client, "_handle", None)
    entries = _materialize_available_models(getattr(client, "available_models", None))
    if not entries and handle is not None:
        entries = _materialize_available_models(getattr(handle, "available_models", None))
    if not entries:
        return []
    try:
        from junction.acp.client import advertised_model_ids

        return advertised_model_ids(entries)
    except Exception:
        return []


def _materialize_available_models(value: Any) -> Any:
    """``available_models`` is a method on ACP clients, a list on tests."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return value
    if callable(value):
        try:
            value = value()
        except Exception:
            logger.debug("model-router advertised lookup failed", exc_info=True)
            return None
    return value


def _is_harness_wire_id(model_id: str) -> bool:
    """True when *model_id* is a bare (non-namespaced) harness ``set_model`` id."""
    return bool(model_id) and "/" not in model_id


def _clean_ids(raw: Sequence[str] | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        value = item.strip()
        if not value or value == DEFAULT_MODEL or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _pick_advertised(cost_class: str, advertised: Sequence[str]) -> str:
    matched = [item for item in advertised if classify_cost(item) == cost_class]
    if matched:
        return sorted(matched)[0]
    # Economy roles should not inherit a flagship session default when a
    # cheaper advertised id exists. Capable/standard stay on ``auto`` rather
    # than silently downgrading planning.
    if cost_class == COST_ECONOMY:
        ranked = sorted(
            advertised,
            key=lambda item: (_CLASS_RANK.get(classify_cost(item), 99), item),
        )
        if ranked:
            return ranked[0]
    return DEFAULT_MODEL


def _suggest_catalog_slug(cost_class: str, listed: Iterable[CatalogModel]) -> str:
    matched = [row for row in listed if classify_cost(row.slug) == cost_class]
    if not matched:
        return ""
    matched.sort(key=lambda row: (-row.priority, row.slug))
    return matched[0].slug
