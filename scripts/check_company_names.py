#!/usr/bin/env python3
"""check_company_names.py -- keep the retired company name out of the tree.

Warding names the *service* or the *distro* it means (S3, Polly, AL2023), never
the company that sells it. Some spellings still contain the name because an
external system defined them and this code must write them exactly to work: an
AWS service hostname, a PyPI package, a Bedrock model id, the predecessor CLI's
auth-store directory. Those are the **functional identifiers**, and they are
listed in ``scripts/company-name-allowlist.txt``. Everything else is residue.

How a line is judged:

1. Every ``token:`` regex from the allowlist is removed from the line.
2. If the company name still appears, the line is a violation, unless an
   ``allow:`` entry accepts that exact line in that exact file.

Step 1 is what makes the rule strict: a line that carries both a functional
hostname and a prose mention of the company is still reported, because only the
hostname is removed.

Every tracked text file is scanned except the allowlist itself, which is the one
place the name is written out in full. There is no inline suppression marker: a
marker would let a mention opt itself back in.

This file and its tests assemble the name from fragments, so both are scanned
like any other file and neither carries it.

## Usage

    # scan the whole tracked tree (exit 1 on any violation)
    python3 scripts/check_company_names.py

    # scan explicit files, ignoring git (exit 1 on any violation)
    python3 scripts/check_company_names.py README.md docs/foo.md

    # self-test: plant probes, assert each verdict
    python3 scripts/check_company_names.py --test
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST_PATH = ROOT / "scripts" / "company-name-allowlist.txt"

# Assembled from fragments so this file does not contain the name it hunts.
_NAME = "ama" + "zon"
_NAME_RE = re.compile(_NAME, re.IGNORECASE)

#: A tracked file larger than this is skipped; none of the sources are, and a
#: multi-megabyte blob is data, not prose.
MAX_BYTES = 4_000_000


@dataclass(frozen=True)
class Rules:
    """Functional-identifier tokens and exact-line allowances."""

    tokens: tuple[re.Pattern[str], ...]
    allows: tuple[tuple[re.Pattern[str], re.Pattern[str]], ...]


@dataclass(frozen=True)
class Violation:
    path: str
    line_no: int
    text: str

    def render(self) -> str:
        return f"{self.path}:{self.line_no}: {self.text.strip()[:160]}"


def parse_rules(lines: Iterable[str]) -> Rules:
    """Parse the allowlist format: ``token: <re>`` and ``allow: <path> :: <line>``."""
    tokens: list[re.Pattern[str]] = []
    allows: list[tuple[re.Pattern[str], re.Pattern[str]]] = []
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        kind, sep, body = line.partition(":")
        body = body.strip()
        if not sep or not body:
            raise SystemExit(f"allowlist line {number}: expected 'token:' or 'allow:': {raw!r}")
        if kind == "token":
            tokens.append(re.compile(body, re.IGNORECASE))
        elif kind == "allow":
            path_part, arrow, line_part = body.partition(" :: ")
            if not arrow:
                raise SystemExit(f"allowlist line {number}: allow needs ' :: ' between regexes")
            allows.append((re.compile(path_part.strip()), re.compile(line_part.strip())))
        else:
            raise SystemExit(f"allowlist line {number}: unknown entry kind {kind!r}")
    return Rules(tuple(tokens), tuple(allows))


def load_rules(path: Path = ALLOWLIST_PATH) -> Rules:
    return parse_rules(path.read_text(encoding="utf-8").splitlines())


def scan_text(path: str, text: str, rules: Rules) -> list[Violation]:
    """Return every line of *text* that names the company outside the allowlist."""
    path_allows = [line_re for path_re, line_re in rules.allows if path_re.search(path)]
    found: list[Violation] = []
    for number, line in enumerate(text.splitlines(), 1):
        if not _NAME_RE.search(line):
            continue
        residue = line
        for token in rules.tokens:
            residue = token.sub("", residue)
        if not _NAME_RE.search(residue):
            continue
        if any(line_re.search(line) for line_re in path_allows):
            continue
        found.append(Violation(path, number, line))
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


def scan_paths(paths: Sequence[str], rules: Rules) -> list[Violation]:
    skip = ALLOWLIST_PATH.relative_to(ROOT).as_posix()
    found: list[Violation] = []
    for path in paths:
        rel = relative(path)
        if rel == skip:
            continue
        text = read_text(ROOT / rel if not Path(path).is_absolute() else Path(path))
        if text is None:
            continue
        found.extend(scan_text(rel, text, rules))
    return found


def report(violations: Sequence[Violation]) -> int:
    if not violations:
        print("company-name gate passed: no mention outside the functional allowlist.")
        return 0
    for item in violations:
        print(f"::error file={item.path},line={item.line_no}::company name outside the allowlist")
        print(f"  {item.render()}")
    print(
        f"\ncompany-name gate FAILED: {len(violations)} line(s). Name the service or the "
        "distro instead (S3, Polly, AL2023). If an external system defines the spelling and "
        "the code must write it exactly, add a token to scripts/company-name-allowlist.txt "
        "with a reason in the PR."
    )
    return 1


def self_test() -> int:
    """Plant probes and assert each verdict, so a typo cannot silently disable a rule."""
    name = _NAME.capitalize()
    low = _NAME
    rules = parse_rules(
        [
            "token: " + low + r"aws\\?\.com",
            "token: " + low + r"[-_]transcribe",
            "token: " + low + r"\.(?:nova|titan)[\w.:-]*",
            "token: (?-i:" + name + r"[A-Z][A-Za-z0-9]+)",
            "token: " + low + r"-?q(?:-?developer-?cli)?(?![a-z])",
            r"allow: ^docs/fixture\.md$ :: only-here",
        ]
    )
    cases: list[tuple[str, str, str, bool]] = [
        ("prose distro name", "docs/a.md", f"Runs on {name} Linux 2023.", True),
        ("prose service name", "docs/a.md", f"Uses {name} Polly for speech.", True),
        ("hostname is functional", "src/a.py", f'URL = "https://s3.{low}aws.com/b"', False),
        ("escaped-dot hostname", "src/a.py", f'rf"^x\\.{low}aws\\.com$"', False),
        ("package is functional", "pyproject.toml", f'"{low}-transcribe==0.6.4"', False),
        ("model id is functional", "src/a.py", f'"{low}.nova-pro-v1:0"', False),
        ("camel-case api id", "src/a.py", f'ARN = ".../{name}SSMManagedInstanceCore"', False),
        ("predecessor dir", "src/a.py", f'".local/share/{low}-q/data"', False),
        ("mixed line still reported", "docs/a.md", f"{name} S3 at b.s3.{low}aws.com", True),
        ("space after q is prose", "docs/a.md", f"the {name} Q Developer CLI", True),
        ("allowed line in its file", "docs/fixture.md", f"{name} only-here", False),
        ("same line in another file", "docs/other.md", f"{name} only-here", True),
        ("no mention", "docs/a.md", "Runs on AL2023 with S3 and Polly.", False),
    ]
    failures = 0
    for label, path, text, expect_violation in cases:
        got = bool(scan_text(path, text, rules))
        status = "ok  " if got == expect_violation else "FAIL"
        if got != expect_violation:
            failures += 1
        print(f"  {status} {label}")
    if failures:
        print(f"company-name gate self-test FAILED: {failures} probe(s) wrong")
        return 1
    print(f"company-name gate self-test passed ({len(cases)} probes)")
    return 0


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", help="files to scan instead of the tracked tree")
    parser.add_argument("--test", action="store_true", help="run the built-in probes and exit")
    args = parser.parse_args(list(argv))
    if args.test:
        return self_test()
    rules = load_rules()
    paths = args.paths or tracked_files()
    return report(scan_paths(paths, rules))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
