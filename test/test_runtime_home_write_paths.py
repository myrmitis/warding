"""Guard: code that WRITES into the data home must target ``~/.junction``.

``build_agent_config()`` overwrites the generated spec's hooks from the bundled
defaults on every launch (so a user override cannot drop the ``PreToolUse``
security gate), so the default ``postToolUse`` bash-audit hook in
``config/defaults.json`` is the ONLY place its path can be set -- hand-editing the
generated spec regresses on the next start. Shell ``${JUNCTION_HOME:-...}``
fallbacks and shipped Python ``JUNCTION_HOME`` defaults are what actually run when
the variable is unset (kiro-cli strips env for MCP subprocesses), so each one that
names a home directory must name the Junction data home.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULTS_JSON = REPO_ROOT / "src" / "junction" / "config" / "defaults.json"

CURRENT_HOME = "/.junction"

# A dot-directory named in a home fallback: ``$HOME/.junction`` -> ``junction``.
_DOT_DIR = re.compile(r"(?:^|/)\.([A-Za-z][\w-]*)")


def _names_only_the_data_home(value: str) -> bool:
    """Whether every dot-directory *value* names is the data home or a sibling of it.

    ``.junction-dev`` (a worktree dev home) counts: it is a Junction home, not
    another product's directory.
    """
    return all(
        name == "junction" or name.startswith("junction-") for name in _DOT_DIR.findall(value)
    )


# Directories that are vendored, generated, or dependency trees.
SKIP_DIR_PARTS = frozenset({"node_modules", "_vendor", ".venv", "build", "dist", ".git"})


def _shell_scripts() -> list[Path]:
    """Every TRACKED shell script in the repo, vendored/generated trees excluded.

    Asks git for the file list rather than walking the filesystem: a bare
    ``rglob`` also descends GITIGNORED directories, so a developer's local data
    home (``.junction-dev/``, which contains installed skill scripts) or any
    scratch checkout would fail this gate on their machine while CI stayed green. Only committed files can actually
    ship, so only committed files are in scope.

    Falls back to the filesystem walk when git is unavailable (e.g. an sdist
    with no ``.git``), preserving the original behavior there.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "*.sh"],
            capture_output=True,
            check=True,
            timeout=30,
        )
        paths = [REPO_ROOT / n for n in out.stdout.decode().split("\0") if n]
    except (OSError, subprocess.SubprocessError):
        paths = sorted(REPO_ROOT.rglob("*.sh"))
    return [
        p
        for p in sorted(paths)
        if p.is_file() and not SKIP_DIR_PARTS.intersection(p.relative_to(REPO_ROOT).parts)
    ]


def _shipped_python() -> list[Path]:
    """Python that ships to users: the package plus the standalone client packages.

    ``test/`` is excluded on purpose -- test fixtures construct arbitrary homes to
    exercise override and sensitive-path behavior.
    """
    roots = [REPO_ROOT / "src" / "junction", REPO_ROOT / "packages"]
    files: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        files += [
            p
            for p in sorted(root.rglob("*.py"))
            if not SKIP_DIR_PARTS.intersection(p.relative_to(REPO_ROOT).parts)
        ]
    return files


def test_default_audit_hook_writes_to_the_current_data_home() -> None:
    """The packaged ``postToolUse`` hook appends into the Junction data home."""
    hooks = json.loads(DEFAULTS_JSON.read_text(encoding="utf-8"))["hooks"]
    audit = [c["command"] for c in hooks["postToolUse"] if "audit.log" in c["command"]]
    assert audit, "expected a default audit hook in defaults.json"
    for command in audit:
        assert (
            CURRENT_HOME in command
        ), f"the audit hook should target {CURRENT_HOME}, got: {command}"
        fallback = command.split("${JUNCTION_HOME:-", 1)[1].split("}", 1)[0]
        assert _names_only_the_data_home(fallback), command


def test_every_shell_home_default_names_the_data_home() -> None:
    """Every ``${JUNCTION_HOME:-...}`` fallback that names a home names ``.junction``."""
    scripts = _shell_scripts()
    assert len(scripts) > 5, f"guard scanned too few scripts: {len(scripts)}"

    pattern = re.compile(r"\$\{JUNCTION_HOME:-([^}]*)\}")
    offenders: list[str] = []
    for path in scripts:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for default in pattern.findall(line):
                if not _names_only_the_data_home(default):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")

    assert not offenders, (
        "A shell JUNCTION_HOME fallback names a directory other than the Junction "
        "data home. Unset is the COMMON case (kiro-cli strips env for MCP "
        "subprocesses), so the fallback is what actually runs:\n  " + "\n  ".join(offenders)
    )


def test_every_shipped_python_home_default_names_the_data_home() -> None:
    """A shipped ``JUNCTION_HOME`` default that names a home must name ``.junction``.

    A default pointing anywhere else makes the client package's
    ``_read_app_secret`` return ``""`` -- silently downgrading app auth to
    unauthenticated -- rather than failing loudly.
    """
    # Only the DEFAULT is inspected, and only in real call sites -- docstring
    # prose cannot match this shape.
    pattern = re.compile(
        r"""(?:os\.environ\.get|os\.getenv)\(\s*["']JUNCTION_HOME["']\s*,(?P<default>.*)$"""
    )
    literal = re.compile(r"""["'](\.[A-Za-z][\w-]*)["']""")
    offenders: list[str] = []
    for path in _shipped_python():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = pattern.search(line)
            if not match:
                continue
            for name in literal.findall(match.group("default")):
                if not _names_only_the_data_home(name):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")

    assert not offenders, (
        "Shipped Python defaults JUNCTION_HOME to a directory other than the "
        "Junction data home. Unset is the normal case, so the default is what "
        "runs:\n  " + "\n  ".join(offenders)
    )
