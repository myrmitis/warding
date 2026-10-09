#!/usr/bin/env python3
"""check_brand_name.py — gate the retired identity on lines a change adds.

A previous product identity is **retired**,
not misspelled: no system in this tree still owns any of its spellings. The CLI,
the Python package, the environment prefix, the data home, the download and
update hosts, the bundle id, the repository slug and the mascot all moved to
Warding's own (``warding``, ``WARDING_*``, ``~/.warding``,
``warding.dev``, ``dev.warding.desktop``, ``myrmitis/warding``, the
J-and-switch mark). So every rendering of the old identity is residue, in prose
and in identifiers alike, and this gate reports each one:

* the retired two-word product name in any case, with its words glued or
  joined by one joiner: whitespace, ``_``, ``-``, ``.``, ``+``, ``/``, ``\\``
  (escaped or not), a Unicode dash or zero-width character, ``%20``,
  ``&nbsp;``, or a regex spelling of a joiner -- an escape (``\\-``, ``\\s``,
  ``\\W``), a short character class (``[/_]``, ``[\\s_-]``) or a short group
  (``(?:-|_)``), optionally made optional with ``?`` or ``*`` (see
  ``_JOINER``). That one family spans the prose name, the CLI and package
  spellings, the environment prefix, and the retired data home beside
  kiro-cli's directory;
* the retired data home INSIDE kiro-cli's directory, both as one path literal
  (either separator, escaped or not, or a regex class or group of the two) and
  as code builds it: the directory and the second word as two string literals
  joined by a path operator, a comma, a ``+`` or ``joinpath``, or around an
  ``os.sep`` / ``path.sep`` interpolation;
* hosts under the retired product domain (its ``download.``, ``updates.`` and
  ``apps.`` subdomains all carry it), with dots plain, regex-escaped or written
  as ``[.]``;
* the retired Apple bundle id, its dots spelled the same ways;
* the retired GitHub organisation, in any use -- a slug with any repository,
  the container namespace, the ``-labs`` registry, an owner check -- and a slug
  naming the retired product also reports the name;
* the retired ghost mascot's component name.

What the gate leaves alone is kiro-cli, the harness Warding drives: its own
home ``~/.kiro`` and kiro-cli's own directories in it (``~/.kiro/settings``,
``~/.kiro/agents``), ``kiro-cli``, ``Kiro CLI``, ``ACP_BACKEND_KIRO``, the
``kiro.dev`` documentation site. The generic word ``crew`` on its own is not the
retired identity either, and neither are the two words when clause
punctuation (``. ``, ``, ``, ``? ``) separates them.

## No exemptions

Every tracked text file is scanned, ``NOTICE`` included. There is no inline
suppression marker, because the retired identity has no legitimate home and a
marker would let residue opt itself back in.

## Why diff-scoped and not whole-tree

The enforcing check reads only the lines the change *adds* (``BRAND_BASE_REF``),
which is complete for regression: a line can only reach ``main`` through a diff
that added it. Residue that predates the rename never becomes the build break
of whoever pushed next; the whole-tree count is printed instead, as a
non-failing report, so it stays visible until it is gone.

## Usage

    # enforce on what this branch adds (exit 1 on any violation)
    BRAND_BASE_REF=origin/main python3 scripts/check_brand_name.py

    # report the whole-tree residue, enforce nothing (exit 0)
    python3 scripts/check_brand_name.py

    # scan explicit files, ignoring git entirely (exit 1 on any violation)
    python3 scripts/check_brand_name.py README.md docs/foo.md

    # self-test: plant one probe per rule family, assert each verdict
    python3 scripts/check_brand_name.py --test

This file and its tests assemble every retired spelling from fragments, so both
are scanned like any other file and neither carries the identity they hunt.
"""

from __future__ import annotations

import math
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Iterable, Iterator

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Self-test timing budget for the growth-ratio check. It divides two measured
# durations, so it is only as trustworthy as the smaller one: pair each baseline
# with its own doubled sample and keep the least noisy RATIO, then refuse to
# judge one whose baseline is too small to measure. The floor sits above the
# ~15.625ms granularity Windows reports process CPU time at, so a coarse clock
# cannot on its own manufacture a regression.
_PERF_ATTEMPTS = 5
_PERF_MIN_BASE_SECS = 0.020

# Baseline workloads, tried in order until one produces a measurable baseline.
# A single fixed size cannot serve both ends of the hardware range: on a fast
# machine the smallest one lands near the floor above, and a baseline under the
# floor leaves the ratio unjudged -- a check that reports `ok` while testing
# nothing. Growing the workload buys a measurable baseline instead.
#
# Escalating is close to free because a REGRESSED scan never reaches it: its
# baseline is many times the linear one, so it clears the floor at the first
# size and is judged there. Only linear scans -- the fast case -- ever pay for a
# larger size, and a slow runner clears the floor at the first size.
_PERF_BASE_SIZES = (20_000, 50_000, 120_000)

# ---------------------------------------------------------------------------
# The retired identity
# ---------------------------------------------------------------------------

# Fragments. Every retired literal is assembled from these at import time, so
# this file never spells one out and the gate can scan itself.
_KIRO = "kiro"
_CREW = "crew"
_AMZ = "ama" + "zon"
_GHOST = "ghost"
_DEV = "dev"

# What may join the two words of a retired name: nothing, or ONE joiner, which is
# one of
#
# * one or two whitespace characters (a space, a tab, a no-break space, a
#   doubled space);
# * one or two of ``_ + / -``, a Unicode hyphen or dash, a soft hyphen, or a
#   zero-width character. None of these is whitespace, so none can end a
#   sentence;
# * a single ``.``, never followed by anything else. A dot followed by a space
#   is a sentence boundary: a sentence that ends on the harness's name, followed
#   by one that opens with the generic word, names kiro-cli and then a crew, not
#   the retired product;
# * one to four backslashes, optionally followed by one of `` .sSwW_+/-`` (a
#   Windows path, the same path escaped inside a string literal, a
#   shell-escaped space, a Markdown-escaped underscore, a JSON-escaped slash, a
#   regex-escaped joiner, or a regex class such as ``\s`` or ``\W``);
# * ``%20`` (a URL-encoded space) or ``&nbsp;`` (an HTML one);
# * a short regex character class of joiners, such as ``[ -]``, ``[/_]``,
#   ``[\\/]`` or ``[\s_-]``;
# * a short regex group, such as ``(?:-|_)`` or ``(\s|-)``. Its contents are
#   only bounded, not inspected: the name's two words never sit either side of a
#   parenthesised aside with no space between them anywhere but in a pattern;
#
# optionally followed by a regex ``?`` or ``*``, so a pattern written to match
# the name (the name with `` ?`` between its words) is reported as the name too.
# Punctuation that separates clauses (``,``, ``;``, ``!``, ``?`` followed by a
# space) is not a joiner, so two words that merely sit next to each other in
# prose are never joined into the name.
#
# Every part is bounded, and that matters for linearity as much as for
# precision: every alternative in RETIRED below has a fixed maximum length, so
# each start position costs constant work and a scan is linear in the line
# whatever the line holds.
_JOINER = (
    r"(?:\s{1,2}"
    r"|[_+/\-\u2010-\u2015\u00ad\u200b-\u200d\u2060\ufeff]{1,2}"
    r"|\."
    r"|\\{1,4}[ .sSwW_+/\-]?"
    r"|%20|&nbsp;"
    r"|\[[\s_./+\-\\sSwW]{1,6}\]"
    r"|\([^()\n]{1,10}\))"
)
_SEPARATOR = rf"(?:{_JOINER}[?*]?)?"

# A path separator between kiro-cli's directory and the second word of the
# retired data home: one to four slashes or backslashes (either separator,
# escaped for a string literal or a JSON document), or a regex spelling of
# one -- a class such as ``[\\/]`` or ``[/\\]+``, or a group such as
# ``(?:/|\\)``.
_PATH_SEP = r"(?:[/\\]{1,4}|\[[/\\]{1,4}\][+?]?|\((?:\?:)?[/\\|]{1,8}\)[+?]?)"

# A dot inside a retired dotted literal (the hosts, the bundle id): plain, or as
# a pattern spells it -- regex-escaped (with the backslash doubled inside a
# string literal) or as the one-character class ``[.]``. A test that asserts a
# URL against a regex carries the retired host just as much as the URL does.
_DOT = r"(?:\\{0,4}\.|\[\.\])"

# A quote that opens or closes a string literal in Python, JavaScript or shell.
_QUOTE = "[\"'`]"

# The retired data home as code usually BUILDS it rather than spelling it: the
# kiro-cli directory and the second word as two string literals joined by a path
# operator, an argument comma, a ``+``, or ``joinpath(`` -- optionally closing a
# ``Path(...)`` call first -- or as one literal around a ``{os.sep}`` /
# ``${path.sep}`` interpolation. Whitespace runs are bounded like everything else.
_HOME_SPLIT = (
    rf"[/\\]{{0,2}}{_QUOTE}\)?\s{{0,2}}(?:[,/+]|\.joinpath\()\s{{0,2}}"
    rf"[rfb]{{0,2}}{_QUOTE}[/\\]{{0,2}}{_CREW}"
    rf"|\$?\{{(?:os|path)\.sep\}}{_CREW}"
)

# The retired literals, each built from the fragments above, and the patterns
# for the two dotted ones, whose dots may be regex-escaped.
_HOST = f"{_CREW}.{_KIRO}.{_DEV}"
_BUNDLE_ID = ".".join(("com", _AMZ, _KIRO, _CREW))
_ORG = f"{_KIRO}dot{_DEV}"
_HOST_RE = _DOT.join((_CREW, _KIRO, _DEV))
_BUNDLE_RE = _DOT.join(("com", _AMZ, _KIRO, _CREW))

# One alternation, so each span is reported once under the rule that names it
# best. `finditer` takes the leftmost match, which is what orders the rules: the
# bundle id and the data-home path both START before the two-word name they
# contain, so they win over it, and the host starts with the second word, so the
# name rule can never claim it. Case never matters: a retired identifier is
# retired in every case, environment prefix included.
RETIRED = re.compile(
    "|".join(
        (
            f"(?P<bundle>{_BUNDLE_RE})",
            f"(?P<host>{_HOST_RE})",
            f"(?P<org>{_ORG})",
            rf"(?P<home>\.{_KIRO}(?:{_PATH_SEP}{_CREW}|{_HOME_SPLIT}))",
            f"(?P<mascot>{_KIRO}{_SEPARATOR}{_GHOST})",
            f"(?P<brand>{_KIRO}{_SEPARATOR}{_CREW})",
        )
    ),
    re.IGNORECASE,
)

# What each rule's residue becomes. Printed beside every finding, so a
# contributor sees the Warding spelling without opening this file.
REPLACEMENTS: dict[str, str] = {
    "brand": "Warding (prose), warding / WARDING_* (identifiers), ~/.warding (data home)",
    "home": "~/.warding (or $WARDING_HOME)",
    "host": "warding.dev (download., updates., apps.)",
    "bundle": "dev.warding.desktop",
    "org": "myrmitis/warding",
    "mascot": "the Warding mark, generated from assets/brand/build.py",
}

# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------

# Trees that hold no text this repository authors: git's own store, installed
# dependencies, build output, screenshots, and the vendored tree (which AGENTS.md
# excludes from every linter, and whose native libraries carry suffixes -- `.0`,
# `.dylib` -- no extension list will ever fully enumerate). These are not
# exemptions from the identity rule; they are bytes the gate cannot read as text.
SKIP_DIRS = (
    ".git/",
    "node_modules/",
    "website/dist/",
    "website/node_modules/",
    "site/node_modules/",
    "temp-screenshots/",
    "src/warding/_vendor/",
)
SKIP_SUFFIXES = (
    ".lock",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".tiff",
    ".bmp",
    ".ico",
    ".icns",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".mp4",
    ".pdf",
    ".zip",
    ".gz",
)


@dataclass(frozen=True)
class Violation:
    path: str
    line_no: int
    token: str
    text: str
    kind: str = "brand"

    def render(self) -> str:
        replacement = REPLACEMENTS.get(self.kind, REPLACEMENTS["brand"])
        head = f"{self.path}:{self.line_no}: {self.token!r} -> {replacement}"
        return f"{head}\n    {self.text.strip()[:160]}"


def repo_relative(path: str) -> str:
    """``path`` as a forward-slashed path relative to the repository root.

    Explicit arguments may be absolute. A path on another Windows drive has no
    relative form, so it comes back unchanged.
    """
    if os.path.isabs(path):
        try:
            path = os.path.relpath(path, REPO_ROOT)
        except ValueError:
            return path
    return os.path.normpath(path).replace(os.sep, "/")


def in_scope(path: str) -> bool:
    """Is this repo-relative path text the gate reads?"""
    if any(path.startswith(d) for d in SKIP_DIRS):
        return False
    if path.endswith(SKIP_SUFFIXES):
        return False
    return True


# ---------------------------------------------------------------------------
# The scan
# ---------------------------------------------------------------------------


def scan_line(path: str, line_no: int, line: str) -> Iterator[Violation]:
    """Every retired spelling on one line, in order.

    No context narrows a finding: code fences, inline code, URLs and identifiers
    are all scanned, because the identity is retired in every one of them. Each
    violation keeps a reference to the line rather than a slice of it, so a line
    carrying many findings costs time linear in its length.
    """
    for m in RETIRED.finditer(line):
        kind = m.lastgroup or "brand"
        yield Violation(path, line_no, m.group(), line, kind)


def read_lines(path: str) -> list[str] | None:
    """The file's lines as *git* models them, or ``None`` if it cannot be read.

    ``newline=""`` disables universal-newline translation and the split is on
    ``\\n`` alone, which is the only line separator git counts. Translating would
    make a lone ``\\r`` start a new line here but not in the diff, and every line
    number after it would point at the wrong text.
    """
    try:
        with open(os.path.join(REPO_ROOT, path), encoding="utf-8", newline="") as fh:
            return fh.read().split("\n")
    except (OSError, UnicodeDecodeError):
        return None


def scan_lines(path: str, lines: list[str], only_lines: set[int] | None = None) -> list[Violation]:
    found: list[Violation] = []
    for line_no, line in enumerate(lines, start=1):
        if only_lines is not None and line_no not in only_lines:
            continue
        found.extend(scan_line(path, line_no, line))
    return found


def scan_file(path: str, only_lines: set[int] | None = None) -> list[Violation]:
    """Scan one file, optionally restricted to a set of 1-based line numbers.

    Unreadable files report nothing. That is right for the whole-tree *report*,
    which walks everything git tracks; the enforcing paths must not use this for
    a verdict on readability, and call :func:`read_lines` themselves so they can
    fail closed instead.
    """
    lines = read_lines(path)
    if lines is None:
        return []
    return scan_lines(path, lines, only_lines)


# ---------------------------------------------------------------------------
# Git plumbing
# ---------------------------------------------------------------------------


def git(args: list[str]) -> str:
    """Run git and decode its output tolerantly.

    ``errors="replace"`` matters because ``--text`` makes git emit the *content*
    of a file that is not valid UTF-8, and a strict decode would raise inside
    ``subprocess`` — a traceback instead of a verdict. Everything this function's
    callers parse (hunk headers, NUL-separated paths) is ASCII, so a mangled body
    costs nothing. Strictness belongs in :func:`read_lines`, which is where an
    undecodable file becomes a deliberate fail-closed.
    """
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        encoding="utf-8",
        errors="replace",
    ).stdout


def tracked_files() -> list[str]:
    return [p for p in git(["ls-files"]).splitlines() if in_scope(p)]


def diff_base(base: str) -> str:
    """The commit to measure against.

    ``merge-base`` is the honest divergence point, but a shallow CI clone fetches
    the base commit as its own tip with no shared history, so it often has none.
    The base tip is then the fallback.
    """
    try:
        return git(["merge-base", base, "HEAD"]).strip()
    except subprocess.CalledProcessError:
        return base


def changed_paths(frm: str) -> list[str]:
    """In-scope paths this change touches.

    ``-z`` is what makes this trustworthy: without it git quotes any path holding
    a non-ASCII or unusual byte (``"b/docs/\\346\\227\\245.md"``), and a parser
    reading ``+++ b/`` lines then silently drops that file — a gate that skips a
    changed file is worse than no gate.
    """
    try:
        out = git(["diff", "--name-only", "-z", "--diff-filter=d", frm])
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"::error::brand gate: cannot diff against {frm} — the base commit is not "
            f"present. Fetch it before running, or unset BRAND_BASE_REF to report "
            f"whole-tree counts without enforcing.\n{exc.stderr}"
        )
    return [p for p in out.split("\0") if p and in_scope(p)]


def added_lines(frm: str, path: str) -> set[int]:
    """1-based line numbers this change adds to ``path``.

    The diff runs base-to-**working-tree**. CI checks out a clean tree, so that is
    the same as base-to-``HEAD`` there; locally it means the gate sees edits that
    are not committed yet, which is the only form in which a local run is useful.
    A brand-new *untracked* file is the one gap, and it is caught on the commit
    that tracks it.

    ``--text`` forces hunks even for a path that ``.gitattributes`` marks
    ``-diff``: git would otherwise report only "Binary files differ", leaving
    nothing to scan and passing the file silently. ``in_scope`` has already
    dropped the genuinely binary suffixes.
    """
    diff = git(["diff", "--unified=0", "--no-color", "--text", frm, "--", path])
    added: set[int] = set()
    for raw in diff.splitlines():
        if not raw.startswith("@@"):
            continue
        # `@@ -old,count +new,count @@` — the `+` side is the post-image, and a
        # missing count means exactly one line. A pure deletion reports `+n,0`,
        # which correctly contributes nothing.
        m = re.search(r"\+(\d+)(?:,(\d+))?", raw)
        if not m:
            continue
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) is not None else 1
        added.update(range(start, start + count))
    return added


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

# Probe spellings, assembled from the fragments like everything else here.
_KIRO_CAP = _KIRO.capitalize()
_CREW_CAP = _CREW.capitalize()
_NAME = _KIRO_CAP + _CREW_CAP
_NAME_SPACED = f"{_KIRO_CAP} {_CREW_CAP}"
_MASCOT = _KIRO_CAP + _GHOST.capitalize()
# The dotted literals as a pattern spells them: dots regex-escaped once, escaped
# again inside a string literal, or written as a one-character class.
_BS = "\\"
_HOST_ESC = _HOST.replace(".", _BS + ".")
_HOST_ESC2 = _HOST.replace(".", _BS * 2 + ".")
_HOST_CLASS = _HOST.replace(".", "[.]")
_BUNDLE_ESC = _BUNDLE_ID.replace(".", _BS + ".")

# (label, line, expected kinds in order). An empty tuple means "must not flag".
PROBES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("prose-joined", f"Run {_NAME} on your laptop.", ("brand",)),
    ("prose-spaced", f"{_NAME_SPACED} keeps working while you sleep.", ("brand",)),
    ("prose-lower", f"install {_NAME_SPACED.lower()} first", ("brand",)),
    ("en-dash", f"the {_KIRO_CAP}\u2013{_CREW_CAP} desktop app", ("brand",)),
    ("zero-width", f"{_KIRO}\u200b{_CREW} hides a joiner", ("brand",)),
    ("url-encoded", f"https://example.com/?q={_KIRO_CAP}%20{_CREW_CAP}", ("brand",)),
    ("regex-optional", f"title.replace(/^{_KIRO_CAP} ?{_CREW_CAP} /g, '')", ("brand",)),
    ("regex-class", f"re.compile(r'{_KIRO}[ -]?{_CREW}')", ("brand",)),
    ("regex-class-slash", f"re.compile(r'{_KIRO}[/_]{_CREW}')", ("brand",)),
    ("regex-class-escape", f"re.compile(r'{_KIRO}[\\s_-]?{_CREW}')", ("brand",)),
    ("regex-group", f"re.compile(r'{_KIRO}(?:-|_)?{_CREW}')", ("brand",)),
    ("regex-nonword", f"re.compile(r'{_KIRO}\\W?{_CREW}')", ("brand",)),
    ("regex-escaped-hyphen", f"/{_KIRO}\\-{_CREW}/", ("brand",)),
    ("markdown-escaped", f"the `{_KIRO}\\_{_CREW}` package", ("brand",)),
    ("json-escaped-slash", f'{{"p": "{_KIRO}\\/{_CREW}"}}', ("brand",)),
    ("shell-escaped", f"open /Applications/{_KIRO_CAP}\\ {_CREW_CAP}.app", ("brand",)),
    ("cli", f"run `{_KIRO}{_CREW} serve` to start it", ("brand",)),
    ("package", f"from {_KIRO}_{_CREW}.config import loader", ("brand",)),
    ("hyphenated", f"mailto:{_KIRO}-{_CREW}-support@example.com", ("brand",)),
    ("env-var", f'os.environ["{(_KIRO + _CREW).upper()}_HOME"]', ("brand",)),
    ("glued-identifier", f"resolve {_NAME}Apps from the registry", ("brand",)),
    ("artifact", f"signs {_NAME}.exe and {_NAME}-x86_64.AppImage", ("brand", "brand")),
    ("home-posix", f"state lives under ~/.{_KIRO}/{_CREW}/workspace", ("home",)),
    ("home-windows", f"C:\\Users\\me\\.{_KIRO}\\{_CREW}\\gateway.sock", ("home",)),
    ("home-escaped", f'"C:\\\\Users\\\\me\\\\.{_KIRO}\\\\{_CREW}"', ("home",)),
    ("home-joined", f"migrated from ~/.{_KIRO}{_CREW}", ("brand",)),
    ("home-path-operator", f'Path.home() / ".{_KIRO}" / "{_CREW}"', ("home",)),
    ("home-join-args", f'os.path.join(home, ".{_KIRO}", "{_CREW}")', ("home",)),
    ("home-tuple", f'parts = (".{_KIRO}", "{_CREW}")', ("home",)),
    ("home-closed-call", f'Path(".{_KIRO}") / "{_CREW}-auth-staging"', ("home",)),
    ("home-os-sep", f'f".{_KIRO}{{os.sep}}{_CREW}"', ("home",)),
    ("home-regex-class", f"re.compile(r'\\.{_KIRO}[\\\\/]{_CREW}')", ("home",)),
    ("home-regex-group", f"re.compile(r'\\.{_KIRO}(?:/|\\\\)+{_CREW}')", ("home",)),
    ("home-json-escaped", f'{{"home": "~\\/.{_KIRO}\\/{_CREW}"}}', ("home",)),
    ("host", f"curl -fsSL https://download.{_HOST}/cli.sh | sh", ("host",)),
    ("host-regex", f"assert.match(url, /^https:\\/\\/download\\.{_HOST_ESC}\\//)", ("host",)),
    ("host-regex-string", f'new RegExp("apps\\\\.{_HOST_ESC2}")', ("host",)),
    ("host-regex-class", f"apps[.]{_HOST_CLASS}", ("host",)),
    ("bundle-id", f"codesign --identifier {_BUNDLE_ID}", ("bundle",)),
    ("bundle-id-regex", f"/^{_BUNDLE_ESC}$/", ("bundle",)),
    ("slug", f"https://github.com/{_ORG}/{_NAME}/issues", ("org", "brand")),
    ("org", f"ghcr.io/{_ORG}/warding:latest", ("org",)),
    ("org-labs", f"registry: '{_ORG}-labs'", ("org",)),
    ("org-other-repo", f"{{ owner: '{_ORG}', repo: 'warding' }}", ("org",)),
    ("mascot", f'import {_MASCOT} from "./{_MASCOT}"', ("mascot", "mascot")),
    ("no-marker", f"x = '{_NAME}'  # brand-ok", ("brand",)),
    ("kiro-home", "kiro-cli reads ~/.kiro/settings/cli.json and ~/.kiro/agents/", ()),
    ("kiro-home-built", 'Path.home() / ".kiro" / "settings" / "cli.json"', ()),
    ("kiro-cli", "install kiro-cli, the Kiro CLI, as ACP_BACKEND_KIRO", ()),
    ("kiro-docs", "see https://kiro.dev/docs/cli for the harness", ()),
    ("kiro-docs-regex", "assert re.match(r'https://kiro\\.dev/docs', url)", ()),
    ("kiro-home-regex", "re.compile(r'\\.kiro[\\\\/](?:settings|agents)')", ()),
    ("aside", f"{_KIRO_CAP} (the harness) and its {_CREW}", ()),
    ("org-first-word-slug", f"fix requested in {_ORG}/{_KIRO_CAP}#10970", ("org",)),
    ("org-first-word-url", f"https://github.com/{_ORG}/{_KIRO_CAP}/issues/11", ("org",)),
    ("org-first-word-pair", f"{{ owner: '{_ORG}', repo: '{_KIRO_CAP}' }}", ("org",)),
    ("crew-alone", "a remote crew runs the crew_companion app (STAGE_CREW_LEAF)", ()),
    ("apart", "kiro-cli drives the agent crew", ()),
    ("sentence-boundary", f"The harness is {_KIRO_CAP}. {_CREW_CAP} agents pick it up.", ()),
    ("clause-comma", f"{_KIRO_CAP}, {_CREW} and more", ()),
    ("clause-question", f"Is it {_KIRO}? {_CREW_CAP} members decide.", ()),
    ("warding", "Warding routes agents; run `warding gateway`", ()),
)


def self_test() -> int:
    failures = 0
    for label, line, want in PROBES:
        got = tuple(v.kind for v in scan_line("probe.py", 1, line))
        if got != want:
            print(f"  FAIL {label}: expected {list(want)}, got {list(got)} — {line}")
            failures += 1
        else:
            print(f"  ok   {label}")

    # No path is exempt: the root NOTICE is read like any other file.
    scope = (in_scope("NOTICE"), in_scope("docs/NOTICE"), in_scope("NOTICE.md"))
    if scope != (True, True, True):
        print(f"  FAIL no-exemption: in_scope(NOTICE, docs/NOTICE, NOTICE.md) = {scope}")
        failures += 1
    else:
        print("  ok   no-exemption")

    # A generated file can carry one very long line. The scan has to stay linear
    # in its length, or the job times out on input a contributor cannot see is
    # pathological. Each filler is a run of near-misses for one of the rules, so
    # a pattern that grew an unbounded quantifier re-walks the run from every
    # offset.
    start = time.monotonic()
    fillers = (
        (".", " "),
        ("a-", " "),
        ("x.com", " "),
        (f"{_KIRO} ", " "),
        (f"{_KIRO}-cli ", ""),
        (f"~/.{_KIRO}/", " "),
        (f'.{_KIRO}" / "', " "),
        (f"{_KIRO}%20", " "),
        (f"{_KIRO}\\\\", " "),
        (f"{_KIRO}[ -]", " "),
        (f"{_KIRO}[\\s_", " "),
        (f"{_KIRO}(?:-", " "),
        (f".{_KIRO}[\\\\/]", " "),
        (f"{_CREW}\\.{_KIRO}\\.x", " "),
        ("\\", " "),
        ("`", " "),
    )
    for filler, glue in fillers:
        long_line = filler * (200_000 // len(filler)) + glue + _NAME
        if [v.token for v in scan_line("big.md", 1, long_line)] != [_NAME]:
            print(f"  FAIL linearity: missed the name after a {filler!r} run")
            failures += 1
    elapsed = time.monotonic() - start
    if elapsed > 2.0:
        print(
            f"  FAIL linearity: {len(fillers)} x 200k-char lines took {elapsed:.1f}s "
            "(expected < 2s)"
        )
        failures += 1
    else:
        print(f"  ok   linearity ({elapsed:.2f}s for {len(fillers)} x 200k chars)")

    # Many findings in ONE whitespace-free run. This is the shape that goes
    # quadratic the moment any per-match step slices the line or rescans its
    # prefix. The assertion is on the GROWTH RATIO, not a wall-clock budget: an
    # absolute threshold generous enough for a loaded CI runner is also generous
    # enough to let a quadratic implementation pass at this size.
    #
    # Measuring a ratio puts the whole burden on the timer, so it measures CPU
    # time, which does not advance while the thread is off-CPU. Wall clock does
    # not work: `time.monotonic()` is `GetTickCount64()` on Windows, a ~15.625ms
    # tick that quantises a short sample by a large fraction of itself, and when
    # xdist workers oversubscribe the runner the LONGER scan absorbs more
    # preemption than the shorter one, which inflates the ratio systematically.
    # Pairing each baseline with its own doubled sample keeps the two halves of a
    # ratio from the same conditions. Under 2x CPU oversubscription a linear scan
    # stays at most ~2x while a quadratic one never drops below ~3.9x, so the 3.0x
    # bound keeps the check's teeth. `process_time` is also coarse on Windows, so
    # the floor still applies.
    def ratio_of(base: int) -> tuple[float, float, int, int]:
        """Best (least noisy) doubled/base CPU-time ratio over several attempts."""
        best = math.inf
        best_pair = (0.0, 0.0)
        found: tuple[int, int] = (0, 0)

        def once(count: int) -> tuple[float, int]:
            began = time.process_time()
            hits = len(list(scan_line("big.md", 1, f"!{_NAME}" * count)))
            return time.process_time() - began, hits

        for _ in range(_PERF_ATTEMPTS):
            base_time, base_hits = once(base)
            doubled_time, doubled_hits = once(base * 2)
            found = (base_hits, doubled_hits)
            if base_time <= 0.0:
                continue
            candidate = doubled_time / base_time
            if candidate < best:
                best, best_pair = candidate, (base_time, doubled_time)
        return (0.0 if best is math.inf else best), best_pair[0], found[0], found[1]

    # Grow the workload until the baseline is big enough to divide. `ratio_of`
    # is only called again when the previous size came in under the floor, so
    # the common cases cost exactly one call.
    base_count = 0
    ratio = base_time = 0.0
    base_found = doubled_found = 0
    for base_count in _PERF_BASE_SIZES:
        ratio, base_time, base_found, doubled_found = ratio_of(base_count)
        if base_time >= _PERF_MIN_BASE_SECS:
            break

    if (base_found, doubled_found) != (base_count, base_count * 2):
        print(
            f"  FAIL repeated-names: found {base_found}/{doubled_found}, "
            f"want {base_count}/{base_count * 2}"
        )
        failures += 1
    elif base_time < _PERF_MIN_BASE_SECS:
        # Even the largest workload was too fast to measure. Quadratic growth at
        # that size costs orders of magnitude more than the floor, so this cannot
        # be hiding a regression -- report the fact rather than dividing noise by
        # noise.
        print(
            f"  ok   repeated-names (baseline {base_time * 1000:.1f}ms at {base_count} "
            f"names still below the {_PERF_MIN_BASE_SECS * 1000:.0f}ms measurement "
            f"floor; ratio not judged)"
        )
    elif ratio > 3.0:
        print(
            f"  FAIL repeated-names: doubling the input cost {ratio:.1f}x CPU time "
            f"(best of {_PERF_ATTEMPTS}, baseline {base_time:.3f}s at {base_count} "
            f"names); linear is ~2x, so a per-match scan of the line has come back"
        )
        failures += 1
    else:
        print(
            f"  ok   repeated-names (doubling cost {ratio:.1f}x at {base_count} " f"names, linear)"
        )

    print("self-test passed" if not failures else f"self-test FAILED ({failures})")
    return 1 if failures else 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def report(violations: Iterable[Violation], *, enforcing: bool, base: str | None) -> int:
    violations = list(violations)
    if not violations:
        if not enforcing:
            scope = "whole tree"
        elif base:
            scope = f"lines added since {base}"
        else:
            scope = "files given"
        print(f"brand gate: no retired identity in the {scope} ✓")
        return 0

    if enforcing:
        print(
            f"::error::brand gate: {len(violations)} retired identity "
            f"spelling(s) on lines this change adds. The retired product's name, "
            f"data homes, hosts, bundle id, organisation and mascot are retired in "
            f"every spelling and every context; use Warding's own instead."
        )
    else:
        print(
            f"::notice::brand gate report: {len(violations)} pre-existing retired "
            f"identity spelling(s). Not enforced here; only lines a change "
            f"adds are gated."
        )
    # The listing is path-sorted, so a silently-truncated report shows only the
    # alphabetically-first paths, and a backlog under 'src/' and 'website/' can
    # hide behind '.github/' alone. Always disclose the cut, and on the report
    # path precede the listing with a per-directory tally so the shape of the
    # backlog survives truncation.
    shown = 200 if enforcing else 40
    if not enforcing and len(violations) > shown:
        tally: dict[str, int] = {}
        for v in violations:
            head, _, tail = v.path.partition("/")
            tally[f"{head}/" if tail else head] = tally.get(f"{head}/" if tail else head, 0) + 1
        print(f"\nby top-level path ({len(tally)} entries, all {len(violations)} lines):")
        for name, count in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {count:>5}  {name}")
        print()

    for v in violations[:shown]:
        print(v.render())
    if len(violations) > shown:
        print(f"... and {len(violations) - shown} more")
    if enforcing:
        print(
            "\nThere is no inline suppression and no exempt file. kiro-cli's own "
            "spellings (~/.kiro and its settings/ and agents/ directories, kiro-cli, "
            "Kiro CLI, kiro.dev) and the word "
            "'crew' on its own are not the retired identity and are not flagged. To name "
            "the retired identity in a test or a gate, build it from fragments."
        )
    return 1 if enforcing else 0


def enforce_diff(base: str) -> int:
    """Enforce on the lines this change adds. Fails closed on anything unreadable."""
    frm = diff_base(base)
    found: list[Violation] = []
    unreadable: list[str] = []
    for path in changed_paths(frm):
        lines = added_lines(frm, path)
        if not lines:
            continue
        content = read_lines(path)
        if content is None:
            unreadable.append(path)
            continue
        found.extend(scan_lines(path, content, lines))

    if unreadable:
        # Reporting nothing for a file the change actually touched is how a gate
        # quietly stops gating, so refuse to pass instead of skipping.
        print(
            "::error::brand gate: cannot read these changed files as UTF-8 text, so "
            "the retired identity in them was never checked. Either make them "
            "decodable or add their suffix to SKIP_SUFFIXES in scripts/check_brand_name.py:"
        )
        for path in unreadable:
            print(f"  {path}")
        return 1

    return report(found, enforcing=True, base=base)


def force_utf8_output() -> None:
    """Print UTF-8 whatever the console's default encoding is.

    Both halves of this gate's output carry non-ASCII: a violation can name a
    non-ASCII path, and the clean verdict ends in a check mark. Windows consoles
    default to cp1252, which raises ``UnicodeEncodeError`` on either — turning a
    PASS into a traceback and failing the build on a tree that was fine.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str]) -> int:
    force_utf8_output()
    if "--test" in argv:
        return self_test()

    explicit = [a for a in argv if not a.startswith("-")]
    if explicit:
        # Same fail-closed rule as enforce_diff: a path that yields no lines has
        # not been checked, so reporting it clean is a false green. Without this,
        # a typo'd or moved path prints the success line and exits 0.
        unreadable = [p for p in explicit if read_lines(p) is None]
        if unreadable:
            print(
                "::error::brand gate: cannot read these paths as UTF-8 text, so the "
                "retired identity in them was never checked:"
            )
            for path in unreadable:
                print(f"  {path}")
            return 1
        found = [v for p in explicit for v in scan_file(p)]
        return report(found, enforcing=True, base=None)

    base = os.environ.get("BRAND_BASE_REF", "").strip()
    if base:
        return enforce_diff(base)

    found = [v for path in tracked_files() for v in scan_file(path)]
    return report(found, enforcing=False, base=None)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
