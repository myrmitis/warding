"""Regression: module-scope ``warding.agent`` imports.

The four modules below historically used function-local
``from warding.agent import ...`` statements, several justified by
``# circular import`` comments that misstated the real import graph
(``warding.agent`` imports nothing from ``warding.dashboard.*`` or
``warding.session``).  The imports were hoisted to module scope; these
tests keep them there and prove no cycle exists in either load order.

Order-dependent cycles only surface in a fresh interpreter, not under a
bare import in an already-warm test process — hence the subprocess runs.
"""

import re
import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"

_HOISTED_MODULES = (
    "warding.dashboard.handlers.agents",
    "warding.dashboard.handlers.mcp",
    "warding.dashboard.handlers.hooks",
    "warding.session",
)

_HOISTED_FILES = (
    "warding/dashboard/handlers/agents.py",
    "warding/dashboard/handlers/mcp.py",
    "warding/dashboard/handlers/hooks.py",
    "warding/session.py",
)


def _fresh_import(statements: str) -> None:
    """Run import statements in a fresh child interpreter; fail on any error."""
    res = subprocess.run(
        [sys.executable, "-c", statements],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert res.returncode == 0, (
        f"fresh-interpreter import failed (a hoisted import created a cycle?):\n"
        f"{res.stderr}"
    )


def test_hoisted_modules_import_together_fresh() -> None:
    """All four hoisted modules import together in a cold interpreter."""
    _fresh_import("; ".join(f"import {m}" for m in _HOISTED_MODULES))


def test_hoisted_modules_import_agent_first_fresh() -> None:
    """Loading warding.agent BEFORE the handlers must also be cycle-free.

    A cycle between ``agent`` and these modules would be order-dependent:
    it can pass in one load order and raise ImportError in the other.
    """
    _fresh_import(
        "; ".join(["import warding.agent"] + [f"import {m}" for m in _HOISTED_MODULES])
    )


def test_no_function_local_agent_imports_remain() -> None:
    """Ratchet: no function-local ``from warding.agent import`` in the four files.

    A reintroduced local import would silently undo the hoist and eventually
    re-grow the false ``# circular import`` folklore this fixed.  All three
    repo spellings are covered: ``from warding.agent import X``,
    ``import warding.agent``, and ``from warding import agent`` (the
    last matched on the bare ``agent`` name so sibling imports like
    ``agent_state`` don't trip it; comments are excluded from the match).
    """
    local_import = re.compile(
        r"^[ \t]+(?:"
        r"from warding\.agent import"
        r"|import warding\.agent\b"
        r"|from warding import [^#\n]*\bagent\b"
        r")",
        re.MULTILINE,
    )
    offenders = {}
    for rel in _HOISTED_FILES:
        text = (_SRC / rel).read_text(encoding="utf-8")
        hits = local_import.findall(text)
        if hits:
            offenders[rel] = len(hits)
    assert not offenders, (
        f"function-local warding.agent imports reintroduced: {offenders}; "
        f"import at module scope instead (no cycle exists)"
    )
