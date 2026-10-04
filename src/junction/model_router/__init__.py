"""Junction's model plane: a loopback catalog listener plus role routing.

``junction up`` starts the listener (typically ``:4202``). This package also
probes health, ships the namespaced model-choice catalog, and plans role
routing. It never copies credentials, never logs secret-bearing bodies, and
never binds a non-loopback host. Provider translation is not bundled. If the
listener is down, the ACP gateway still runs — that is a documented degraded
mode, not a hard failure.
"""

from __future__ import annotations

from junction.model_router.catalog import (
    MODEL_ID_MAX_LEN,
    MODEL_ID_PATTERN,
    load_catalog,
)
from junction.model_router.probe import (
    DEFAULT_GATEWAY_PORT,
    DEFAULT_ROUTER_PORT,
    HEALTH_PATH,
    LOOPBACK_HOST,
    PROBE_TIMEOUT_SECS,
    RouterStatus,
    probe_status,
)
from junction.model_router.routing import (
    ROLE_DAG_EDGES,
    ROUTE_ROLE_KEYS,
    annotated_catalog,
    apply_role_model,
    build_plan,
    classify_cost,
    resolve_wire_id,
)

__all__ = [
    "DEFAULT_GATEWAY_PORT",
    "DEFAULT_ROUTER_PORT",
    "HEALTH_PATH",
    "LOOPBACK_HOST",
    "MODEL_ID_MAX_LEN",
    "MODEL_ID_PATTERN",
    "PROBE_TIMEOUT_SECS",
    "ROLE_DAG_EDGES",
    "ROUTE_ROLE_KEYS",
    "RouterStatus",
    "annotated_catalog",
    "apply_role_model",
    "build_plan",
    "classify_cost",
    "load_catalog",
    "probe_status",
    "resolve_wire_id",
]
