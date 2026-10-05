"""Namespaced model-choice catalog observed from Codex Router.

The sidecar owns credentials and live entitlement. This module ships the
**choices** — provider ids and ``provider/model`` slugs — so Junction can list
them, classify them, and route work without vendoring the Node tree or copying
secret files. Live-catalog providers (Copilot, Groq, local Ollama, …) ship as
provider rows without hardcoded model ids: the operator curates those on the
sidecar.

Source: MIT ``duolahypercho/codex-router`` registry fragments. Copied fields are
slugs, labels, and non-secret metadata only.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CATALOG_FILE = Path(__file__).resolve().parent / "catalog.json"

# Grammar for a model id that may be a kiro-cli id *or* a namespaced router slug
# (``kimi-oauth/k3``, ``openrouter/tencent/hy4-preview``). Slash is the namespace
# separator. ``..``, ``//``, ``/.``, a leading or trailing slash stay out so a
# pin cannot be a path. Owned here so Settings PATCH, CLI pins, and the catalog
# agree.
MODEL_ID_MAX_LEN = 64
MODEL_ID_PATTERN = r"^(?!.*\.\.)(?!.*//)(?!.*/\./)(?!/)[A-Za-z0-9._/\-\[\]]*(?<!/)$"

CATALOG_VERSION = 1
SOURCE_PROJECT = "duolahypercho/codex-router"

AUTH_ANONYMOUS = "anonymous"
AUTH_API_KEY = "api_key"
AUTH_KEYLESS = "keyless"
AUTH_LIVE = "live"
AUTH_OAUTH = "oauth"
AUTH_PER_MODEL = "per-model"

CATALOG_KIND_LIVE = "live"
CATALOG_KIND_STATIC = "static"


@dataclass(frozen=True, slots=True)
class CatalogProvider:
    """One inference vendor or access method. Never carries a credential."""

    id: str
    display_name: str
    auth_kind: str
    catalog_kind: str
    owned_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "auth_kind": self.auth_kind,
            "catalog_kind": self.catalog_kind,
            "owned_by": self.owned_by,
        }


@dataclass(frozen=True, slots=True)
class CatalogModel:
    """One namespaced model choice (``provider/model``)."""

    slug: str
    display_name: str
    provider: str
    listed: bool
    context_window: int | None
    input_modalities: tuple[str, ...]
    default_effort: str
    priority: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "display_name": self.display_name,
            "provider": self.provider,
            "listed": self.listed,
            "context_window": self.context_window,
            "input_modalities": list(self.input_modalities),
            "default_effort": self.default_effort,
            "priority": self.priority,
        }


@dataclass(frozen=True, slots=True)
class ModelCatalog:
    """Frozen snapshot of router model choices."""

    version: int
    source: str
    providers: tuple[CatalogProvider, ...]
    models: tuple[CatalogModel, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "source": self.source,
            "provider_count": len(self.providers),
            "model_count": len(self.models),
            "providers": [p.to_dict() for p in self.providers],
            "models": [m.to_dict() for m in self.models],
        }


def load_catalog() -> ModelCatalog:
    """Load the shipped snapshot. Empty catalog on a corrupt file, never raise."""
    return _load_catalog()


@lru_cache(maxsize=1)
def _load_catalog() -> ModelCatalog:
    try:
        with open(_CATALOG_FILE, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        logger.warning("model-router catalog.json unreadable; catalog empty", exc_info=True)
        return ModelCatalog(version=CATALOG_VERSION, source=SOURCE_PROJECT, providers=(), models=())
    if not isinstance(raw, dict):
        return ModelCatalog(version=CATALOG_VERSION, source=SOURCE_PROJECT, providers=(), models=())
    providers: list[CatalogProvider] = []
    for row in raw.get("providers") or []:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        providers.append(
            CatalogProvider(
                id=row["id"],
                display_name=str(row.get("display_name") or row["id"]),
                auth_kind=str(row.get("auth_kind") or AUTH_API_KEY),
                catalog_kind=str(row.get("catalog_kind") or CATALOG_KIND_STATIC),
                owned_by=str(row.get("owned_by") or ""),
            )
        )
    models: list[CatalogModel] = []
    for row in raw.get("models") or []:
        if not isinstance(row, dict) or not isinstance(row.get("slug"), str):
            continue
        window = row.get("context_window")
        modalities = row.get("input_modalities") or []
        if not isinstance(modalities, list):
            modalities = []
        models.append(
            CatalogModel(
                slug=row["slug"],
                display_name=str(row.get("display_name") or row["slug"]),
                provider=str(row.get("provider") or row["slug"].split("/", 1)[0]),
                listed=bool(row.get("listed", True)),
                context_window=window if isinstance(window, int) else None,
                input_modalities=tuple(str(m) for m in modalities if isinstance(m, str)),
                default_effort=str(row.get("default_effort") or ""),
                priority=int(row["priority"]) if isinstance(row.get("priority"), int) else 0,
            )
        )
    version = raw.get("version")
    return ModelCatalog(
        version=int(version) if isinstance(version, int) else CATALOG_VERSION,
        source=str(raw.get("source") or SOURCE_PROJECT),
        providers=tuple(providers),
        models=tuple(models),
    )


def is_catalog_slug(value: str) -> bool:
    """True when *value* is a namespaced slug this snapshot lists."""
    needle = (value or "").strip()
    if not needle:
        return False
    return any(row.slug == needle for row in load_catalog().models)


def catalog_slugs() -> frozenset[str]:
    return frozenset(row.slug for row in load_catalog().models)
