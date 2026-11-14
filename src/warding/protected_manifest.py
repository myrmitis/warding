"""The manifest of protected leaves under Warding's data home.

This module is the single place that says which files and directories under the
data home an agent must not read or rewrite. Three layers read it:

* the tool gate in ``security.py`` (``is_sensitive_path`` and the shell matchers),
* the OS sandbox in ``sandbox.py`` (macOS seatbelt profile and Linux launcher),
* the posture report in ``security_posture.py``.

Each layer derives its list from :data:`LEAVES`. Nobody keeps a second list by
hand. To protect a new leaf, add one :class:`ProtectedLeaf` row here. The test in
``test/test_protected_manifest.py`` fails when a layer does not cover a row.

Every row is blocked in the tool gate, for reads and writes. The disposition says
what the OS sandbox does with the same path for a spawned child process:

``HIDDEN``
    No process inside the sandbox reads the leaf. The sandbox hides it: Linux
    bind-mounts an empty path over it, macOS denies reads, writes and links.

``READONLY``
    Code inside the sandbox reads the leaf, and a write would let the agent pick
    its own ceiling. The sandbox keeps it readable and denies writes and links.
    Policy and profile files belong here, not under ``HIDDEN``: a missing policy
    resolves to the permissive standalone default
    (``platform.governance.load_security_policy`` returns ``None``, and an empty
    profiles directory governs nothing). Hiding a ceiling from the process that
    enforces it removes the ceiling.

``VISIBLE``
    Code inside the sandbox needs to read and write the leaf. No OS rule can apply
    without breaking that code, so the tool gate is the only layer. Each row says
    which reader needs it.

A ``*`` as a whole path segment matches one directory level, for per-app files
such as ``apps/*/.app_secret``.

This is a leaf module. It imports only ``warding.config.paths``, so ``security``
and ``sandbox`` can both import it without a cycle.
"""

from __future__ import annotations

import enum
import os
import re
from dataclasses import dataclass

from warding.config.paths import CONFIG_DIR_NAME, config_dir

#: Home-relative prefixes of the data home (``~/.warding``).
DATA_HOME_PREFIXES: tuple[str, ...] = (CONFIG_DIR_NAME,)


class Disposition(enum.Enum):
    """What the OS sandbox does with a protected leaf (see the module docstring)."""

    HIDDEN = "hidden"
    READONLY = "readonly"
    VISIBLE = "visible"


@dataclass(frozen=True)
class ProtectedLeaf:
    """One protected path under the data home."""

    #: POSIX path relative to the data home. A ``*`` segment matches one level.
    path: str
    disposition: Disposition
    #: Why the leaf is protected, and for ``VISIBLE``, which reader needs it.
    reason: str
    #: The boot integrity check refuses to start if the tool gate drops this row.
    keystone: bool = False

    @property
    def is_wildcard(self) -> bool:
        return "*" in self.path.split("/")


_H = Disposition.HIDDEN
_R = Disposition.READONLY
_V = Disposition.VISIBLE

#: Every protected leaf. Order is stable and carries no meaning.
LEAVES: tuple[ProtectedLeaf, ...] = (
    # ── HIDDEN: nothing inside the sandbox reads these ──
    ProtectedLeaf(".env", _H, "Channel and API credentials. The gateway reads them."),
    ProtectedLeaf(".vault", _H, "Encrypted secret vault, its key, lock and temp files."),
    ProtectedLeaf(
        "apps/*/.app_secret",
        _H,
        "Per-app proxy bearer secret. The gateway reads it and hands it to the "
        "backend through the environment, so the file itself has no in-sandbox reader.",
    ),
    ProtectedLeaf(
        "whatsapp",
        _H,
        "WhatsApp linked-device session store. It is the credential. The channel client "
        "in the gateway opens it.",
    ),
    ProtectedLeaf("browser-cookies.txt", _H, "Retired browser session cookies. No reader."),
    ProtectedLeaf("playwright-storage-state.json", _H, "Retired browser storage state. No reader."),
    ProtectedLeaf(
        "playwright-extension-token",
        _H,
        "Removes the browser approval click. The gateway passes it to the CLI "
        "through the environment, so no process opens the file.",
    ),
    ProtectedLeaf(
        "token_signing.key",
        _H,
        "Dashboard token signing key. Only the gateway web server reads it.",
    ),
    ProtectedLeaf(
        "refresh_chains.json",
        _H,
        "Refresh-token chain state. Only the gateway web server reads it.",
    ),
    ProtectedLeaf(
        "ledger",
        _H,
        "Per-session work ledgers. Sessions reach their own ledger through the "
        "gateway HTTP routes, never through the file.",
    ),
    ProtectedLeaf("webhooks", _H, "Inbound-webhook token hashes and signing secrets."),
    ProtectedLeaf("mcp-apps", _H, "MCP Apps spool. The gateway writes and reads it."),
    ProtectedLeaf(
        ".kiro_cli_binary_trust.json",
        _H,
        "Pinned installer provenance. No producer or consumer remains in the tree.",
    ),
    # ── READONLY: code inside the sandbox reads these; a write moves a ceiling ──
    ProtectedLeaf(
        "security_policy.json",
        _R,
        "Governance ceiling. A missing file resolves to the permissive default.",
        keystone=True,
    ),
    ProtectedLeaf(
        "profiles",
        _R,
        "Governance profiles. An empty directory governs nothing, so hiding it "
        "removes the profile half of POLICY ∩ PROFILE.",
        keystone=True,
    ),
    ProtectedLeaf(
        "admission_policy.json", _R, "Signed-plugin admission trust root.", keystone=True
    ),
    ProtectedLeaf("app_admission.json", _R, "App Kit admission ceiling."),
    ProtectedLeaf(
        "denied_commands.json",
        _R,
        "Denied-command opt-out. A writable file lets the agent set disable_all.",
        keystone=True,
    ),
    ProtectedLeaf(
        "computer_use.json",
        _R,
        "Computer-use enable. A writable file lets the agent grant itself the desktop.",
    ),
    ProtectedLeaf(
        "oauth_endpoints.json",
        _R,
        "Operator OAuth consent-endpoint extension. A write widens an exfiltration carve-out.",
    ),
    ProtectedLeaf(
        "aws_service_consent.json",
        _R,
        "Recorded consent to call a paid AWS service. A write would consent for the operator.",
    ),
    ProtectedLeaf(
        "browser-mode-enabled",
        _R,
        "Browser Mode enable. The dashboard MCP server reads it; its presence "
        "alone authorizes browser operation, so a write is a self-grant.",
    ),
    ProtectedLeaf(
        "browser-engine",
        _R,
        "Selects the browser Playwright launches. The dashboard MCP server reads it.",
    ),
    # ── VISIBLE: code inside the sandbox needs read and write ──
    ProtectedLeaf(
        ".local_secret",
        _V,
        "Loopback MCP, cron and CLI callback secret. In-sandbox MCP servers and "
        "cron scripts read it to call the dashboard. Follow-up: serve it through the "
        "per-session secret so this leaf can be hidden.",
    ),
    ProtectedLeaf(
        "trust",
        _V,
        "SEL trust root. In-sandbox code reads trust/sel_hmac.key to resolve the "
        "session identity.",
    ),
    ProtectedLeaf("sel_hmac.key", _V, "Legacy SEL HMAC key location, read like trust/."),
    ProtectedLeaf(
        "security_events.jsonl",
        _V,
        "SEL audit log. In-sandbox MCP servers append to it directly.",
    ),
    ProtectedLeaf("security_events.d", _V, "Rotated SEL segments, written by the same appenders."),
    ProtectedLeaf(
        "crons.json",
        _V,
        "Cron job store. The in-sandbox cron MCP server reads and rewrites it.",
    ),
    ProtectedLeaf(
        "cron-history",
        _V,
        "Cron run records. The in-sandbox cron service writes them.",
    ),
    ProtectedLeaf(
        "run",
        _V,
        "Holds the sandbox launcher scripts the child executes. Masking it stops the exec.",
    ),
    ProtectedLeaf(
        "routing",
        _V,
        "Harness-router usage ledger, read by `warding route` from an agent shell. "
        "It also holds channel routing state. Follow-up: split the two.",
    ),
    ProtectedLeaf(
        "live_target.json",
        _V,
        "Dev Fleet cutover pointer. The Dev Fleet app backend runs sandboxed and writes it.",
    ),
    ProtectedLeaf(
        "workspace/md-notebook/pat",
        _V,
        "Notes GitHub token. The Notes app backend runs sandboxed and opens it.",
    ),
    ProtectedLeaf(
        "workspace/md-notebook/vaults.json",
        _V,
        "Notes vault registry. The Notes app backend runs sandboxed and opens it.",
    ),
    ProtectedLeaf(
        "workspace/md-notebook/settings.json",
        _V,
        "Notes sync settings. The Notes app backend runs sandboxed and opens it.",
    ),
    ProtectedLeaf(
        "ops_mission_control_secrets.json",
        _V,
        "Ops Mission Control provider tokens. The app backend runs sandboxed and opens them.",
    ),
    ProtectedLeaf(
        "ops_mission_control_policy.json",
        _V,
        "Ops Mission Control autonomy ceiling. The app backend runs sandboxed and opens it.",
    ),
)


# ── Tool-gate view ──


def tool_gate_leaves() -> list[str]:
    """Literal data-home leaves for the tool gate's read+write block list."""
    return [leaf.path for leaf in LEAVES if not leaf.is_wildcard]


def wildcard_leaves() -> list[ProtectedLeaf]:
    """Rows whose path holds a ``*`` segment."""
    return [leaf for leaf in LEAVES if leaf.is_wildcard]


def tool_gate_names() -> frozenset[str]:
    """Casefolded final segments of the wildcard rows.

    The tool gate matches these by name under any directory, the same way it
    matches the harness config files. That covers every per-app directory without
    listing the apps.
    """
    return frozenset(leaf.path.rsplit("/", 1)[-1].casefold() for leaf in wildcard_leaves())


def wildcard_bash_patterns() -> list[str]:
    """Regex alternatives, relative to the data home, for the shell matcher.

    One alternative per wildcard row. Each ``*`` becomes one path segment with no
    whitespace or quote. The caller matches them under ANY leading path, so a data
    home that ``WARDING_HOME`` moved, ``$WARDING_HOME/...`` and the default
    ``~/.warding/...`` are all covered. Over-matching a same-named path elsewhere
    is the safe direction.
    """
    return [
        "/".join(r"[^/\s'\"]+" if part == "*" else re.escape(part) for part in leaf.path.split("/"))
        for leaf in wildcard_leaves()
    ]


# ── Sandbox view ──


def leaves_with(disposition: Disposition) -> list[ProtectedLeaf]:
    """Rows with the given disposition."""
    return [leaf for leaf in LEAVES if leaf.disposition is disposition]


def home_relative(disposition: Disposition) -> list[str]:
    """Literal ``$HOME``-relative paths (``.warding/.vault``) for *disposition*."""
    return [
        f"{prefix}/{leaf.path}"
        for leaf in leaves_with(disposition)
        if not leaf.is_wildcard
        for prefix in DATA_HOME_PREFIXES
    ]


def _data_home_roots(home: str) -> list[str]:
    """Absolute data-home roots: the default one under *home* and the live one.

    ``WARDING_HOME`` can move the data home out from under every ``$HOME``-relative
    entry. ``config_dir()`` already resolves symlinks, so its spelling is the one the
    kernel reports. ``normpath`` only: no extra filesystem call on the spawn path.
    """
    roots = [os.path.normpath(os.path.join(home, prefix)) for prefix in DATA_HOME_PREFIXES]
    try:
        live = os.path.normpath(str(config_dir()))
    except Exception:  # a spawn must not fail on this
        return roots
    if live not in roots:
        roots.append(live)
    return roots


def relocated_targets(disposition: Disposition, home: str) -> list[str]:
    """Absolute literal paths under a data home that is NOT under ``$HOME/.warding``.

    Empty for the default layout, so the default gains no duplicate rule.
    """
    default = {os.path.normpath(os.path.join(home, p)) for p in DATA_HOME_PREFIXES}
    return [
        os.path.join(root, *leaf.path.split("/"))
        for root in _data_home_roots(home)
        if root not in default
        for leaf in leaves_with(disposition)
        if not leaf.is_wildcard
    ]


def wildcard_home_relative() -> list[str]:
    """``$HOME``-relative patterns for the wildcard rows (``.warding/apps/*/.app_secret``)."""
    return [f"{prefix}/{leaf.path}" for leaf in wildcard_leaves() for prefix in DATA_HOME_PREFIXES]


def all_targets(disposition: Disposition, home: str) -> list[str]:
    """Absolute literal paths for *disposition*: default spelling plus relocated."""
    return [
        os.path.join(root, *leaf.path.split("/"))
        for root in _data_home_roots(home)
        for leaf in leaves_with(disposition)
        if not leaf.is_wildcard
    ]


def wildcard_roots(home: str) -> list[str]:
    """Data-home roots the wildcard rows apply under."""
    return _data_home_roots(home)


def expand_wildcards(disposition: Disposition, home: str) -> list[str]:
    """Existing files that the wildcard rows of *disposition* match right now.

    The Linux launcher binds a path that exists at spawn time, so it needs concrete
    paths. One ``scandir`` per ``*`` level. A directory that is missing or
    unreadable yields nothing.
    """
    found: list[str] = []
    for root in _data_home_roots(home):
        for leaf in leaves_with(disposition):
            if not leaf.is_wildcard:
                continue
            level = [root]
            for part in leaf.path.split("/"):
                nxt: list[str] = []
                for base in level:
                    if part != "*":
                        nxt.append(os.path.join(base, part))
                        continue
                    try:
                        with os.scandir(base) as it:
                            nxt.extend(e.path for e in it if e.is_dir(follow_symlinks=False))
                    except OSError:
                        continue
                level = nxt
            found.extend(p for p in level if os.path.lexists(p))
    return list(dict.fromkeys(found))


def seatbelt_regexes(disposition: Disposition, home: str) -> list[str]:
    """Anchored ERE patterns (for a seatbelt ``regex`` filter) for the wildcard rows.

    A regex covers apps installed after the spawn, which a path list cannot.
    Every ERE metacharacter in the path text is escaped, so a home directory named
    ``a[b]`` or ``x^y`` cannot change what the rule matches. Most characters use a
    bracket class. ``[``, ``]``, ``^`` and a backslash cannot sit alone in one, so
    they take a backslash, which the caller doubles for the seatbelt string literal.
    The result keeps the first copy of each rule.
    """

    def esc(text: str) -> str:
        out_chars: list[str] = []
        for c in text:
            if c in "[]^\\":
                out_chars.append("\\" + c)
            elif c in ".+*?()|{}$":
                out_chars.append(f"[{c}]")
            else:
                out_chars.append(c)
        return "".join(out_chars)

    out: list[str] = []
    for root in _data_home_roots(home):
        for leaf in leaves_with(disposition):
            if not leaf.is_wildcard:
                continue
            body = "/".join("[^/]+" if part == "*" else esc(part) for part in leaf.path.split("/"))
            out.append(f"^{esc(root)}/{body}$")
    return list(dict.fromkeys(out))


# ── Posture view ──


def disposition_of(entry: str) -> Disposition | None:
    """Disposition of a ``$HOME``-relative tool-gate entry, or None if not a data-home leaf."""
    for prefix in DATA_HOME_PREFIXES:
        if entry.startswith(prefix + "/"):
            rel = entry[len(prefix) + 1 :]
            for leaf in LEAVES:
                if leaf.path == rel:
                    return leaf.disposition
    return None


def keystone_entries() -> list[str]:
    """``$HOME``-relative entries the boot integrity check requires in the tool gate."""
    return [f"{DATA_HOME_PREFIXES[0]}/{leaf.path}" for leaf in LEAVES if leaf.keystone]
