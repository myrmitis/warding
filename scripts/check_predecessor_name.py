#!/usr/bin/env python3
"""check_predecessor_name.py -- keep the predecessor project's identity out of the tree.

Warding was first developed under a predecessor name. That identity is retired:
its domain, repository slug, environment prefix, data home, Python package and
bundle id all moved to Warding's own (``warding.dev``, ``myrmitis/warding``,
``WARDING_*``, ``~/.warding``, ``warding``, ``dev.warding.desktop``).

The predecessor name is also an ordinary technical word. A Windows *directory
junction* is a reparse point that ``platform_compat`` creates and detects, and
``os.path.isjunction`` and ``_winapi.CreateJunction`` are standard-library
names. Those uses are correct and stay. So this gate does not match the bare
word. It matches only spellings that can name the retired identity:

* the retired product domain;
* the retired repository slug;
* the retired environment prefix (upper case, then an upper-case letter);
* the retired data home (a dot directly before the name);
* the retired Python package (``src/<name>``, ``import``, ``from``, ``-m``);
* the retired bundle id and the retired company suffix ``labs``;
* the capitalized name followed by a product noun (gateway, dashboard, CLI,
  app, desktop, "by").

Dated history keeps its references: ``docs/adr/`` and ``CHANGELOG.md`` are not
scanned, because an accepted decision or a release note must keep the evidence
it cites. Every other tracked text file is scanned. There is no inline
suppression marker.

This file and its tests assemble the name from fragments, so both are scanned
like any other file and neither carries the identity they hunt.

## Usage

    # scan the whole tracked tree (exit 1 on any violation)
    python3 scripts/check_predecessor_name.py

    # scan explicit files, ignoring git (exit 1 on any violation)
    python3 scripts/check_predecessor_name.py README.md docs/foo.md

    # self-test: plant probes, assert each verdict
    python3 scripts/check_predecessor_name.py --test
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent

# Assembled from fragments so this file does not contain the identity it hunts.
_NAME = "junc" + "tion"
_CAP = _NAME.capitalize()
_UPPER = _NAME.upper()
_OWNER = "laq" + "aer"

#: Dated history that must keep the evidence it cites.
EXEMPT_PREFIXES = ("docs/adr/",)
EXEMPT_FILES = ("CHANGELOG.md",)

#: A tracked file larger than this is skipped; a multi-megabyte blob is data.
MAX_BYTES = 4_000_000

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("retired domain", re.compile(rf"get{_NAME}", re.IGNORECASE)),
    ("retired repository slug", re.compile(rf"{_OWNER}[/\\]+{_NAME}\b", re.IGNORECASE)),
    ("retired environment prefix", re.compile(rf"\b{_UPPER}_[A-Z]")),
    ("retired data home", re.compile(rf"(?<![\w])\.{_NAME}\b", re.IGNORECASE)),
    (
        "retired Python package",
        re.compile(rf"src[/\\]{_NAME}\b|\b(?:import|from)\s+{_NAME}\b|-m\s+{_NAME}\b"),
    ),
    ("retired bundle id", re.compile(rf"\bdev\.{_NAME}\b", re.IGNORECASE)),
    ("retired company name", re.compile(rf"\b{_NAME}[ -]labs\b", re.IGNORECASE)),
    (
        "retired product name",
        re.compile(rf"\b{_CAP}\s+(?:gateway|dashboard|CLI|app|desktop|by)\b"),
    ),
)


@dataclass(frozen=True)
class Violation:
    path: str
    line_no: int
    rule: str
    text: str

    def render(self) -> str:
        return f"{self.path}:{self.line_no}: [{self.rule}] {self.text.strip()[:160]}"


def is_exempt(path: str) -> bool:
    return path in EXEMPT_FILES or path.startswith(EXEMPT_PREFIXES)


def scan_text(path: str, text: str) -> list[Violation]:
    """Return every line of *text* that carries a retired-identity spelling."""
    if is_exempt(path):
        return []
    found: list[Violation] = []
    for number, line in enumerate(text.splitlines(), 1):
        for rule, pattern in _PATTERNS:
            if pattern.search(line):
                found.append(Violation(path, number, rule, line))
                break
    return found


def read_text(path: Path) -> str | None:
    """File text, or None for something that is not a readable text file."""
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    return [p for p in out.decode("utf-8", errors="replace").split("\0") if p]


def relative(path: str) -> str:
    candidate = Path(path)
    try:
        return candidate.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return candidate.as_posix()


def scan_paths(paths: Sequence[str]) -> list[Violation]:
    found: list[Violation] = []
    for path in paths:
        rel = relative(path)
        text = read_text(Path(path) if Path(path).is_absolute() else ROOT / rel)
        if text is None:
            continue
        found.extend(scan_text(rel, text))
    return found


def report(violations: Sequence[Violation]) -> int:
    if not violations:
        print("predecessor-name gate passed: no retired identity outside dated history.")
        return 0
    for item in violations:
        print(f"::error file={item.path},line={item.line_no}::{item.rule}")
        print(f"  {item.render()}")
    print(
        f"\npredecessor-name gate FAILED: {len(violations)} line(s). Use Warding's own "
        "identity (warding, WARDING_*, ~/.warding, warding.dev, myrmitis/warding). "
        "A Windows directory link is still called a junction; only the identity "
        "spellings fail."
    )
    return 1


def self_test() -> int:
    """Plant probes and assert each verdict, so a typo cannot silently disable a rule."""
    n, cap, up = _NAME, _CAP, _UPPER
    cases: list[tuple[str, str, str, bool]] = [
        ("domain", "site/a.ts", f'url: "https://get{n}.dev"', True),
        ("repository slug", "README.md", f"gh repo clone {_OWNER}/{n}", True),
        ("environment prefix", "src/a.py", f'os.environ["{up}_HOME"]', True),
        ("data home", "docs/a.md", f"Data lives in ~/.{n}/config.json.", True),
        ("package path", "setup.py", f'packages=find_packages("src/{n}")', True),
        ("package import", "src/a.py", f"from {n}.session import Session", True),
        ("module run", "docs/a.md", f"python -m {n} doctor", True),
        ("bundle id", "packaging/a.plist", f"dev.{n}.desktop", True),
        ("company suffix", "site/a.ts", f"{cap} Labs", True),
        ("product noun", "docs/a.md", f"Open the {cap} dashboard.", True),
        ("windows junction prose", "docs/a.md", f"A directory {n} needs no privilege.", False),
        ("windows junction class", "test/a.py", f"class Test{cap}Classification:", False),
        ("stdlib probe", "src/a.py", f"os.path.is{n}(p)", False),
        ("winapi call", "test/a.py", f"_winapi.Create{cap}(t, ln)", False),
        ("helper call", "src/a.py", f"platform_compat.symlink_or_{n}(t, ln)", False),
        ("powershell item type", "skills/a.md", f"New-Item -ItemType {cap} -Path x", False),
        ("sentence end", "docs/a.md", f"it follows the {n}.", False),
        ("i18n conjunction", "website/a.ts", f"type: 'con{n}'", False),
        ("adr history", "docs/adr/0009-x.md", f"github.com/{_OWNER}/{n}/tree/abc", False),
        ("changelog history", "CHANGELOG.md", f"Renamed from {cap} by Myrmitis.", False),
    ]
    failures = 0
    for label, path, text, expect_violation in cases:
        got = bool(scan_text(path, text))
        ok = got == expect_violation
        if not ok:
            failures += 1
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if failures:
        print(f"predecessor-name gate self-test FAILED: {failures} probe(s) wrong")
        return 1
    print(f"predecessor-name gate self-test passed ({len(cases)} probes)")
    return 0


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("paths", nargs="*", help="files to scan instead of the tracked tree")
    parser.add_argument("--test", action="store_true", help="run the built-in probes and exit")
    args = parser.parse_args(list(argv))
    if args.test:
        return self_test()
    return report(scan_paths(args.paths or tracked_files()))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
