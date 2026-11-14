"""One canonical path identity for the gates that match paths.

Three gates ask what a path argument names: the sensitive-path keystone in
``security``, the path matcher in ``platform.governance``, and the PreToolUse gate
in ``hooks``. Each used to normalize on its own, so each had its own gaps. This
module holds the two primitives they share.

``canonical_path_forms(path, base)`` returns every spelling of *path* that a deny
check must test. ``iter_target_paths(params)`` returns every path a tool call
names, at any depth of its arguments.

The forms are for MATCHING ONLY. A form is an extra deny candidate. It never
becomes a path that an operation opens, reads or writes. A caller that tests a
form against an allow list must not use the folded forms: they can only widen a
match, and widening is safe for a deny and unsafe for an allow.

This module imports only ``path_spellings`` from the package, so ``hooks``,
``security`` and ``platform.governance`` (which cannot import each other) can all
use it.
"""

from __future__ import annotations

import ntpath
import os
import re
import sys
from collections.abc import Callable, Iterable, Iterator, Mapping

from warding.path_spellings import MAX_TARGET_PATHS, PATH_LIMIT_SENTINEL, path_spellings

# ── Tool-argument walker ───────────────────────────────────────────────────

#: Argument names a tool may carry ONE target path under. The gate, the governance
#: gate and the consent prompt all read them through ``iter_target_paths``, so a
#: prompt cannot disclose a path the gate did not inspect.
#:
#: Rename-shaped keys (``old_path``, ``new_path``, ``src``, ``dest``) are NOT read.
#: Names such as ``src`` and ``dest`` often hold URLs or addresses, and the same set
#: feeds governance allow-mode ceilings, so reading them would deny ordinary calls.
TARGET_PATH_KEYS: tuple[str, ...] = ("path", "file_path", "filePath")

#: Argument names whose value is a LIST of target paths (a multi-file patch, a
#: batched read). A bare string under one of these keys is not a path list, so it is
#: not read as a path. A list under any key of either tuple holds paths.
TARGET_PATH_LIST_KEYS: tuple[str, ...] = ("paths",)

#: Container nodes the walker visits before it fails closed. A real call has a few
#: dozen. The bound keeps an attacker-shaped payload from stalling the gateway's
#: event loop, and it ends a self-referencing container.
MAX_TARGET_NODES = 10_000

#: Nesting depth the walker follows before it fails closed. A real tool schema nests
#: a path two or three levels down.
MAX_TARGET_DEPTH = 64

_PATH_BEARING_KEYS = frozenset(TARGET_PATH_KEYS + TARGET_PATH_LIST_KEYS)


def iter_target_paths(params: object) -> Iterator[str]:
    """Yield every path a tool call names, at any depth of its arguments.

    A string under one of ``TARGET_PATH_KEYS`` is a path wherever it sits: at the
    top, inside a list of operations, or inside an object inside a list. A list under
    any key of ``TARGET_PATH_KEYS`` or ``TARGET_PATH_LIST_KEYS`` holds paths
    directly. Every container is walked. The walk is iterative, so no
    ``RecursionError`` can reach the gate. Order of first appearance is kept and
    duplicates collapse.

    A value a harness would trim (``path_spellings``) yields the trimmed path as
    well, because the harness opens that one.

    The walk FAILS CLOSED, and it bounds only what can carry a path. It yields
    ``PATH_LIMIT_SENTINEL`` and stops when:

    * a path-bearing list is longer than ``MAX_TARGET_PATHS`` (it is never iterated);
    * more than ``MAX_TARGET_PATHS`` distinct paths turn up;
    * more than ``MAX_TARGET_NODES`` containers that can carry a path turn up;
    * nesting is deeper than ``MAX_TARGET_DEPTH``.

    A container that cannot carry a path is not counted. That covers a long list of
    numbers (an embedding), a list of plain strings under another key, and a
    mapping with no path key and no container inside. So a large ordinary argument
    passes. The sentinel is longer than any path, so the gate that checks
    ``exceeds_path_limits`` denies the call.

    The function extracts only. It makes no decision about a path.
    """
    if not isinstance(params, Mapping):
        return
    seen: set[str] = set()
    nodes = 0
    # Each entry: (node, depth, whether strings directly in it are paths).
    stack: list[tuple[object, int, bool]] = [(params, 0, False)]
    children: list[tuple[object, bool]]
    while stack:
        node, depth, bearing = stack.pop()
        if depth > MAX_TARGET_DEPTH:
            yield PATH_LIMIT_SENTINEL
            return
        if isinstance(node, str):
            if bearing:
                for spelling in _new_spellings(node, seen):
                    if len(seen) > MAX_TARGET_PATHS:
                        yield PATH_LIMIT_SENTINEL
                        return
                    yield spelling
            continue
        if isinstance(node, Mapping):
            carries = False
            for key in TARGET_PATH_KEYS:
                value = node.get(key)
                if isinstance(value, str):
                    carries = True
                    # Direct path values first, in the documented key order, so the
                    # first path a caller shows a human is the call's primary target.
                    for spelling in _new_spellings(value, seen):
                        if len(seen) > MAX_TARGET_PATHS:
                            yield PATH_LIMIT_SENTINEL
                            return
                        yield spelling
            children = [
                (value, key in _PATH_BEARING_KEYS)
                for key, value in node.items()
                if isinstance(value, (Mapping, list, tuple))
            ]
            if not (carries or children):
                continue
        elif isinstance(node, (list, tuple)):
            if bearing and len(node) > MAX_TARGET_PATHS:
                yield PATH_LIMIT_SENTINEL
                return
            children = [
                (child, bearing)
                for child in node
                if isinstance(child, (Mapping, list, tuple)) or (bearing and isinstance(child, str))
            ]
            if not children:
                continue
        else:
            continue
        nodes += 1
        if nodes > MAX_TARGET_NODES:
            yield PATH_LIMIT_SENTINEL
            return
        stack.extend((child, depth + 1, flag) for child, flag in reversed(children))


def _new_spellings(value: str, seen: set[str]) -> list[str]:
    """The spellings of *value* not yet seen, recorded in *seen*."""
    fresh: list[str] = []
    if value.strip():
        for spelling in path_spellings(value):
            if spelling not in seen:
                seen.add(spelling)
                fresh.append(spelling)
    return fresh


# ── Canonical forms ────────────────────────────────────────────────────────

#: Whether the host's default filesystem folds case. Windows and macOS default
#: volumes do. A module constant so a test on another platform can read a path the
#: way such a host does.
CASE_INSENSITIVE_HOST = sys.platform in ("win32", "darwin")

#: ``\\?\`` (extended-length), ``\\.\`` (device) and ``\??\`` (NT object) prefixes.
#: Win32 reads ``/`` as ``\`` in the first two.
_NAMESPACE_PREFIX_RE = re.compile(r"[\\/]{2}[?.][\\/]|\\\?\?\\")
_TWO_SEPARATORS_RE = re.compile(r"[\\/]{2}")
_DRIVE_RE = re.compile(r"[A-Za-z]:(?:\\|$)")
#: A loopback host and a drive-letter administrative share: ``\\localhost\C$\...``.
#: The whole share component must be one ASCII drive letter and ``$``. The head is
#: validated here, before any normalization can repair a malformed one.
_LOOPBACK_SHARE_RE = re.compile(
    r"\\\\(?:localhost|127\.0\.0\.1)\\([A-Za-z])\$(?:\\(.*))?",
    re.IGNORECASE | re.ASCII | re.DOTALL,
)
#: A path that is Windows-shaped: a drive, a UNC or device head, or an NT object head.
_WINDOWS_SHAPE_RE = re.compile(r"[A-Za-z]:(?:[\\/]|$)|[\\/]{2}[^\\/]|\\\?\?\\")
_SEPARATOR_RUN_RE = re.compile(r"([\\/]+)")

# The fold is a fixpoint over a few steps. A path needs at most four (a device
# prefix, a UNC head, a loopback share, a stream suffix); the bound ends any loop.
_MAX_FOLD_FORMS = 32


def expand_path(path: str) -> str:
    """Expand ``~`` and ``$VAR`` without touching the filesystem."""
    return os.path.expanduser(os.path.expandvars(path))


def is_windows_shaped(path: str) -> bool:
    """Whether *path* is spelled as a Windows drive, UNC, device or NT-object path."""
    return _WINDOWS_SHAPE_RE.match(path) is not None


def split_namespace_prefix(path: str) -> tuple[str, bool] | None:
    """Split a Win32 namespace-prefixed *path* into its plain remainder and a UNC flag.

    Reads the three prefixes that name a local object: ``\\\\?\\`` (extended-length),
    ``\\\\.\\`` (device) and ``\\??\\`` (NT object). ``None`` when *path* has none.
    ``\\\\?\\C:\\x`` gives ``("C:\\x", False)``. ``\\\\?\\UNC\\host\\share`` gives
    ``("\\\\host\\share", True)``: the flag marks a UNC head. For matching only: Win32
    rewrites some plain spellings, such as a name that ends in a dot or a space, so
    the plain spelling can name a different file.
    """
    prefix = _NAMESPACE_PREFIX_RE.match(path)
    if prefix is None:
        return None
    rest = path[prefix.end() :]
    if rest[:4].upper() in ("UNC\\", "UNC/"):
        return "\\\\" + rest[4:], True
    return rest, False


def lexical_path(path: str, base: str | None = None) -> str:
    """*path* expanded, absolutized and lexically collapsed: the one plain form.

    1. ``expand_path``: ``~`` and ``$VAR``.
    2. Anchor a relative path against *base*, or the process working directory
       when *base* is ``None``. ``abspath`` also runs ``normpath``.
    3. Collapse a leading ``//`` to ``/``. POSIX leaves exactly two leading slashes
       implementation-defined, ``normpath`` keeps them, and the OS opens the
       single-slash path, so an item spelled ``//etc/passwd`` would miss a
       ``/etc/**`` deny.

    Purely lexical: no filesystem access, no symlink resolution. This is the form
    an allow list is matched against, because it adds no spelling.
    """
    expanded = expand_path(path)
    if base and not os.path.isabs(expanded):
        expanded = os.path.join(os.path.abspath(base), expanded)
    result = os.path.abspath(expanded)
    if result.startswith("//") and not result.startswith("///"):
        result = result[1:]
    return result


def canonical_path_forms(
    path: str,
    base: str | None = None,
    *,
    resolve: Callable[[str], Iterable[str]] | None = None,
) -> set[str]:
    """Every spelling of *path* that a deny check must test. For matching only.

    The set holds, for the expanded input (``~``, ``$VAR``, and *base* anchoring
    for a relative path) and for the raw input:

    * the spelling as written, and its lexical normalization;
    * the Windows extended-length (``\\\\?\\``), device (``\\\\.\\``) and NT-object
      (``\\??\\``) spellings of a local drive, folded to the plain drive path, and
      the ``UNC`` forms of each folded to the plain UNC path;
    * a loopback administrative share (``\\\\localhost\\C$\\x`` and
      ``\\\\127.0.0.1\\C$\\x``) folded to the local drive path ``C:\\x``;
    * a path with its alternate-data-stream suffixes removed (``f::$DATA``,
      ``d::$INDEX_ALLOCATION``, ``f:stream``).

    The fold is platform-independent, so a Windows spelling is recognized on every
    host. The forms are extra DENY candidates. They never become a path that an
    operation uses. A form can only widen a match, so it belongs in a deny test and
    not in an allow test. Case is NOT folded here: ``CASE_INSENSITIVE_HOST`` and
    ``is_windows_shaped`` tell a caller when to fold it.

    *resolve* lets a caller that may touch the filesystem add resolved forms. It is
    called once per lexical form and returns that form's symlink-resolved
    spellings. Each resolved spelling is folded too, because Windows ``realpath``
    keeps a prefix the input carried. A caller that must stay lexical, such as the
    governance matcher, passes nothing.
    """
    expanded = expand_path(path)
    anchored = expanded
    if base and not os.path.isabs(anchored):
        anchored = os.path.join(os.path.abspath(base), anchored)
    seeds = [anchored, lexical_path(path, base)]
    # A Windows-shaped input is not absolute on POSIX, so anchoring would bury it
    # under *base*. Keep its own spelling as a seed as well.
    for raw in (expanded, path):
        if raw not in seeds and is_windows_shaped(raw.replace("/", "\\")):
            seeds.append(raw)

    lexical: set[str] = set()
    for seed in seeds:
        lexical |= _fold_forms(seed)
    forms = set(lexical)
    if resolve is not None:
        for form in lexical:
            for resolved in resolve(form):
                forms |= _fold_forms(resolved)
    return forms


def _fold_forms(path: str) -> set[str]:
    """*path*, every alias spelling it folds to, and the normalization of each."""
    forms = {path}
    pending = [path]
    while pending and len(forms) < _MAX_FOLD_FORMS:
        current = pending.pop()
        folded, terminal = _fold_step(current)
        forms |= terminal
        for form in folded:
            if form not in forms:
                forms.add(form)
                pending.append(form)
    for form in list(forms):
        forms.add(_normpath(form))
    return forms


def _normpath(path: str) -> str:
    """Lexical normalization in the path's own flavor: Windows-shaped or native."""
    return ntpath.normpath(path) if is_windows_shaped(path) else os.path.normpath(path)


def _fold_step(path: str) -> tuple[set[str], set[str]]:
    """The spellings one fold step derives from *path*. Never touches the filesystem.

    Returns ``(folded, terminal)``. A folded spelling is folded again by the next
    step. A terminal spelling is a candidate only: it is never read as a UNC head,
    because it comes from a prefix followed by a second root, and stripping that
    prefix would repair an excluded namespace into a UNC path.
    """
    folded: set[str] = set()
    terminal: set[str] = set()
    # ``/`` and ``\`` name the same separator to Win32. Read the head that way.
    spelled = path.replace("/", "\\")
    if not is_windows_shaped(spelled):
        return folded, terminal
    if spelled != path:
        folded.add(spelled)
    # A UNC head that the loopback rule may read: the input's own, or one made by
    # ``UNC\`` after a namespace prefix.
    unc: str | None = None if _NAMESPACE_PREFIX_RE.match(path) else spelled
    split = split_namespace_prefix(path)
    if split is not None:
        rest, is_unc = split
        if is_unc:
            unc = rest
            folded.add(rest)
        elif _TWO_SEPARATORS_RE.match(rest):
            terminal.add(rest)
        elif _DRIVE_RE.match(rest.replace("/", "\\")):
            # A bare volume (``\\.\C:``) is the drive root.
            folded.add(rest if len(rest) > 2 else rest + "\\")
        elif path.startswith(("\\\\?\\", "//?/")):
            # An extended-length prefix on a non-drive name, such as a volume GUID,
            # or on a POSIX-style path: one more fail-safe candidate.
            terminal.add(rest)
    if unc is not None and unc.startswith("\\\\"):
        local = _loopback_drive_form(unc)
        if local is not None:
            folded.add(local)
    for candidate in {path, spelled, *folded}:
        stripped = _without_streams(candidate)
        if stripped != candidate:
            folded.add(stripped)
    folded.discard(path)
    return folded, terminal


def _loopback_drive_form(unc: str) -> str | None:
    """The local drive path a loopback administrative share names, or ``None``.

    ``\\\\localhost\\C$\\Users\\x`` gives ``C:\\Users\\x``. A bare share root gives the
    drive root. A remote host, a hostname lookalike, an IPv6 or other loopback
    alias, a machine-name alias and a share that is not one drive letter and ``$``
    give nothing. No lookup runs: this reads the spelling only.
    """
    match = _LOOPBACK_SHARE_RE.fullmatch(unc)
    if match is None:
        return None
    return ntpath.normpath(match[1] + ":\\" + (match[2] or ""))


def _without_streams(path: str) -> str:
    """*path* with the stream suffix of each component removed, when Windows-shaped.

    ``file::$DATA`` is the plain file. ``dir::$INDEX_ALLOCATION`` is the plain
    directory. ``file:stream`` names an alternate stream of the same file.
    """
    spelled = path.replace("/", "\\")
    # A namespace prefix holds a drive colon of its own. The fold strips the prefix
    # first, and the stream strip then reads the plain form.
    if not is_windows_shaped(spelled) or _NAMESPACE_PREFIX_RE.match(path):
        return path
    drive, tail = ntpath.splitdrive(path)
    if ":" not in tail:
        return path
    parts = _SEPARATOR_RUN_RE.split(tail)
    for index in range(0, len(parts), 2):
        name = parts[index]
        base = name.split(":", 1)[0]
        if base:
            parts[index] = base
    return drive + "".join(parts)


def casefold_match_needed(form: str) -> bool:
    """Whether a deny comparison of *form* must ignore case.

    True on a host whose default filesystem folds case, and for any Windows-shaped
    form. Only a deny folds case: a directory can be case sensitive, so folding in
    an allow could admit a sibling the operator did not name, while folding in a
    deny refuses at most an extra name.
    """
    return CASE_INSENSITIVE_HOST or is_windows_shaped(form)
