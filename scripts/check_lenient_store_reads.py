#!/usr/bin/env python3
"""check_lenient_store_reads.py — no new lenient read of a JSON store file.

A JSON store is a file that a process loads, changes and writes back. A
*lenient* read turns a failed read into an empty store::

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}

The next save then replaces the original file with the empty store. A byte-order
mark, a truncated file or one transient ``OSError`` is enough to lose every
record. The stores listed in ``STORE_MODULES`` load through
``warding.atomic_write.load_json_store`` or ``locked_update`` instead. Those
helpers treat only a missing file as empty, and they refuse to write after an
unreadable load.

## What is flagged

In each store module, a ``json.loads`` / ``json.load`` call that reads a file
(directly through ``.read_text()``, ``.read_bytes()`` or ``open()``, or through
a name assigned from one of those in the same function) and sits in a ``try``
whose handler catches ``OSError``, ``ValueError``, ``JSONDecodeError``,
``UnicodeDecodeError``, ``Exception`` or everything, without re-raising.

## Ratchet

``scripts/lenient_store_reads_baseline.json`` lists the sites that exist today
as ``<file>::<function>`` with a count. The gate fails when a site is new or its
count grows. It also fails when a baseline entry no longer exists, so the list
only shrinks: run ``--update-baseline`` after you remove a site.

A site that is a read-only lookup, never written back, can carry a
``strict-store-ok`` comment on the ``json.loads`` line. State why in the comment.

## Read-modify-write

A hit in a function that also calls a writer (``_write_mcp_json``,
``atomic_write``, ``_save``, ``json.dump`` and so on) is reported with a
``[writes]`` suffix. Such a function is a read-modify-write. The baseline may
not hold it: the gate fails on it. Load strictly, or add the ``strict-store-ok``
marker with the reason the written file is not the one that was read.

## Usage

    python3 scripts/check_lenient_store_reads.py                    # scan
    python3 scripts/check_lenient_store_reads.py --update-baseline  # rewrite the baseline
    python3 scripts/check_lenient_store_reads.py --test             # self-test
"""

from __future__ import annotations

import ast
import json
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_ROOT = os.path.join("src", "warding")
BASELINE = os.path.join(REPO_ROOT, "scripts", "lenient_store_reads_baseline.json")
MARKER = "strict-store-ok"

#: Modules whose JSON stores must load strictly (paths under ``src/warding``).
STORE_MODULES = (
    "session_map.py",
    "cron.py",
    "subagent_persistence.py",
    "apps/dependency_ledger.py",
    "dashboard/handlers/mcp.py",
    "dashboard/handlers/mcp_custom.py",
)

READ_ATTRS = {"read_text", "read_bytes"}
#: Calls that write a store back. A lenient read in a function that also calls one
#: of these is a read-modify-write, which the baseline may not hold.
WRITE_CALLS = {
    "_write_mcp_json",
    "_atomic_write",
    "_atomic_json_write",
    "atomic_write",
    "_save",
    "_write",
    "write_text",
    "write_bytes",
    "dump",
}
SWALLOWED = {
    "OSError",
    "IOError",
    "ValueError",
    "JSONDecodeError",
    "UnicodeDecodeError",
    "Exception",
    "BaseException",
}

REMEDY = (
    "Load the store with `warding.atomic_write.load_json_store` (then call "
    "`require_writable()` before a write) or change it with `locked_update`. "
    f"A read-only lookup can carry a `{MARKER}` comment that says why."
)


def _is_file_read(node: ast.AST) -> bool:
    """True for ``x.read_text(...)``, ``x.read_bytes(...)`` and ``open(...)``."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in READ_ATTRS:
        return True
    return isinstance(func, ast.Name) and func.id == "open"


def _is_json_load(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in ("loads", "load")
        and isinstance(func.value, ast.Name)
        and func.value.id == "json"
    )


def _is_json_load_name(func: ast.AST) -> bool:
    """True for ``json.dump`` (a write), so ``other.dump`` is not mistaken for one."""
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "json"
    )


def _handler_swallows(handler: ast.ExceptHandler) -> bool:
    if any(isinstance(n, ast.Raise) for n in ast.walk(handler)):
        return False
    if handler.type is None:
        return True
    types = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    for t in types:
        name = t.attr if isinstance(t, ast.Attribute) else getattr(t, "id", "")
        if name in SWALLOWED:
            return True
    return False


class _Visitor(ast.NodeVisitor):
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.scope: list[str] = []
        self.read_names: list[set[str]] = [set()]
        self.try_stack: list[bool] = []
        self.hits: list[tuple[str, int]] = []
        self.writes: list[bool] = [False]
        self.pending: list[list[tuple[str, int]]] = [[]]

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.scope.append(node.name)
        self.read_names.append(set())
        self.writes.append(False)
        self.pending.append([])
        outer, self.try_stack = self.try_stack, []
        self.generic_visit(node)
        self.try_stack = outer
        self.read_names.pop()
        wrote = self.writes.pop()
        for func, line in self.pending.pop():
            self.hits.append((func + (" [writes]" if wrote else ""), line))
        self.scope.pop()

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        if _is_file_read(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.read_names[-1].add(target.id)
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        swallows = any(_handler_swallows(h) for h in node.handlers)
        self.try_stack.append(swallows)
        for stmt in node.body:
            self.visit(stmt)
        self.try_stack.pop()
        for part in (node.handlers, node.orelse, node.finalbody):
            for stmt in part:
                self.visit(stmt)

    def visit_Call(self, node: ast.Call) -> None:
        if _is_json_load(node) and node.args and any(self.try_stack):
            arg = node.args[0]
            reads = any(_is_file_read(n) for n in ast.walk(arg)) or (
                isinstance(arg, ast.Name) and arg.id in self.read_names[-1]
            )
            if reads and MARKER not in self.lines[node.lineno - 1]:
                self.pending[-1].append((".".join(self.scope) or "<module>", node.lineno))
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in WRITE_CALLS and not (name == "dump" and not _is_json_load_name(func)):
            self.writes[-1] = True
        self.generic_visit(node)


def scan_source(source: str) -> list[tuple[str, int]]:
    """Return ``(function, line)`` for each lenient read in *source*."""
    tree = ast.parse(source)
    visitor = _Visitor(source.splitlines())
    visitor.visit(tree)
    return visitor.hits


def scan_tree(root: str) -> dict[str, int]:
    """Count lenient reads per ``<file>::<function>`` in the store modules."""
    counts: dict[str, int] = {}
    for rel in STORE_MODULES:
        path = os.path.join(root, SCAN_ROOT, rel)
        if not os.path.isfile(path):
            counts[f"{rel}::<missing module>"] = 1
            continue
        with open(path, encoding="utf-8") as fh:
            hits = scan_source(fh.read())
        for func, _line in hits:
            key = f"{rel}::{func}"
            counts[key] = counts.get(key, 0) + 1
    return counts


def compare(found: dict[str, int], baseline: dict[str, int]) -> tuple[list[str], list[str]]:
    """Return ``(new_or_grown, gone_or_shrunk)`` messages."""
    writers = [
        f"{key}: lenient read in a function that writes (read-modify-write)"
        for key in sorted(found)
        if key.endswith(" [writes]")
    ]
    grown = writers + [
        f"{key}: {n} lenient read(s), baseline {baseline.get(key, 0)}"
        for key, n in sorted(found.items())
        if n > baseline.get(key, 0) and not key.endswith(" [writes]")
    ]
    shrunk = [
        f"{key}: baseline {n}, found {found.get(key, 0)}"
        for key, n in sorted(baseline.items())
        if found.get(key, 0) < n
    ]
    return grown, shrunk


def _load_baseline() -> dict[str, int]:
    if not os.path.isfile(BASELINE):
        return {}
    with open(BASELINE, encoding="utf-8") as fh:
        return json.load(fh)  # strict-store-ok: tool input, not a runtime store


def _self_test() -> int:
    lenient = (
        "import json\n"
        "def load(p):\n"
        "    try:\n"
        "        return json.loads(p.read_text(encoding='utf-8'))\n"
        "    except (OSError, ValueError):\n"
        "        return {}\n"
    )
    via_name = (
        "import json\n"
        "class S:\n"
        "    def _load(self):\n"
        "        try:\n"
        "            raw = self.path.read_bytes()\n"
        "            return json.loads(raw)\n"
        "        except json.JSONDecodeError:\n"
        "            return {}\n"
    )
    strict = (
        "import json\n"
        "def load(p):\n"
        "    try:\n"
        "        return json.loads(p.read_text())\n"
        "    except ValueError as exc:\n"
        "        raise RuntimeError('bad') from exc\n"
    )
    bare = "import json\ndef load(p):\n    return json.loads(p.read_text())\n"
    marked = (
        "import json\n"
        "def load(p):\n"
        "    try:\n"
        f"        return json.loads(p.read_text())  # {MARKER}: lookup\n"
        "    except OSError:\n"
        "        return {}\n"
    )
    not_a_file = (
        "import json\n"
        "def load(s):\n"
        "    try:\n"
        "        return json.loads(s)\n"
        "    except ValueError:\n"
        "        return {}\n"
    )
    read_modify_write = (
        "import json\n"
        "def bump(p):\n"
        "    try:\n"
        "        data = json.loads(p.read_text())\n"
        "    except OSError:\n"
        "        data = {}\n"
        "    atomic_write(p, json.dumps(data))\n"
    )
    cases = [
        ("lenient direct read", lenient, 1),
        ("lenient read through a name", via_name, 1),
        ("handler re-raises", strict, 0),
        ("no try block", bare, 0),
        ("marked lookup", marked, 0),
        ("read-modify-write", read_modify_write, 1),
        ("parsing a string, not a file", not_a_file, 0),
    ]
    failed = 0
    for label, src, want in cases:
        got = len(scan_source(src))
        if got != want:
            print(f"SELF-TEST FAIL: {label}: expected {want} hit(s), got {got}")
            failed += 1
    if [f for f, _ in scan_source(read_modify_write)] != ["bump [writes]"]:
        print("SELF-TEST FAIL: a read-modify-write is not marked [writes]")
        failed += 1
    with tempfile.TemporaryDirectory() as tmp:
        for rel in STORE_MODULES:
            full = os.path.join(tmp, SCAN_ROOT, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(lenient if rel == STORE_MODULES[0] else "x = 1\n")
        found = scan_tree(tmp)
        grown, shrunk = compare(found, {})
        if len(grown) != 1 or shrunk:
            print(f"SELF-TEST FAIL: tree scan/compare gave {grown} / {shrunk}")
            failed += 1
        grown, shrunk = compare({}, found)
        if grown or len(shrunk) != 1:
            print(f"SELF-TEST FAIL: shrink detection gave {grown} / {shrunk}")
            failed += 1
    if failed:
        return 1
    print("check_lenient_store_reads: self-test ok")
    return 0


def main(argv: list[str]) -> int:
    if "--test" in argv:
        return _self_test()
    found = scan_tree(REPO_ROOT)
    if "--update-baseline" in argv:
        with open(BASELINE, "w", encoding="utf-8") as fh:
            json.dump(dict(sorted(found.items())), fh, indent=2)
            fh.write("\n")
        print(f"check_lenient_store_reads: baseline written ({len(found)} site(s))")
        return 0
    grown, shrunk = compare(found, _load_baseline())
    if grown:
        print("Lenient JSON store read(s) found:")
        for line in grown:
            print(f"  {line}")
        print(REMEDY)
    if shrunk:
        print("The baseline lists sites that no longer exist. Run with --update-baseline:")
        for line in shrunk:
            print(f"  {line}")
    if grown or shrunk:
        return 1
    print("check_lenient_store_reads: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
