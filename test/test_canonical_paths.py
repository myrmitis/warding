"""One canonical path identity: spelling folds, deny-only matching, and the argument walker.

The Windows spellings are emulated, so every case runs on every platform. A fold only
adds a deny candidate. The tests check both halves: a spelling of a protected path is
caught, and a spelling that names something else adds no local candidate.
"""

from __future__ import annotations

import ntpath
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

from warding import path_forms, security
from warding.hooks import TOOL_DENY, HookManager, HooksConfig
from warding.path_forms import MAX_TARGET_DEPTH, MAX_TARGET_NODES, canonical_path_forms
from warding.path_spellings import MAX_TARGET_PATHS, PATH_LIMIT_SENTINEL, exceeds_path_limits
from warding.platform.governance import ScopedRuleset, classify_tool_args

HOME = r"C:\Users\fixture"
DATA_HOME = r"D:\isolated\warding"
# The same home with forward slashes, and its part after the drive. They are built
# from HOME so that no line spells a forward-slash home path as a literal.
HOME_SLASH = HOME.replace("\\", "/")
HOME_TAIL_SLASH = HOME_SLASH[2:]


@pytest.fixture
def windows_path_matching(monkeypatch):
    """Read paths the way a Windows gateway does, with no filesystem or network access."""

    class LexicalWindowsPath(PureWindowsPath):
        @classmethod
        def home(cls):
            return cls(HOME)

        def resolve(self):
            return type(self)(ntpath.normpath(str(self)))

        def expanduser(self):
            return self

    paths = SimpleNamespace(**vars(ntpath))
    paths.realpath = ntpath.normpath
    paths.abspath = ntpath.normpath
    monkeypatch.setattr(
        security,
        "os",
        SimpleNamespace(path=paths, sep="\\", environ={"WARDING_HOME": DATA_HOME}),
    )
    monkeypatch.setattr(security, "Path", LexicalWindowsPath)
    monkeypatch.setattr(security, "_home_targets_cache", {})


# ── Windows spellings of a protected path ──────────────────────────────────

SSH_KEY = HOME + r"\.ssh\id_rsa"
POLICY = DATA_HOME + r"\security_policy.json"

PROTECTED_SPELLINGS = [
    # Extended-length, device and NT-object prefixes, in either separator.
    "\\\\?\\" + SSH_KEY,
    "\\\\.\\" + SSH_KEY,
    "//./" + HOME_SLASH + "/.ssh/id_rsa",
    "//?/" + HOME_SLASH + "/.ssh/id_rsa",
    "\\??\\" + SSH_KEY,
    "\\\\?\\" + POLICY,
    "\\??\\" + POLICY,
    # Alternate data streams and the default-stream suffixes.
    SSH_KEY + "::$DATA",
    HOME + r"\.ssh::$INDEX_ALLOCATION\id_rsa",
    HOME + r"\.ssh:$I30:$INDEX_ALLOCATION\id_rsa",
    SSH_KEY + ":hidden",
    "\\??\\" + SSH_KEY + "::$DATA",
    # Loopback administrative shares, alone and behind a prefix.
    r"\\localhost\C$\Users\fixture\.ssh\id_rsa",
    r"\\LOCALHOST\c$\USERS\FIXTURE\.SSH\id_rsa",
    r"\\127.0.0.1\D$\isolated\warding\security_policy.json",
    r"\\?\UNC\localhost\C$\Users\fixture\.ssh\id_rsa",
    r"\\.\UNC\127.0.0.1\C$\Users\fixture\.ssh\id_rsa",
    "//localhost/C$" + HOME_TAIL_SLASH + "/docs/../.ssh/./id_rsa",
    r"\\127.0.0.1\C$\Users/fixture\\.ssh\id_rsa",
    # Plain spellings that already worked must keep working, in any case and separator.
    r"c:/users/FIXTURE/.SSH/id_rsa",
    HOME + r"\docs\..\.ssh\id_rsa",
]


@pytest.mark.parametrize("spelling", PROTECTED_SPELLINGS)
def test_every_windows_spelling_of_a_protected_path_is_caught(windows_path_matching, spelling):
    assert security.is_sensitive_path(spelling) is True
    assert security.is_sensitive_write_path(spelling) is True


def test_a_spelling_is_a_candidate_and_the_input_stays_as_written(windows_path_matching):
    alias = r"\\localhost\C$\Users\fixture\.ssh\id_rsa"
    forms = security._candidate_forms(alias)
    assert alias in forms
    assert SSH_KEY in forms


@pytest.mark.parametrize(
    "spelling, protected_root",
    [
        ("\\\\.\\C:", True),
        ("\\\\?\\C:\\", True),
        (r"\\localhost\C$", True),
        ("\\\\127.0.0.1\\d$\\", True),
        (r"\\localhost\C$\Users\fixture", True),
        (r"\\localhost\D$\isolated\warding", True),
        (r"\\localhost\C$\Users\fixture\.ssh-copy\id_rsa", False),
        (r"\\localhost\D$\isolated\warding-copy\security_policy.json", False),
    ],
)
def test_a_folded_root_is_matched_in_the_containment_direction(
    windows_path_matching, spelling, protected_root
):
    assert security.path_contains_sensitive(spelling) is protected_root
    assert security.is_sensitive_path(spelling) is False


@pytest.mark.parametrize(
    "spelling",
    [
        r"\\?\C:\Users\fixture\docs\notes.txt",
        r"\\.\C:\Users\fixture\docs\notes.txt",
        r"\\localhost\C$\Users\fixture\docs\notes.txt",
        r"C:\Users\fixture\docs\notes.txt::$DATA",
        r"C:\Users\fixture\docs\notes.txt:stream",
        r"\\?\UNC\localhost\C$\work\a.txt",
    ],
)
def test_a_spelling_of_an_unprotected_path_stays_unprotected(windows_path_matching, spelling):
    assert security.is_sensitive_path(spelling) is False


@pytest.mark.parametrize(
    "alias",
    [
        "\\\\?\\\\\\localhost\\C$\\Users\\fixture\\.ssh\\id_rsa",
        "\\\\?\\//localhost/C$" + HOME_TAIL_SLASH + "/.ssh/id_rsa",
        r"\\remote\C$\Users\fixture\.ssh\id_rsa",
        r"\\localhost.evil\C$\Users\fixture\.ssh\id_rsa",
        r"\\localhost.\C$\Users\fixture\.ssh\id_rsa",
        r"\\127.0.0.10\C$\Users\fixture\.ssh\id_rsa",
        r"\\127.1\C$\Users\fixture\.ssh\id_rsa",
        r"\\machine-name\C$\Users\fixture\.ssh\id_rsa",
        r"\\[::1]\C$\Users\fixture\.ssh\id_rsa",
        r"\\localhost\share\Users\fixture\.ssh\id_rsa",
        r"\\localhost\CC$\Users\fixture\.ssh\id_rsa",
        r"\\localhost\1$\Users\fixture\.ssh\id_rsa",
        "\\\\localhost\\\u00e9$\\Users\\fixture\\.ssh\\id_rsa",
        r"\\localhost\C$extra\Users\fixture\.ssh\id_rsa",
        r"\\localhost\C$.\Users\fixture\.ssh\id_rsa",
        r"\localhost\C$\Users\fixture\.ssh\id_rsa",
        r"localhost\C$\Users\fixture\.ssh\id_rsa",
        r"\\\localhost\C$\Users\fixture\.ssh\id_rsa",
        r"\\localhost\\C$\Users\fixture\.ssh\id_rsa",
        r"\\.\localhost\C$\Users\fixture\.ssh\id_rsa",
        r"\\?\Volume{fixture}\Users\fixture\.ssh\id_rsa",
        r"\\?\UNC\remote\C$\Users\fixture\.ssh\id_rsa",
    ],
)
def test_an_unsupported_alias_adds_no_local_drive_candidate(alias):
    forms = canonical_path_forms(alias)
    assert alias in forms
    for form in forms:
        drive = ntpath.splitdrive(form)[0]
        assert not (len(drive) == 2 and drive[1] == ":" and form.startswith(drive)), form


def test_the_fold_is_lexical_and_makes_no_lookup(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the fold touched the filesystem or the network")

    monkeypatch.setattr(path_forms.os.path, "realpath", refuse)
    monkeypatch.setattr(path_forms.os, "stat", refuse, raising=False)
    forms = canonical_path_forms(r"\\localhost\C$\Users\fixture\.ssh\id_rsa::$DATA")
    assert SSH_KEY in forms


# ── Governance: deny-only matching ─────────────────────────────────────────


def _deny(*patterns):
    return ScopedRuleset.from_dict({"mode": "deny", "deny": list(patterns)}, matcher="path")


def _allow(*patterns):
    return ScopedRuleset.from_dict({"mode": "allow", "allow": list(patterns)}, matcher="path")


@pytest.mark.parametrize(
    "item",
    [
        r"C:\Users\u\.ssh\id_rsa",
        r"\\?\C:\Users\u\.ssh\id_rsa",
        r"\\.\C:\Users\u\.ssh\id_rsa",
        "\\??\\C:\\Users\\u\\.ssh\\id_rsa",
        r"\\localhost\C$\Users\u\.ssh\id_rsa",
        r"\\?\UNC\127.0.0.1\C$\Users\u\.ssh\id_rsa",
        r"C:\Users\u\.ssh\id_rsa::$DATA",
        r"C:\Users\u\.ssh\id_rsa:stream",
        r"c:\USERS\U\.SSH\ID_RSA",
        "C:/Users/u/.ssh/id_rsa",
    ],
)
def test_a_deny_glob_catches_every_spelling_of_the_item(item):
    assert _deny("C:/Users/u/.ssh/**").permits(item).permitted is False
    assert _deny(r"C:\Users\u\.ssh\**").permits(item).permitted is False


def test_a_deny_glob_leaves_an_unrelated_windows_item_alone():
    assert _deny("C:/Users/u/.ssh/**").permits(r"\\?\C:\Users\u\docs\notes.txt").permitted is True
    assert _deny("C:/Users/u/.ssh/**").permits(r"\\remote\C$\Users\u\.ssh\id_rsa").permitted is True


def test_a_folded_spelling_never_widens_an_allow():
    allow = _allow("C:/work/**")
    assert allow.permits(r"\\localhost\C$\work\a.txt").permitted is False
    assert allow.permits(r"\\?\C:\work\..\secret.txt").permitted is False
    assert allow.permits(r"C:\work\a.txt::$DATA").permitted is False


@pytest.mark.parametrize("insensitive, denied", [(True, True), (False, False)])
def test_a_deny_follows_the_filesystem_case_rule(monkeypatch, tmp_path, insensitive, denied):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(path_forms, "CASE_INSENSITIVE_HOST", insensitive)
    item = str(tmp_path / ".ssh" / "id_rsa")
    assert (_deny("~/.SSH/**").permits(item).permitted is False) is denied
    assert _deny("~/.ssh/**").permits(item).permitted is False


def test_an_allow_never_folds_case(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(path_forms, "CASE_INSENSITIVE_HOST", True)
    assert _allow("~/Work/**").permits(str(tmp_path / "work" / "a.txt")).permitted is False


# ── The argument walker ────────────────────────────────────────────────────


def walk(params):
    return list(path_forms.iter_target_paths(params))


def test_the_walker_finds_a_path_nested_in_an_array_of_objects():
    params = {"operations": [{"mode": "Line", "path": "/a"}, {"mode": "Line", "path": "/b"}]}
    assert walk(params) == ["/a", "/b"]


def test_the_walker_finds_a_path_at_any_depth_under_any_accepted_spelling():
    params = {
        "request": {"batch": [[{"inner": {"filePath": "/deep"}}], {"file_path": "/second"}]},
        "path": "/top",
        "paths": ["/listed", {"path": "/listed-object"}, ["/nested-list"]],
    }
    assert walk(params) == ["/top", "/deep", "/second", "/listed", "/listed-object", "/nested-list"]


def test_the_walker_keeps_first_appearance_and_collapses_duplicates():
    params = {"path": "/a", "items": [{"path": "/a"}, {"path": "/b"}], "paths": ["/b", "/c"]}
    assert walk(params) == ["/a", "/b", "/c"]


def test_the_walker_yields_the_trimmed_spelling_a_harness_opens():
    assert walk({"items": [{"path": "\ufeff/x"}]}) == ["\ufeff/x", "/x"]


def test_the_walker_ignores_what_is_not_a_path_argument():
    assert (
        walk({"command": "ls", "content": "/etc/passwd", "items": [{"name": "/etc/passwd"}]}) == []
    )
    assert walk({"paths": "/not-a-list"}) == []
    assert walk({"items": ["/a", "/b"]}) == []
    assert walk(None) == []
    assert walk(["/a"]) == []


def test_the_walker_fails_closed_past_its_depth_bound():
    params: dict = {"path": "/safe"}
    node = params
    for _ in range(MAX_TARGET_DEPTH + 5):
        node["next"] = {}
        node = node["next"]
    node["path"] = "/hidden-past-the-bound"
    found = walk(params)
    assert found[-1] == PATH_LIMIT_SENTINEL
    assert exceeds_path_limits(found)


def test_the_walker_fails_closed_past_its_node_bound():
    params = {"items": [{"sub": {"path": "/same"}} for _ in range(MAX_TARGET_NODES + 10)]}
    assert walk(params)[-1] == PATH_LIMIT_SENTINEL


def test_the_walker_fails_closed_on_an_oversized_path_list_of_non_paths():
    assert walk({"paths": [1.5] * (MAX_TARGET_PATHS + 1)}) == [PATH_LIMIT_SENTINEL]
    assert walk({"items": [{"paths": [None] * (MAX_TARGET_PATHS + 1)}]}) == [PATH_LIMIT_SENTINEL]


def test_a_large_argument_that_cannot_carry_a_path_is_not_bounded():
    embedding = [0.25] * (MAX_TARGET_PATHS * 3)
    params = {
        "embedding": embedding,
        "rows": [embedding[:50]] * 5000,
        "content": [{"type": "text", "text": "hello"}] * (MAX_TARGET_NODES + 500),
        "tags": ["a", "b"] * (MAX_TARGET_PATHS + 10),
        "path": "/real/target.md",
    }
    assert walk(params) == ["/real/target.md"]


def test_a_path_is_still_found_beside_a_large_non_path_argument():
    params = {
        "embedding": [0.5] * (MAX_TARGET_PATHS * 3),
        "content": [{"type": "text", "text": "x"}] * (MAX_TARGET_NODES + 500),
        "operations": [{"path": "/deep/target.md"}],
    }
    assert walk(params) == ["/deep/target.md"]


def test_the_walker_fails_closed_past_the_distinct_path_bound():
    chunk = MAX_TARGET_PATHS // 2
    params = {
        "a": [{"path": f"/a{i}"} for i in range(chunk)],
        "b": [{"path": f"/b{i}"} for i in range(chunk)],
        "c": [{"path": f"/c{i}"} for i in range(chunk)],
    }
    found = walk(params)
    assert found[-1] == PATH_LIMIT_SENTINEL
    assert exceeds_path_limits(found)


def test_the_walker_ends_on_a_container_that_contains_itself():
    params: dict = {"items": []}
    params["items"].append(params)
    assert walk(params)[-1] == PATH_LIMIT_SENTINEL


def test_the_walker_is_iterative():
    params: dict = {}
    node = params
    for _ in range(5000):
        node["x"] = {}
        node = node["x"]
    assert walk(params)[-1] == PATH_LIMIT_SENTINEL


def test_governance_and_the_gate_read_the_same_nested_paths():
    params = {"operations": [{"mode": "Line", "path": "/srv/a"}, {"filePath": "/srv/b"}]}
    assert classify_tool_args("edit", params) == (
        ("filesystem.write", "/srv/a"),
        ("filesystem.write", "/srv/b"),
    )


# ── The real gate: a nested path to a keystone file is denied ──────────────


def _gate(kind, params, title="Read files"):
    return HookManager(HooksConfig.from_dict({})).on_tool_call(
        title,
        session_key="cli_chat",
        tool_kind=kind,
        raw_params=params,
    )


KEYSTONE = [
    "~/.warding/security_policy.json",
    "~/.warding/profiles/team.json",
    "~/.warding/admission_policy.json",
    "~/.warding/computer_use.json",
]


@pytest.mark.parametrize("keystone", KEYSTONE)
@pytest.mark.parametrize("kind", ["read", "edit", "delete", "move"])
def test_the_gate_denies_a_keystone_path_nested_in_an_array_argument(keystone, kind):
    flat = _gate(kind, {"path": keystone})
    nested = _gate(kind, {"operations": [{"mode": "Line", "path": keystone}]})
    deeper = _gate(kind, {"request": {"batch": [{"items": [{"file_path": keystone}]}]}})
    assert flat.action == TOOL_DENY
    assert nested.action == TOOL_DENY
    assert deeper.action == TOOL_DENY


def test_the_gate_denies_a_credential_path_nested_in_an_array_argument():
    decision = _gate("read", {"operations": [{"mode": "Line", "path": "~/.ssh/id_rsa"}]})
    assert decision.action == TOOL_DENY
    assert "sensitive" in decision.reason.lower()


def test_the_gate_denies_a_call_that_hides_a_path_past_the_walker_bound():
    params: dict = {}
    node = params
    for _ in range(MAX_TARGET_DEPTH + 5):
        node["next"] = {}
        node = node["next"]
    node["path"] = "~/.ssh/id_rsa"
    assert _gate("read", params).action == TOOL_DENY


def test_the_gate_still_allows_an_ordinary_nested_path(tmp_path):
    notes = tmp_path / "notes.md"
    notes.write_text("ok", encoding="utf-8")
    decision = _gate("read", {"operations": [{"mode": "Line", "path": str(notes)}]})
    assert decision.action != TOOL_DENY


def test_the_gate_allows_a_large_argument_that_carries_no_path():
    params = {
        "embedding": [0.1] * (MAX_TARGET_PATHS * 3),
        "content": [{"type": "text", "text": "hello"}] * (MAX_TARGET_NODES + 500),
    }
    for kind in ("read", "edit"):
        decision = _gate(kind, params)
        assert decision.action != TOOL_DENY, decision.reason


# ── A protected directory that is itself a symlink ─────────────────────────


@pytest.mark.skipif(not hasattr(Path, "symlink_to"), reason="symlinks unavailable")
def test_a_symlinked_protected_directory_is_matched_by_its_real_location(monkeypatch, tmp_path):
    home = tmp_path / "home"
    real_ssh = tmp_path / "elsewhere" / "ssh-keys"
    real_aws = tmp_path / "elsewhere" / "aws-config"
    for directory in (home, real_ssh, real_aws):
        directory.mkdir(parents=True)
    (real_ssh / "id_rsa").write_text("fixture", encoding="utf-8")
    (real_aws / "credentials").write_text("fixture", encoding="utf-8")
    try:
        (home / ".ssh").symlink_to(real_ssh, target_is_directory=True)
        (home / ".aws").symlink_to(real_aws, target_is_directory=True)
    except OSError:
        pytest.skip("this account cannot create symlinks")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(security, "_home_targets_cache", {})

    # By the lexical anchor, as before.
    assert security.is_sensitive_path(str(home / ".ssh" / "id_rsa")) is True
    # By the directory's real location: no lexical anchor names it.
    assert security.is_sensitive_path(str(real_ssh / "id_rsa")) is True
    assert security.is_sensitive_path(str(real_aws / "credentials")) is True
    assert security.is_sensitive_write_path(str(real_ssh / "new_key")) is True
    assert security.path_contains_sensitive(str(real_ssh.parent)) is True
    # A sibling that is not the protected directory stays open.
    sibling = tmp_path / "elsewhere" / "notes"
    sibling.mkdir()
    assert security.is_sensitive_path(str(sibling / "a.txt")) is False
    assert _gate("read", {"operations": [{"path": str(real_ssh / "id_rsa")}]}).action == TOOL_DENY
