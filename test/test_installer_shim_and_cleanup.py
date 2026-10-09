"""Regression gates for the packaged-install path of the Warding installer.

A property only a *packaged* install can violate — a dev or source tree
satisfies it by accident, which is why this gate exists:

Property A — the packaged launcher must resolve
    ``_resolve_warding_bin()`` reaches the desktop bundle's launcher by walking
    up from ``warding.__file__``: the bundle is a python-build-standalone
    interpreter tree carrying the package under ``lib/*/site-packages`` and
    exposing a launcher at its root. When that walk misses, the resolver falls
    back to the bare string ``"warding"`` — which is not on ``PATH`` inside a
    bundle — and ``build_agent_config`` / ``rebuild_agent_config`` then DROP
    ``warding-core`` and ``warding-cron``, taking ``spawn_run``, ``cron_add``,
    ``learn_add`` … offline.

    NOTE: a live ``warding mcp-core`` stdio handshake PASSES even when this is
    broken — the server code is healthy, it just never gets launched. The gate
    is at the *resolution / wiring* level, which is what these tests assert: the
    managed-server command must be an absolute, existing, executable path so the
    validation loop keeps it.

These tests FAIL against the pre-fix code, proving they catch the real bug.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

import warding
import warding.agent as agent
import warding.mcp_cleanup as mcp_cleanup

# The ~/.local/bin symlink shim is POSIX-only: ensure_warding_on_path returns
# early on Windows (pip's Scripts\warding.exe is the launcher there, and a
# symlink needs Developer Mode / elevation). These exercise the symlink
# behavior itself, so they are POSIX-only; a dedicated Windows no-op test
# covers the other branch.
_posix_shim_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX ~/.local/bin symlink shim; Windows uses pip's Scripts\\warding.exe",
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _fake_bundle_launcher(tmp_path: Path) -> Path:
    """The desktop bundle's launcher, at the root of a python-build-standalone tree.

    The path comes from :func:`agent._warding_bin_subpath`, the same helper the
    resolver uses, so the fixture cannot drift from the layout under test (or from
    the per-OS naming: ``bin/warding`` on POSIX, ``Scripts\\warding.exe`` on
    Windows).
    """
    root = tmp_path / "backend-dist" / "warding-backend"
    launcher = agent._warding_bin_subpath(root)
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("#!/bin/sh\nexit 0\n")
    launcher.chmod(0o755)
    return launcher


def _bundled_defaults(tmp_path: Path) -> Path:
    """Minimal bundled defaults.json + prompt; returns the config dir."""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(exist_ok=True)
    defaults = {
        "model": "claude-default",
        "tools": [],
        "allowedTools": [],
        "mcpServers": {},
        "hooks": {"preToolUse": "audit"},
    }
    (cfg_dir / "defaults.json").write_text(json.dumps(defaults))
    (cfg_dir / "prompt.md").write_text("system prompt")
    return cfg_dir


def _simulate_bundled_app(monkeypatch, launcher: Path) -> None:
    """Make the running process look like the shipped desktop app.

    Nothing marks the bundle at runtime — it is an ordinary python-build-standalone
    interpreter — so what distinguishes it is WHERE the package sits: the
    resolver's walk-up from ``warding.__file__`` is what reaches the bundle's
    launcher. Point the package at the bundle's ``site-packages`` so that walk runs
    against the shipped layout, reject every other candidate so the test does not
    depend on the tree it runs in, and leave nothing named ``warding`` on PATH.
    """
    root = launcher.parent.parent
    pkg_init = root / "lib" / "python3.12" / "site-packages" / "warding" / "__init__.py"
    pkg_init.parent.mkdir(parents=True, exist_ok=True)
    pkg_init.touch()
    monkeypatch.setattr(agent, "_WARDING_BIN", "", raising=False)
    monkeypatch.setattr(warding, "__file__", str(pkg_init))
    monkeypatch.setattr(agent, "_bin_is_usable", lambda p: str(p) == str(launcher))
    # `warding` is not on PATH; only absolute paths resolve.
    monkeypatch.setattr(
        agent.shutil, "which", lambda c, **kw: c if str(c).startswith("/") else None
    )


# --------------------------------------------------------------------------
# Defect A — resolver
# --------------------------------------------------------------------------
def test_resolver_finds_the_bundled_launcher(tmp_path, monkeypatch):
    """In the desktop bundle, the walk-up from the package must reach the
    bundle's own launcher instead of the bare ``"warding"`` sentinel."""
    launcher = _fake_bundle_launcher(tmp_path)
    _simulate_bundled_app(monkeypatch, launcher)

    resolved = agent._resolve_warding_bin()

    assert resolved == str(launcher), (
        "bundled app must resolve to its own launcher, not bare 'warding' "
        f"(got {resolved!r})"
    )


# --------------------------------------------------------------------------
# Defect A — managed servers survive (no longer dropped)
# --------------------------------------------------------------------------
def test_managed_servers_survive_in_the_desktop_bundle(tmp_path, monkeypatch):
    """build_agent_config() must give warding-core/warding-cron an absolute,
    existing, executable command — the exact predicate the rebuild validation
    loop uses to KEEP (vs. drop) a server."""
    launcher = _fake_bundle_launcher(tmp_path)
    cfg_dir = _bundled_defaults(tmp_path)
    _simulate_bundled_app(monkeypatch, launcher)

    with ExitStack() as stack:
        stack.enter_context(
            patch("warding.agent._shipped_defaults", return_value=cfg_dir / "defaults.json")
        )
        _missing_overrides = tmp_path / "missing_overrides.json"
        stack.enter_context(patch.multiple("warding.agent", _BUNDLED_CFG_DIR=cfg_dir))
        stack.enter_context(
            patch("warding.agent._user_overrides_path", return_value=_missing_overrides)
        )
        stack.enter_context(
            patch("warding.agent._prompt_path", return_value=cfg_dir / "prompt.md")
        )
        stack.enter_context(
            patch("warding.agent._mc_config_path", return_value=tmp_path / "missing_mc.json")
        )
        config = agent.build_agent_config()

    servers = config.get("mcpServers", {})
    for name in ("warding-core", "warding-cron"):
        assert name in servers, f"{name} missing from generated config"
        cmd = servers[name]["command"]
        assert cmd == str(launcher), f"{name} command should be the bundle launcher, got {cmd!r}"
        # This is the literal keep-condition from rebuild_agent_config's
        # validation loop; if it fails the server would be DROPPED.
        assert (
            os.path.isabs(cmd) and os.path.isfile(cmd) and os.access(cmd, os.X_OK)
        ), f"{name} command {cmd!r} would be DROPPED by validation in the bundle"


# --------------------------------------------------------------------------
# Shim install — mirrors install.sh for install paths that skip it (the app)
# --------------------------------------------------------------------------
@_posix_shim_only
def test_ensure_warding_on_path_creates_shim(tmp_path, monkeypatch):
    """A bundled app with no `warding` on PATH must get a shim pointing at the
    bundle's launcher."""
    exe = _fake_bundle_launcher(tmp_path)
    _simulate_bundled_app(monkeypatch, exe)
    bin_dir = tmp_path / "localbin"

    created = agent.ensure_warding_on_path(bin_dir=bin_dir)

    link = bin_dir / "warding"
    assert created == str(link)
    assert link.is_symlink()
    assert os.path.realpath(link) == os.path.realpath(exe)
    assert os.access(link, os.X_OK), "shim must be executable"


@_posix_shim_only
def test_ensure_warding_on_path_idempotent(tmp_path, monkeypatch):
    """Re-running setup when the shim is already correct is a no-op."""
    exe = _fake_bundle_launcher(tmp_path)
    _simulate_bundled_app(monkeypatch, exe)
    bin_dir = tmp_path / "localbin"

    assert agent.ensure_warding_on_path(bin_dir=bin_dir) is not None
    assert agent.ensure_warding_on_path(bin_dir=bin_dir) is None
    assert os.path.realpath(bin_dir / "warding") == os.path.realpath(exe)


def test_ensure_warding_on_path_is_noop_on_windows(tmp_path, monkeypatch):
    """On Windows the POSIX symlink shim must be skipped entirely — pip's
    Scripts\\warding.exe is the launcher, and attempting the symlink raises
    WinError 1314 without Developer Mode, printing a traceback into the setup
    wizard. It must return None WITHOUT touching the filesystem."""
    monkeypatch.setattr(agent.platform_compat, "IS_WINDOWS", True)
    bin_dir = tmp_path / "localbin"

    # Even with a resolvable target, Windows returns None and creates nothing.
    with patch.object(agent, "_resolve_warding_bin", return_value=str(tmp_path / "warding")):
        assert agent.ensure_warding_on_path(bin_dir=bin_dir) is None
    assert not bin_dir.exists()


# --------------------------------------------------------------------------
# First-run auto-delivery (gateway path) — shim on every start.
# The desktop app launches `warding gateway` (never `warding setup`), so
# run_first_run_setup() delivers the shim automatically.
# --------------------------------------------------------------------------
def _sandbox_first_run(tmp_path, monkeypatch, exe):
    """Point first-run's home-derived paths into tmp_path."""
    monkeypatch.setenv("HOME", str(tmp_path))  # shim default ~/.local/bin
    _simulate_bundled_app(monkeypatch, exe)


@_posix_shim_only
def test_first_run_delivers_shim(tmp_path, monkeypatch):
    exe = _fake_bundle_launcher(tmp_path)
    _sandbox_first_run(tmp_path, monkeypatch, exe)

    agent.run_first_run_setup()

    # shim created under sandbox ~/.local/bin
    link = tmp_path / ".local" / "bin" / "warding"
    assert link.is_symlink() and os.path.realpath(link) == os.path.realpath(exe)


def test_first_run_is_best_effort(tmp_path, monkeypatch):
    exe = _fake_bundle_launcher(tmp_path)
    _sandbox_first_run(tmp_path, monkeypatch, exe)

    def _raise(*a, **k):
        raise OSError("shim boom")

    monkeypatch.setattr(agent, "ensure_warding_on_path", _raise)

    # Must not propagate — gateway startup cannot be broken by setup failures.
    agent.run_first_run_setup()


# --------------------------------------------------------------------------
# Resolver: the running interpreter is never the answer
# --------------------------------------------------------------------------
def test_resolver_never_returns_the_interpreter(tmp_path, monkeypatch):
    """The resolver must return a ``warding`` launcher, never whatever
    interpreter happens to be running — a source install with the launcher only
    on PATH must resolve through PATH."""
    path_bin = tmp_path / "warding"
    path_bin.write_text("#!/bin/sh\n")
    path_bin.chmod(0o755)
    interp = tmp_path / "python-interp"  # the running interpreter
    interp.write_text("x")
    interp.chmod(0o755)
    monkeypatch.setattr(agent, "_WARDING_BIN", "", raising=False)
    monkeypatch.setattr(sys, "executable", str(interp))
    # venv + bin-walk find nothing usable; only PATH resolves to path_bin.
    monkeypatch.setattr(agent, "_bin_is_usable", lambda p: str(p) == str(path_bin))
    monkeypatch.setattr(
        agent.shutil, "which", lambda c, **kw: str(path_bin) if c == "warding" else None
    )

    resolved = agent._resolve_warding_bin()
    assert resolved == str(path_bin)
    assert resolved != str(interp), "the resolver must not return sys.executable"


# --------------------------------------------------------------------------
# ensure_warding_on_path — edge cases
# --------------------------------------------------------------------------
def test_ensure_shim_noop_when_no_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "_WARDING_BIN", "", raising=False)
    monkeypatch.setattr(agent, "_bin_is_usable", lambda p: False)
    monkeypatch.setattr(agent.shutil, "which", lambda c, **kw: None)
    bin_dir = tmp_path / "localbin"
    assert agent.ensure_warding_on_path(bin_dir=bin_dir) is None
    assert not (bin_dir / "warding").exists()


@_posix_shim_only
def test_ensure_shim_refreshes_stale_symlink(tmp_path, monkeypatch):
    exe = _fake_bundle_launcher(tmp_path)
    _simulate_bundled_app(monkeypatch, exe)
    bin_dir = tmp_path / "localbin"
    bin_dir.mkdir()
    stale = tmp_path / "old-binary"
    stale.write_text("x")
    stale.chmod(0o755)
    (bin_dir / "warding").symlink_to(stale)

    created = agent.ensure_warding_on_path(bin_dir=bin_dir)
    assert created == str(bin_dir / "warding")
    assert os.path.realpath(bin_dir / "warding") == os.path.realpath(exe)


def test_ensure_shim_noop_when_already_on_path(tmp_path, monkeypatch):
    exe = _fake_bundle_launcher(tmp_path)
    monkeypatch.setattr(agent, "_WARDING_BIN", "", raising=False)
    monkeypatch.setattr(agent, "_bin_is_usable", lambda p: str(p) == str(exe))
    # `warding` already resolves on PATH to the SAME binary.
    monkeypatch.setattr(
        agent.shutil, "which", lambda c, **kw: str(exe) if c == "warding" else None
    )
    bin_dir = tmp_path / "localbin"
    assert agent.ensure_warding_on_path(bin_dir=bin_dir) is None
    assert not (bin_dir / "warding").exists()


# --------------------------------------------------------------------------
# ensure_warding_on_path — never follow an ephemeral git worktree
#
# `git worktree remove` deletes the tree's .venv with it, so a shim pointing
# there dangles and `warding` breaks machine-wide, not just in that tree.
# --------------------------------------------------------------------------
def _checkout_with_warding(root: Path, *, linked_worktree: bool, bare_parent: bool = False) -> Path:
    """Build a fake checkout at *root* whose venv holds a `warding` entrypoint.

    ``linked_worktree`` chooses the repository marker: a ``.git`` FILE with a
    ``gitdir:`` pointer (what `git worktree add` writes) versus a ``.git``
    DIRECTORY (an ordinary clone). ``bare_parent`` selects the pointer shape a
    **bare** repo produces — ``<repo>.git/worktrees/<name>``, with no ``.git``
    path component — verified against real git, not assumed.
    """
    binary = root / ".venv" / "bin" / "warding"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    if linked_worktree:
        git_dir = (
            f"{root.parent}/myrepo.git" if bare_parent else f"{root.parent}/main/.git"
        )
        (root / ".git").write_text(f"gitdir: {git_dir}/worktrees/{root.name}\n")
    else:
        (root / ".git").mkdir()
    return binary


def _resolve_to(monkeypatch, binary: Path) -> None:
    """Make resolution land on *binary* and leave nothing else on PATH."""
    monkeypatch.setattr(agent, "_WARDING_BIN", "", raising=False)
    monkeypatch.setattr(agent, "_resolve_warding_bin", lambda: str(binary))
    monkeypatch.setattr(agent.shutil, "which", lambda c, **kw: None)


def test_in_linked_git_worktree_distinguishes_marker_kind(tmp_path):
    """The detector answers on the nearest marker: `.git` file vs `.git` dir."""
    wt = _checkout_with_warding(tmp_path / "wt-feature", linked_worktree=True)
    clone = _checkout_with_warding(tmp_path / "clone", linked_worktree=False)

    assert agent._in_linked_git_worktree(wt) is True
    assert agent._in_linked_git_worktree(clone) is False
    # Not a repository at all — nothing to decline.
    assert agent._in_linked_git_worktree(tmp_path / "nowhere" / "bin" / "warding") is False


def test_in_linked_git_worktree_matches_a_bare_repo_pointer(tmp_path):
    """A bare repo's git dir IS the repo dir, so its worktree pointer carries no
    `.git` component (`/…/myrepo.git/worktrees/<name>`). Matching on `/.git/`
    would miss it and reopen the bypass."""
    wt = _checkout_with_warding(
        tmp_path / "wt-from-bare", linked_worktree=True, bare_parent=True
    )
    pointer = (tmp_path / "wt-from-bare" / ".git").read_text()
    assert "/.git/worktrees/" not in pointer, "fixture must reproduce the bare shape"

    assert agent._in_linked_git_worktree(wt) is True


def test_in_linked_git_worktree_ignores_a_submodule_pointer(tmp_path):
    """`/worktrees/` must not be so loose that a submodule matches: submodules
    write `gitdir: ../.git/modules/<name>`, a different subtree."""
    root = tmp_path / "sub"
    binary = root / ".venv" / "bin" / "warding"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    (root / ".git").write_text("gitdir: ../.git/modules/sub\n")

    assert agent._in_linked_git_worktree(binary) is False


@_posix_shim_only
def test_ensure_shim_declines_a_worktree_target(tmp_path, monkeypatch):
    """A venv inside a linked worktree must never become the global launcher."""
    binary = _checkout_with_warding(tmp_path / "wt-feature", linked_worktree=True)
    _resolve_to(monkeypatch, binary)
    bin_dir = tmp_path / "localbin"

    assert agent.ensure_warding_on_path(bin_dir=bin_dir) is None
    assert not (bin_dir / "warding").exists(), "worktree venv must not be linked"


@_posix_shim_only
def test_ensure_shim_declines_a_symlink_pointing_into_a_worktree(tmp_path, monkeypatch):
    """The ancestry walk is lexical, so a target that is ITSELF a symlink into a
    worktree must be resolved first — otherwise its own parents carry no `.git`
    marker and the worktree is waved through."""
    real = _checkout_with_warding(tmp_path / "wt-feature", linked_worktree=True)
    # A PATH-style indirection outside any repo, pointing into the worktree.
    link_dir = tmp_path / "elsewhere"
    link_dir.mkdir()
    link = link_dir / "warding"
    link.symlink_to(real)
    assert agent._in_linked_git_worktree(link) is False, "lexical walk cannot see through it"

    _resolve_to(monkeypatch, link)
    bin_dir = tmp_path / "localbin"

    assert agent.ensure_warding_on_path(bin_dir=bin_dir) is None
    assert not (bin_dir / "warding").exists()


@_posix_shim_only
def test_ensure_shim_declines_a_bare_repo_worktree_target(tmp_path, monkeypatch):
    """Same refusal for a worktree of a bare repo — the shape that bypassed the
    first version of this guard."""
    binary = _checkout_with_warding(
        tmp_path / "wt-from-bare", linked_worktree=True, bare_parent=True
    )
    _resolve_to(monkeypatch, binary)
    bin_dir = tmp_path / "localbin"

    assert agent.ensure_warding_on_path(bin_dir=bin_dir) is None
    assert not (bin_dir / "warding").exists()


@_posix_shim_only
def test_ensure_shim_links_an_ordinary_clone_target(tmp_path, monkeypatch):
    """Negative control: the same setup in a normal clone still gets linked, so
    the guard rejects worktrees specifically rather than disabling the shim."""
    binary = _checkout_with_warding(tmp_path / "clone", linked_worktree=False)
    _resolve_to(monkeypatch, binary)
    bin_dir = tmp_path / "localbin"

    created = agent.ensure_warding_on_path(bin_dir=bin_dir)

    assert created == str(bin_dir / "warding")
    assert os.path.realpath(bin_dir / "warding") == os.path.realpath(binary)


@_posix_shim_only
def test_ensure_shim_keeps_a_working_shim_when_target_is_a_worktree(tmp_path, monkeypatch):
    """The regression that broke the machine: an existing, working shim must
    survive a resolution that lands in a worktree — not be replaced by it."""
    good = _checkout_with_warding(tmp_path / "clone", linked_worktree=False)
    bin_dir = tmp_path / "localbin"
    bin_dir.mkdir()
    (bin_dir / "warding").symlink_to(good)

    worktree_binary = _checkout_with_warding(tmp_path / "wt-feature", linked_worktree=True)
    _resolve_to(monkeypatch, worktree_binary)

    assert agent.ensure_warding_on_path(bin_dir=bin_dir) is None
    assert os.path.realpath(bin_dir / "warding") == os.path.realpath(good)
    assert os.path.exists(bin_dir / "warding"), "shim must not be left dangling"


# --------------------------------------------------------------------------
# clean_stale_managed_mcp — edge cases
# --------------------------------------------------------------------------
def test_clean_stale_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_cleanup, "_KIRO_MCP_JSON", tmp_path / "nope.json")
    assert mcp_cleanup.clean_stale_managed_mcp() == []


def test_clean_stale_malformed_json_untouched(tmp_path, monkeypatch):
    p = tmp_path / "mcp.json"
    p.write_text("{ not valid json ")
    monkeypatch.setattr(mcp_cleanup, "_KIRO_MCP_JSON", p)
    assert mcp_cleanup.clean_stale_managed_mcp() == []
    assert p.read_text(encoding="utf-8") == "{ not valid json "  # left untouched


def test_clean_stale_no_stale_leaves_file_untouched(tmp_path, monkeypatch):
    p = tmp_path / "mcp.json"
    content = json.dumps(
        {"mcpServers": {"acme-slack-mcp": {"command": "x", "args": []}}}, indent=2
    )
    p.write_text(content)
    monkeypatch.setattr(mcp_cleanup, "_KIRO_MCP_JSON", p)
    assert mcp_cleanup.clean_stale_managed_mcp() == []
    assert p.read_text(encoding="utf-8") == content  # not rewritten when nothing to remove


def test_in_ephemeral_tree_matches_the_runtime_mount(tmp_path):
    """An AppImage's `/tmp/.mount_<name>XXXXXX` tree disappears on exit, so a
    launcher aimed into it dangles. Matched on the `.mount_` path component."""
    mount = tmp_path / ".mount_WardingAbc123"
    binary = mount / "resources" / "backend-dist" / "warding-backend" / "bin" / "warding"
    assert agent._in_ephemeral_tree(binary) is True
    # A durable install is not condemned by the same check.
    assert agent._in_ephemeral_tree(Path("/opt/Warding/resources/bin/warding")) is False
    assert agent._in_ephemeral_tree(tmp_path / "clone" / "bin" / "warding") is False


def test_in_ephemeral_tree_honors_appdir(tmp_path):
    """$APPDIR is the runtime's own statement of where it mounted, so it decides
    even when the path carries no `.mount_` component (a custom TMPDIR, or a
    runtime that changes its prefix)."""
    appdir = tmp_path / "some-extracted-dir"
    binary = appdir / "bin" / "warding"
    env = {"APPDIR": str(appdir)}
    assert agent._in_ephemeral_tree(binary, env) is True
    # Outside $APPDIR, the same env must not condemn an unrelated path.
    assert agent._in_ephemeral_tree(tmp_path / "elsewhere" / "warding", env) is False


def test_shim_declines_an_appimage_mount_target(tmp_path, monkeypatch):
    """The guard's payoff: ensure_warding_on_path() runs on EVERY gateway start,
    so without it an AppImage re-creates a dangling ~/.local/bin/warding every
    time. Declining leaves whatever already worked in place."""
    mount = tmp_path / ".mount_WardingXyz789"
    binary = mount / "bin" / "warding"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    _resolve_to(monkeypatch, binary)

    bin_dir = tmp_path / "localbin"
    assert agent.ensure_warding_on_path(bin_dir) is None
    assert not (bin_dir / "warding").exists()


def test_launcher_whose_venv_is_gone_is_not_usable(tmp_path):
    """The reaped-work-directory case, observed live: a clone's `bin/warding`
    survives while its `.venv` is deleted, so the file is readable and executable
    but fails at run time. Publishing it as the machine-wide `warding` writes a
    command that is broken the moment it is written."""
    root = tmp_path / "jn-work-dir"
    launcher = root / "bin" / "warding"
    launcher.parent.mkdir(parents=True)
    launcher.write_text('#!/bin/sh\nexec "$(dirname "$0")/../.venv/bin/python" -m warding "$@"\n')
    launcher.chmod(0o755)

    assert agent._bin_is_usable(launcher) is False

    # The INTERPRETER decides, not the directory: a `.venv` that exists but has
    # had its python removed is still dead.
    (root / ".venv" / "bin").mkdir(parents=True)
    assert agent._bin_is_usable(launcher) is False

    (root / ".venv" / "bin" / "python").write_text("")
    (root / ".venv" / "bin" / "python").chmod(0o755)  # a real interpreter is executable
    assert agent._bin_is_usable(launcher) is True


def test_console_script_inside_a_venv_stays_usable(tmp_path):
    """A pip console script lives INSIDE `.venv/bin`, so its interpreter is its own
    sibling. Resolving `<parent>/../.venv` from there probes a nested `.venv/.venv`
    that never exists and would reject the most common source install -- dropping
    the built-in MCP servers, because resolution then falls through to the bare
    "warding" sentinel."""
    venv = tmp_path / "checkout" / ".venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").write_text("")
    (venv / "bin" / "python").chmod(0o755)  # a real interpreter is executable
    script = venv / "bin" / "warding"
    script.write_text(f"#!{venv}/bin/python\nfrom warding.cli import main\n")
    script.chmod(0o755)

    assert agent._bin_is_usable(script) is True


def test_console_script_is_judged_by_its_own_shebang(tmp_path):
    """A pip console script names its interpreter in the shebang, which is the only
    form that stays correct across install layouts -- a venv, a `python3.12 -m pip
    install` into ~/.local/bin, a distro package. Inferring sibling candidates from
    the launcher's directory instead would reject a wheel install whose interpreter
    is the system python."""
    python = tmp_path / "usr" / "bin" / "python3.12"
    python.parent.mkdir(parents=True)
    python.write_text("")
    python.chmod(0o755)  # a real interpreter is executable
    script = tmp_path / "localbin" / "warding"
    script.parent.mkdir(parents=True)
    script.write_text(f"#!{python}\nfrom warding.cli import main\n")
    script.chmod(0o755)

    assert agent._bin_is_usable(script) is True

    python.unlink()
    assert agent._bin_is_usable(script) is False


def test_env_shebang_is_not_treated_as_an_interpreter_path(tmp_path):
    """`#!/usr/bin/env python3` names the FINDER, not the interpreter, so it says
    nothing about a specific path and must not be tested as one."""
    script = tmp_path / "bin" / "warding"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env python3\nfrom warding.cli import main\n")
    script.chmod(0o755)

    assert agent._bin_is_usable(script) is True


def test_launcher_naming_no_interpreter_stays_usable(tmp_path):
    """A launcher that names no interpreter of ours — a compiled entry point, or a
    plain script — must not be condemned by the check above."""
    plain = tmp_path / "bin" / "warding"
    plain.parent.mkdir(parents=True)
    plain.write_text("#!/bin/sh\nexit 0\n")
    plain.chmod(0o755)
    assert agent._bin_is_usable(plain) is True

    compiled = tmp_path / "bin" / "warding.exe"
    compiled.write_bytes(b"MZ\x90\x00compiled-launcher")
    assert agent._bin_is_usable(compiled) is True


# --------------------------------------------------------------------------
# Shim ownership — a background start must not take the name from another
# install. The documented Linux pairing (cli.sh for the CLI, deb/rpm for the
# desktop shell) puts a wheel launcher and a package launcher on ONE machine,
# and `ensure_warding_on_path` runs on every gateway start.
# --------------------------------------------------------------------------
def _simulate_bundled_app_honest(monkeypatch, tmp_path, exe):
    """``_simulate_bundled_app``, but launchers under *tmp_path* are judged for real.

    The shared helper stubs ``_bin_is_usable`` to accept ONLY the bundle launcher.
    That is right for the resolver tests -- it makes them independent of whatever dev
    tree they run in -- but wrong for these, which turn entirely on whether
    ANOTHER install's launcher is judged alive or dead. A stub that calls every
    foreign launcher dead would report ownership working while the product still
    hijacked a live one, so the verdict for the paths built by this test comes
    from the real predicate.
    """
    real_usable = agent._bin_is_usable
    _simulate_bundled_app(monkeypatch, exe)
    monkeypatch.setattr(
        agent,
        "_bin_is_usable",
        lambda p: str(p) == str(exe) or (str(p).startswith(str(tmp_path)) and real_usable(Path(p))),
    )


def _foreign_working_launcher(tmp_path):
    """A launcher for another install: a pip console script whose venv exists."""
    venv_bin = tmp_path / "warding-venv" / "bin"
    venv_bin.mkdir(parents=True)
    interpreter = venv_bin / "python3"
    interpreter.write_text("")
    interpreter.chmod(0o755)
    launcher = venv_bin / "warding"
    launcher.write_text(f"#!{interpreter}\nprint('cli.sh install')\n")
    launcher.chmod(0o755)
    return launcher


@_posix_shim_only
def test_gateway_start_leaves_another_installs_working_launcher(tmp_path, monkeypatch):
    """A package/app start must NOT repoint a wheel install's working launcher.

    Both live on one machine by design, and this runs unattended on every start,
    so claiming the name would make the last install to boot win -- and the other
    installer's upgrades would then land on a path nothing points at.
    """
    exe = _fake_bundle_launcher(tmp_path)
    _simulate_bundled_app_honest(monkeypatch, tmp_path, exe)
    foreign = _foreign_working_launcher(tmp_path)
    bin_dir = tmp_path / "localbin"
    bin_dir.mkdir()
    link = bin_dir / "warding"
    link.symlink_to(foreign)

    assert agent.ensure_warding_on_path(bin_dir=bin_dir) is None
    assert os.path.realpath(link) == os.path.realpath(foreign)


@_posix_shim_only
def test_explicit_setup_claims_the_name(tmp_path, monkeypatch):
    """`warding setup` names an install deliberately, so it MAY take over."""
    exe = _fake_bundle_launcher(tmp_path)
    _simulate_bundled_app_honest(monkeypatch, tmp_path, exe)
    foreign = _foreign_working_launcher(tmp_path)
    bin_dir = tmp_path / "localbin"
    bin_dir.mkdir()
    link = bin_dir / "warding"
    link.symlink_to(foreign)

    created = agent.ensure_warding_on_path(bin_dir=bin_dir, claim_existing=True)

    assert created == str(link)
    assert os.path.realpath(link) == os.path.realpath(exe)


@_posix_shim_only
def test_gateway_start_repairs_a_dangling_launcher(tmp_path, monkeypatch):
    """Filling a BROKEN slot is the whole point -- ownership must not block it."""
    exe = _fake_bundle_launcher(tmp_path)
    _simulate_bundled_app_honest(monkeypatch, tmp_path, exe)
    bin_dir = tmp_path / "localbin"
    bin_dir.mkdir()
    link = bin_dir / "warding"
    link.symlink_to(tmp_path / "reaped" / "bin" / "warding")

    created = agent.ensure_warding_on_path(bin_dir=bin_dir)

    assert created == str(link)
    assert os.path.realpath(link) == os.path.realpath(exe)


@_posix_shim_only
def test_gateway_start_replaces_launcher_whose_interpreter_vanished(tmp_path, monkeypatch):
    """The launcher file exists but its venv was reaped: dead, so replaceable.

    This is the shape that made the live host's `warding` fail -- a readable,
    executable console script whose interpreter no longer exists.
    """
    exe = _fake_bundle_launcher(tmp_path)
    _simulate_bundled_app_honest(monkeypatch, tmp_path, exe)
    stale_bin = tmp_path / "reaped-venv" / "bin"
    stale_bin.mkdir(parents=True)
    stale = stale_bin / "warding"
    stale.write_text(f"#!{stale_bin / 'python3'}\n")  # interpreter never created
    stale.chmod(0o755)
    bin_dir = tmp_path / "localbin"
    bin_dir.mkdir()
    link = bin_dir / "warding"
    link.symlink_to(stale)

    created = agent.ensure_warding_on_path(bin_dir=bin_dir)

    assert created == str(link)
    assert os.path.realpath(link) == os.path.realpath(exe)


_posix_exec_bit_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "the execute BIT is a POSIX concept: on Windows os.access(f, X_OK) is True "
        "for any existing file, so chmod(0o644) cannot model a non-executable "
        "interpreter there"
    ),
)


@_posix_exec_bit_only
def test_interpreter_that_is_not_executable_is_not_usable(tmp_path):
    """A present-but-non-executable interpreter fails at exec time (EACCES), so
    the launcher naming it is as dead as one naming a reaped path -- existence
    alone must not qualify, or gateway startup would decline to repair a
    `warding` that cannot run."""
    python = tmp_path / "venvless" / "bin" / "python3"
    python.parent.mkdir(parents=True)
    python.write_text("")
    python.chmod(0o644)  # readable, NOT executable
    script = tmp_path / "localbin" / "warding"
    script.parent.mkdir(parents=True)
    script.write_text(f"#!{python}\nfrom warding.cli import main\n")
    script.chmod(0o755)

    assert agent._bin_is_usable(script) is False

    python.chmod(0o755)
    assert agent._bin_is_usable(script) is True


@_posix_shim_only
def test_gateway_start_does_not_shadow_a_working_launcher_elsewhere_on_path(tmp_path, monkeypatch):
    """Ownership is about the NAME on PATH, not one directory.

    A pipx bin dir, /usr/local/bin, or a distro package can own a working
    `warding` while ~/.local/bin holds none. Creating one there would shadow it
    or be shadowed by it depending on PATH order -- not a choice an unattended
    gateway start gets to make.
    """
    exe = _fake_bundle_launcher(tmp_path)
    foreign = _foreign_working_launcher(tmp_path)
    _simulate_bundled_app_honest(monkeypatch, tmp_path, exe)
    # `warding` resolves on PATH to the other install, and nothing is in bin_dir.
    monkeypatch.setattr(
        agent.shutil, "which", lambda c, **kw: str(foreign) if c == "warding" else None
    )
    bin_dir = tmp_path / "localbin"

    assert agent.ensure_warding_on_path(bin_dir=bin_dir) is None
    assert not (bin_dir / "warding").exists()


@_posix_shim_only
def test_explicit_setup_may_shadow_a_launcher_elsewhere_on_path(tmp_path, monkeypatch):
    """`warding setup` names this install, so it may publish into bin_dir."""
    exe = _fake_bundle_launcher(tmp_path)
    foreign = _foreign_working_launcher(tmp_path)
    _simulate_bundled_app_honest(monkeypatch, tmp_path, exe)
    monkeypatch.setattr(
        agent.shutil, "which", lambda c, **kw: str(foreign) if c == "warding" else None
    )
    bin_dir = tmp_path / "localbin"

    created = agent.ensure_warding_on_path(bin_dir=bin_dir, claim_existing=True)

    assert created == str(bin_dir / "warding")
    assert os.path.realpath(bin_dir / "warding") == os.path.realpath(exe)
