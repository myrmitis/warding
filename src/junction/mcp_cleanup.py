"""Shared MCP config cleanup utilities.

Junction does NOT write Junction-managed MCP servers to the user's global
provider MCP config (``~/.kiro/settings/mcp.json``) during normal
operation — the Junction agent file is authoritative, and provider
globals are user-owned.  Remaining helpers here clean up stale
junction-binary entries left over from older install methods.

Extracted from agent.py so both agent.py and cli.py can import at the
top level without circular dependencies (agent.py imports cli.py).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from junction.config.paths import kiro_home

logger = logging.getLogger(__name__)

# Override hook + accessor, NOT a resolved constant. Binding
# `kiro_home()` at import time froze whichever home was active when this module
# was first imported, so conftest's isolation fixture -- which runs after
# collection has already imported it -- could not redirect it, and a test that
# reached `clean_stale_managed_mcp()` without patching would rewrite the
# operator's REAL mcp.json. Keeping the module-level name means the existing
# `monkeypatch.setattr(mcp_cleanup, "_KIRO_MCP_JSON", tmp)` call sites still work.
_KIRO_MCP_JSON: Path | None = None  # explicit override hook, None = live


def _kiro_mcp_json() -> Path:
    if _KIRO_MCP_JSON is not None:
        return _KIRO_MCP_JSON
    return kiro_home() / "settings" / "mcp.json"


# Managed servers whose command is the junction binary itself.
# Only these are affected by install-method path changes.
# Ordered tuples (not sets) so consumers that iterate — e.g. `junction
# doctor`'s MCP probe — get a deterministic order.
#
# The split matters to every consumer that asks "should this server be in the
# spec?". An ALWAYS_ON server missing from an agent spec is a broken install; an
# OPT_IN one is an assignable set that most agents are simply not granted, so
# demanding its presence — or minting an auto-approve grant for it — would undo
# the assignment. Membership here must track the ``opt_in`` flags in
# ``agent._MANAGED_MCP_SERVERS``; a ratchet test pins the two together.
ALWAYS_ON_BIN_MCP_SERVERS = (
    "junction-cron",
    "junction-core",
    "junction-computer",
)
OPT_IN_BIN_MCP_SERVERS = ("junction-dashboard",)

# Every managed-binary server name, regardless of how it reaches a spec. This is
# the cleanup view: Junction never legitimately writes any of them into the
# user's global mcp.json, so a stray entry is purgeable either way.
JUNCTION_BIN_MCP_SERVERS = ALWAYS_ON_BIN_MCP_SERVERS + OPT_IN_BIN_MCP_SERVERS

# Every managed-binary server name Junction is responsible for removing from
# the user's global mcp.json (Junction never legitimately writes these there).
#
# ALWAYS_ON only, and there is no ownership-proven exception. This purge exists
# to reclaim entries an OLDER INSTALL METHOD wrote to the global file — but an
# opt-in server is never written there by any version of Junction, since the
# only way it is ever granted is by hand. So no legitimate residue can exist
# under that name, and anything found there is necessarily the user's own: to be
# left alone, not reclaimed on a technicality about how it happens to be spelled.
STALE_MANAGED_MCP_SERVERS = frozenset(ALWAYS_ON_BIN_MCP_SERVERS)


def _predecessor_mcp_names() -> frozenset[str]:
    """Managed server names owned by an agent an edition supersedes.

    An edition that replaces a predecessor registers it as an import source, and
    the same descriptor names the MCP servers that agent managed. Those entries
    point at a runtime that is gone, so they are unambiguously stale — but only
    the edition knows they exist, which is why this is read from the registry
    rather than listed here.
    """
    # Deferred, NOT top-level: cli.py imports this module eagerly, and
    # onboarding_import pulls yaml/croniter/vector_memory/embeddings. Hoisting it
    # puts that weight on every CLI invocation, which
    # test_cli_lazy_imports.py::test_cli_import_does_not_load_heavy_modules
    # fails on by design. Same annotation as the call site in agent.py.
    from junction.onboarding_import import predecessor_mcp_names  # noqa: PLC0415

    return predecessor_mcp_names()


def _stale_mcp_binaries() -> frozenset[str]:
    """Launcher basenames whose leftover MCP entries an edition declared purgeable."""
    # Deferred for the same boot-weight reason as _predecessor_mcp_names above.
    from junction.onboarding_import import stale_mcp_binaries  # noqa: PLC0415

    return stale_mcp_binaries()


#: Executable suffixes a Windows console script carries (`...\Scripts\<name>.exe`).
#: Only these are stripped when matching a launcher basename, so an unrelated
#: dotted command is never collapsed onto a registered name.
_WINDOWS_LAUNCHER_SUFFIXES = (".exe", ".cmd", ".bat", ".ps1", ".com")


def _invokes_superseded_agent(spec: object) -> bool:
    """True if a server spec's command is the launcher of a superseded agent.

    Catches stale entries a rename left behind whose *name* is not in the managed
    set — e.g. a leftover ``npm:@playwright/mcp`` proxy pointing at the old
    runtime. Keyed on the command basename so it matches both a bare name and an
    absolute path, and never matches a genuine playwright server (which runs
    ``npx``/``node``). The names come from the import-source registry, so the
    core does not hardcode any superseded product name.
    """
    if not isinstance(spec, dict):
        return False
    cmd = spec.get("command", "")
    if not isinstance(cmd, str) or not cmd:
        return False
    binaries = _stale_mcp_binaries()
    if not binaries:
        return False
    # mcp.json is cross-platform data (a config written on Windows may be read
    # anywhere), so split on BOTH separators rather than the host's os.sep —
    # os.path.basename only honors the local separator.
    leaf = re.split(r"[\\/]", cmd)[-1]
    stem = leaf.casefold()
    # Strip only a real executable suffix. Splitting on the FIRST dot instead
    # would collapse any dotted command onto its first segment, so a server
    # launched by an unrelated `<name>.<something>` binary would match a
    # registered `<name>` and be deleted.
    for suffix in _WINDOWS_LAUNCHER_SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem in binaries


def clean_stale_managed_mcp() -> list[str]:
    """Remove stale managed-binary MCP entries from ``~/.kiro/settings/mcp.json``.

    Runs only from explicit setup (``junction setup``) — never on startup, which
    would violate the "Junction owns only the agent file" boundary.

    Removes two classes of stale entry left in the user's global provider
    config; genuine user-installed servers are never touched:

    * **By name** — ``junction-cron`` / ``junction-core`` (written there by an
      older install method; Junction now keeps these in the agent file), plus
      the managed servers of any agent an edition declares it supersedes.
    * **By command** — any server whose command is a superseded agent's launcher,
      e.g. a leftover ``npm:@playwright/mcp`` proxy pointing at its old runtime.

    Returns names of removed servers (empty list on no-op or error).
    """
    if not _kiro_mcp_json().is_file():
        return []
    try:
        data = json.loads(_kiro_mcp_json().read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    servers = data.get("mcpServers", {})
    if not isinstance(servers, dict):
        return []
    removed = sorted(
        name
        for name, spec in servers.items()
        if name in STALE_MANAGED_MCP_SERVERS
        or name in _predecessor_mcp_names()
        or _invokes_superseded_agent(spec)
    )
    if not removed:
        return []
    for name in removed:
        del servers[name]
    try:
        _kiro_mcp_json().write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        logger.info("Removed stale managed MCP entries from kiro mcp.json: %s", removed)
    except OSError:
        logger.debug("Could not clean kiro mcp.json", exc_info=True)
        return []
    return removed
