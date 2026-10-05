"""Task kinds the harness router scores against.

Stdlib-only so the tool-argument validator can import the enum without pulling
in the ACP stack. The calling agent names the kind explicitly (an enum on
the MCP tool); the router never guesses it from free text.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

KIND_PLAN = "plan"
KIND_IMPLEMENT = "implement"
KIND_DEBUG = "debug"
KIND_REVIEW = "review"
KIND_TEST = "test"
KIND_RESEARCH = "research"
KIND_DOCS = "docs"
KIND_QUICK = "quick"
KIND_BULK = "bulk"

TASK_KINDS: tuple[str, ...] = (
    KIND_PLAN,
    KIND_IMPLEMENT,
    KIND_DEBUG,
    KIND_REVIEW,
    KIND_TEST,
    KIND_RESEARCH,
    KIND_DOCS,
    KIND_QUICK,
    KIND_BULK,
)

KIND_DESCRIPTIONS: Mapping[str, str] = MappingProxyType(
    {
        KIND_PLAN: "architecture, decomposition, design decisions",
        KIND_IMPLEMENT: "write or change code for a feature",
        KIND_DEBUG: "reproduce and fix a bug or failing test",
        KIND_REVIEW: "review a diff, audit code, find defects",
        KIND_TEST: "write or extend tests",
        KIND_RESEARCH: "look things up: docs, web, current events",
        KIND_DOCS: "write prose: docs, READMEs, changelogs",
        KIND_QUICK: "small edit, one-liner, quick question",
        KIND_BULK: "high-volume mechanical work: renames, codemods, many small items",
    }
)

# DAG role → kind, so a caller that only knows its role still routes.
ROLE_DEFAULT_KIND: Mapping[str, str] = MappingProxyType(
    {
        "planning": KIND_PLAN,
        "execution": KIND_IMPLEMENT,
        "subagent": KIND_IMPLEMENT,
        "orchestration": KIND_QUICK,
        "background": KIND_QUICK,
    }
)

DEFAULT_KIND = KIND_IMPLEMENT


def normalize_kind(kind: str | None, *, role: str | None = None) -> str:
    """A known task kind: *kind* if valid, else the role's default, else implement."""
    value = (kind or "").strip().lower()
    if value in TASK_KINDS:
        return value
    if role:
        mapped = ROLE_DEFAULT_KIND.get(role.strip().lower())
        if mapped:
            return mapped
    return DEFAULT_KIND
