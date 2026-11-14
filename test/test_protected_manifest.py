"""Every layer must cover every row of ``protected_manifest.LEAVES``.

The manifest is the one list of protected leaves under the data home. The tool gate
(``security``), the OS sandbox (``sandbox``, both backends) and the posture report
(``security_posture``) derive from it. These checks fail when a layer drops a row, so
a leaf cannot be protected at one layer and missing at another.

``test_real_sandboxed_child_*`` run a real macOS sandbox child. They skip when the
host cannot apply a seatbelt profile, for example when the test process is already
inside one (seatbelt cannot nest).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from warding import protected_manifest as pm
from warding import sandbox, security, security_posture
from warding.config.paths import config_dir

D = pm.Disposition
MODES = ("standard", "cc", "strict")

#: The Linux launcher has no read-only mount step yet, so READONLY rows are not
#: enforced there. Flip this to False in the change that adds the step; the staleness
#: check below then forces the exemption out.
LINUX_READONLY_ENFORCED = False

LITERAL = [leaf for leaf in pm.LEAVES if not leaf.is_wildcard]
WILDCARD = pm.wildcard_leaves()


def _roots() -> list[str]:
    """The default data-home spelling and the live (``WARDING_HOME``) one."""
    return [os.path.join(str(Path.home()), ".warding"), str(config_dir())]


def _targets(leaf: pm.ProtectedLeaf) -> list[str]:
    return [os.path.join(root, *leaf.path.split("/")) for root in _roots()]


# ── The manifest itself ──


def test_rows_are_unique_and_explained():
    paths = [leaf.path for leaf in pm.LEAVES]
    assert len(paths) == len(set(paths))
    assert all(leaf.reason.strip() for leaf in pm.LEAVES)


def test_keystone_rows_are_the_four_trust_roots():
    assert sorted(pm.keystone_entries()) == [
        ".warding/admission_policy.json",
        ".warding/denied_commands.json",
        ".warding/profiles",
        ".warding/security_policy.json",
    ]


def test_policy_and_profile_files_are_readonly_not_hidden():
    """A missing policy resolves permissive, so the sandbox must not hide it."""
    by_path = {leaf.path: leaf.disposition for leaf in pm.LEAVES}
    for path in ("security_policy.json", "profiles", "admission_policy.json"):
        assert by_path[path] is D.READONLY


def test_secret_leaves_the_review_named_are_in_the_manifest():
    by_path = {leaf.path: leaf.disposition for leaf in pm.LEAVES}
    assert by_path["apps/*/.app_secret"] is D.HIDDEN
    assert ".local_secret" in by_path


# ── Layer 1: the tool gate ──


@pytest.mark.parametrize("leaf", LITERAL, ids=lambda leaf: leaf.path)
def test_tool_gate_blocks_every_literal_row(leaf):
    for target in _targets(leaf):
        assert security.is_sensitive_path(target), target
        assert security.is_sensitive_write_path(target), target
        assert security.is_sensitive_path(os.path.join(target, "child")), target


def test_tool_gate_blocks_the_per_app_secret():
    secret = os.path.join(str(config_dir()), "apps", "demo", ".app_secret")
    assert security.is_sensitive_path(secret)
    assert security.is_sensitive_write_path(secret)
    assert security.is_sensitive_bash_command("cat ~/.warding/apps/demo/.app_secret")


def test_tool_gate_name_match_is_segment_exact():
    base = os.path.join(str(config_dir()), "apps", "demo")
    assert not security.is_sensitive_path(os.path.join(base, ".app_secret.txt"))
    assert not security.is_sensitive_path(os.path.join(base, "app_secret"))


def test_the_agent_still_cannot_reach_its_own_ceiling():
    """Disposition never loosens the tool gate: READONLY rows are blocked for reads too."""
    for name in ("security_policy.json", "profiles", "admission_policy.json"):
        assert f".warding/{name}" in security._SENSITIVE_HOME_DIRS
        assert security.is_sensitive_path(os.path.join(str(config_dir()), name))


def test_governance_boot_check_passes():
    from warding.platform.governance import assert_governance_paths_protected

    assert_governance_paths_protected()


# ── Layer 2a: the macOS seatbelt profile ──


@pytest.mark.parametrize("mode", MODES)
def test_seatbelt_hides_and_write_denies_every_hidden_row(mode):
    profile = sandbox._build_seatbelt_profile(mode)
    for leaf in (x for x in LITERAL if x.disposition is D.HIDDEN):
        for target in _targets(leaf):
            assert f'(deny file-read* (subpath "{target}"))' in profile, target
            assert f'(deny file-write* (subpath "{target}"))' in profile, target
            assert f'(deny file-write* (literal "{target}"))' in profile, target
            assert f'(deny file-link (subpath "{target}"))' in profile, target


@pytest.mark.parametrize("mode", MODES)
def test_seatbelt_seals_every_readonly_row_and_keeps_it_readable(mode):
    profile = sandbox._build_seatbelt_profile(mode)
    for leaf in (x for x in LITERAL if x.disposition is D.READONLY):
        for target in _targets(leaf):
            assert f'(deny file-write* (literal "{target}"))' in profile, target
            assert f'(deny file-write* (subpath "{target}"))' in profile, target
            assert f'(deny file-link (subpath "{target}"))' in profile, target
            assert f'(deny file-read* (subpath "{target}"))' not in profile, target
            assert f'(deny file-read* (literal "{target}"))' not in profile, target


@pytest.mark.parametrize("mode", MODES)
def test_seatbelt_leaves_visible_rows_alone(mode):
    profile = sandbox._build_seatbelt_profile(mode)
    for leaf in (x for x in LITERAL if x.disposition is D.VISIBLE):
        for target in _targets(leaf):
            assert f'"{target}"' not in profile, target


@pytest.mark.parametrize("mode", MODES)
def test_seatbelt_covers_the_per_app_secret_with_a_regex(mode):
    profile = sandbox._build_seatbelt_profile(mode)
    for op in ("file-read*", "file-write*", "file-link"):
        assert f'(deny {op} (regex #"^' in profile
    assert "[^/]+/[.]app_secret$" in profile


def test_seatbelt_regex_escapes_every_metacharacter_of_the_home_path(monkeypatch, tmp_path):
    """A data home named like a character class cannot widen or break the rule."""
    odd = tmp_path / "a[b]^c.d+e(f)$"
    odd.mkdir()
    monkeypatch.setenv("WARDING_HOME", str(odd))
    patterns = pm.seatbelt_regexes(D.HIDDEN, str(Path.home()))
    live = [p for p in patterns if "[b]" in p or "\\[b\\]" in p]
    assert live, patterns
    pattern = live[0]
    assert "\\[b\\]\\^c" in pattern
    assert "[.]d[+]e[(]f[)][$]" in pattern
    # The compiled rule matches the real secret and nothing next to it.
    real = os.path.join(str(config_dir()), "apps", "demo", ".app_secret")
    assert re.match(pattern, real)
    assert not re.match(pattern, real.replace("a[b]", "ab"))
    assert not re.match(pattern, real + "x")


def test_seatbelt_profile_has_no_duplicate_rules():
    for mode in MODES:
        lines = sandbox._build_seatbelt_profile(mode).splitlines()
        assert len(lines) == len(set(lines)), mode


def test_seatbelt_regex_rule_respects_extra_visible_dirs():
    secret = os.path.join(str(config_dir()), "apps", "demo", ".app_secret")
    masked = sandbox._build_seatbelt_profile("strict")
    assert 'regex #"^' in masked
    visible = sandbox._build_seatbelt_profile("strict", extra_visible_dirs=(secret,))
    # Only the rows under the data home that holds the visible path drop out.
    # The default-home spelling stays masked.
    assert visible.count('(regex #"^') < masked.count('(regex #"^')
    assert visible.count('(regex #"^') > 0


def test_shell_matcher_covers_a_relocated_data_home():
    for command in (
        "cat /srv/crew/apps/demo/.app_secret",
        'cat "$WARDING_HOME/apps/demo/.app_secret"',
        "cd apps/demo && cat .app_secret; cat apps/demo/.app_secret",
        "python -c \"open('/srv/crew/apps/demo/.app_secret').read()\"",
    ):
        assert security.is_sensitive_bash_command(command), command
    assert not security.is_sensitive_bash_command("cat /srv/crew/apps/demo/.app_secret.txt")


# ── Layer 2b: the Linux launcher ──


def _launcher_lists(script: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in script.splitlines():
        for name in ("SENSITIVE_DIRS", "SENSITIVE_FILES"):
            if line.startswith(f"{name} = "):
                out[name] = json.loads(line.split(" = ", 1)[1])
    return out


@pytest.mark.parametrize("mode", MODES)
def test_linux_launcher_masks_every_hidden_row(mode):
    app = Path(config_dir()) / "apps" / "demo"
    app.mkdir(parents=True, exist_ok=True)
    (app / ".app_secret").write_text("s")
    lists = _launcher_lists(sandbox._build_launcher_script(mode))
    for key in ("SENSITIVE_DIRS", "SENSITIVE_FILES"):
        for leaf in (x for x in LITERAL if x.disposition is D.HIDDEN):
            for target in _targets(leaf):
                assert target in lists[key], (key, target)
        assert str(app / ".app_secret") in lists[key]


@pytest.mark.parametrize("mode", MODES)
def test_linux_launcher_does_not_hide_readonly_or_visible_rows(mode):
    lists = _launcher_lists(sandbox._build_launcher_script(mode))
    hidden = set(lists["SENSITIVE_DIRS"]) | set(lists["SENSITIVE_FILES"])
    for leaf in (x for x in LITERAL if x.disposition is not D.HIDDEN):
        for target in _targets(leaf):
            assert target not in hidden, target


def test_linux_launcher_readonly_gap_is_declared_and_not_stale():
    script = sandbox._build_launcher_script("strict")
    if LINUX_READONLY_ENFORCED:
        for leaf in (x for x in LITERAL if x.disposition is D.READONLY):
            for target in _targets(leaf):
                assert target in script, target
    else:
        assert (
            "READONLY_DIRS" not in script
        ), "the Linux launcher now seals read-only paths: set LINUX_READONLY_ENFORCED"


# ── Layer 3: the posture report ──


def test_posture_lists_every_row_with_its_sandbox_treatment():
    items = {item.label: item.detail for item in security_posture._sensitive_path_items()}
    for leaf in pm.LEAVES:
        label = f"~/.warding/{leaf.path}"
        assert label in items, label
        assert security_posture._SANDBOX_DETAIL[leaf.disposition] in items[label], label


# ── A real sandboxed child (macOS) ──


def _can_apply_seatbelt() -> bool:
    if sys.platform != "darwin":
        return False
    probe = subprocess.run(
        ["/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)", "/usr/bin/true"],
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


_CHILD = """
import json, os, sys
home, spec = sys.argv[1], json.loads(sys.argv[2])
def first_file(p):
    if os.path.isdir(p):
        for root, _d, files in os.walk(p):
            if files:
                return os.path.join(root, files[0])
        return None
    return p
out = {"read": {}, "write": {}, "readonly_read": {}}
for rel in spec["hidden"]:
    try:
        open(first_file(os.path.join(home, rel)), "rb").read()
        out["read"][rel] = "READABLE"
    except OSError:
        out["read"][rel] = "denied"
for rel in spec["readonly"]:
    target = os.path.join(home, rel)
    if os.path.isdir(target):
        target = os.path.join(target, "new-from-child")
    try:
        open(target, "ab").write(b"x")
        out["write"][rel] = "WRITABLE"
    except OSError:
        out["write"][rel] = "denied"
    try:
        open(first_file(os.path.join(home, rel)), "rb").read()
        out["readonly_read"][rel] = "readable"
    except OSError:
        out["readonly_read"][rel] = "UNREADABLE"
open(os.path.join(os.environ["TMPDIR"], "ok"), "w").write("ok")
out["normal"] = open(os.path.join(os.environ["TMPDIR"], "ok")).read()
print(json.dumps(out))
"""


@pytest.mark.skipif(not _can_apply_seatbelt(), reason="cannot apply a seatbelt profile here")
@pytest.mark.parametrize("mode", MODES)
def test_real_sandboxed_child_cannot_read_hidden_or_write_readonly(mode, tmp_path, monkeypatch):
    monkeypatch.delenv("WARDING_SANDBOX_ACTIVE", raising=False)
    monkeypatch.delenv("WARDING_SANDBOX_LEVEL", raising=False)
    data = Path(config_dir())
    for leaf in LITERAL:
        target = data / leaf.path
        target.parent.mkdir(parents=True, exist_ok=True)
        if leaf.path in {"profiles", ".vault", "whatsapp", "ledger", "webhooks", "mcp-apps"}:
            target.mkdir(exist_ok=True)
            (target / "inner").write_text("secret")
        else:
            target.write_text("secret")
    (data / "apps" / "demo").mkdir(parents=True, exist_ok=True)
    (data / "apps" / "demo" / ".app_secret").write_text("secret")
    spec = {
        "hidden": [x.path for x in LITERAL if x.disposition is D.HIDDEN]
        + ["apps/demo/.app_secret"],
        "readonly": [x.path for x in LITERAL if x.disposition is D.READONLY],
    }
    argv, cleanup = sandbox.wrap_argv(
        [sys.executable, "-c", _CHILD, str(data), json.dumps(spec)], mode=mode
    )
    try:
        run = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            env={**os.environ, "TMPDIR": str(tmp_path)},
        )
    finally:
        if cleanup:
            Path(cleanup).unlink(missing_ok=True)
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout.strip().splitlines()[-1])
    assert {k: v for k, v in result["read"].items() if v != "denied"} == {}
    assert {k: v for k, v in result["write"].items() if v != "denied"} == {}
    assert {k: v for k, v in result["readonly_read"].items() if v != "readable"} == {}
    assert result["normal"] == "ok"
