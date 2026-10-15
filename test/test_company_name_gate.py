"""Unit tests for scripts/check_company_names.py.

The gate keeps the retired company name out of the tree except for the
functional identifiers an external system defines. Both directions get tests: a
rule that silently stops matching turns the gate into a rubber stamp, and one
that silently widens starts flagging the hostnames, package names and model ids
the code has to spell exactly. The name is assembled from fragments here, so
this file is clean under the gate it tests.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT_PATH = os.path.join(_REPO_ROOT, "scripts", "check_company_names.py")


def _load():
    spec = importlib.util.spec_from_file_location("check_company_names", _SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_company_names"] = module
    spec.loader.exec_module(module)
    return module


gate = _load()

LOW = "ama" + "zon"
CAP = LOW.capitalize()

RULES = gate.parse_rules(
    [
        "# a comment and a blank line are ignored",
        "",
        "token: " + LOW + r"aws\\?\.com",
        "token: (?-i:" + CAP + r"[A-Z][A-Za-z0-9]+)",
        "token: " + LOW + r"-?q(?:-?developer-?cli)?(?![a-z])",
        r"allow: ^docs/fixture\.md$ :: only-here",
    ]
)


def _scan(path: str, text: str):
    return gate.scan_text(path, text, RULES)


class TestLineVerdicts:
    def test_prose_mention_is_a_violation(self) -> None:
        found = _scan("docs/a.md", f"Runs on {CAP} Linux.\nand fine here")
        assert [(v.path, v.line_no) for v in found] == [("docs/a.md", 1)]

    def test_mention_is_matched_in_any_case(self) -> None:
        assert _scan("a.txt", LOW.upper())
        assert _scan("a.txt", LOW)

    def test_functional_tokens_do_not_count(self) -> None:
        assert not _scan("a.py", f'"https://s3.{LOW}aws.com/bucket"')
        assert not _scan("a.py", f'ARN = "arn:aws:iam::aws:policy/{CAP}SSMManagedInstanceCore"')
        assert not _scan("a.py", f'".local/share/{LOW}-q/data.sqlite3"')

    def test_token_removal_leaves_other_mentions_reported(self) -> None:
        assert _scan("docs/a.md", f"{CAP} S3 at bucket.s3.{LOW}aws.com")

    def test_a_space_after_the_q_is_prose_not_the_directory_name(self) -> None:
        assert _scan("docs/a.md", f"the {CAP} Q Developer CLI")
        assert not _scan("docs/a.md", f"the {LOW}-q-developer-cli directory")

    def test_camel_case_token_is_case_sensitive(self) -> None:
        # The CamelCase token must not swallow a lower-case prose word.
        assert _scan("docs/a.md", f"{LOW}Sprawl")

    def test_allow_entry_covers_only_its_file_and_line(self) -> None:
        assert not _scan("docs/fixture.md", f"{CAP} only-here")
        assert _scan("docs/fixture.md", f"{CAP} somewhere else")
        assert _scan("docs/other.md", f"{CAP} only-here")

    def test_clean_text_has_no_violations(self) -> None:
        assert not _scan("docs/a.md", "Runs on AL2023 with S3 and Polly.")


class TestNoticeAttribution:
    @pytest.mark.parametrize(
        "line",
        [
            f"Copyright {CAP}.com, Inc. or its affiliates. All Rights Reserved.",
            f"{CAP}.com, Inc. (https://www.{LOW}.com/).",
        ],
    )
    def test_attribution_is_exact_and_root_notice_only(self, line: str) -> None:
        rules = gate.load_rules()
        assert gate.scan_text("NOTICE", line, rules) == []
        for path in ("README.md", "docs/NOTICE", "NOTICE.txt"):
            assert gate.scan_text(path, line, rules)
        for altered in ("Use " + line, line + " Endorsement", " " + line, line + " "):
            assert gate.scan_text("NOTICE", altered, rules)


class TestRuleParsing:
    def test_unknown_entry_kind_is_rejected(self) -> None:
        with pytest.raises(SystemExit):
            gate.parse_rules(["bogus: x"])

    def test_allow_needs_both_regexes(self) -> None:
        with pytest.raises(SystemExit):
            gate.parse_rules(["allow: only-a-path"])

    def test_empty_body_is_rejected(self) -> None:
        with pytest.raises(SystemExit):
            gate.parse_rules(["token:"])


class TestFileScanning:
    def test_binary_and_undecodable_files_are_skipped(self, tmp_path) -> None:
        binary = tmp_path / "blob.bin"
        binary.write_bytes(b"\0\1\2" + LOW.encode())
        latin = tmp_path / "latin.txt"
        latin.write_bytes(b"\xff\xfe" + LOW.encode())
        assert gate.read_text(binary) is None
        assert gate.read_text(latin) is None

    def test_the_allowlist_file_is_not_scanned(self) -> None:
        assert gate.scan_paths([str(gate.ALLOWLIST_PATH)], gate.load_rules()) == []

    def test_scan_paths_reports_a_planted_mention(self, tmp_path) -> None:
        planted = tmp_path / "note.md"
        planted.write_text(f"We deploy on {CAP} Linux.\n", encoding="utf-8")
        found = gate.scan_paths([str(planted)], RULES)
        assert len(found) == 1 and found[0].line_no == 1


class TestExitContract:
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, _SCRIPT_PATH, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=_REPO_ROOT,
        )

    def test_self_test_passes(self) -> None:
        result = self._run("--test")
        assert result.returncode == 0, result.stdout + result.stderr

    def test_planted_mention_fails_and_clean_file_passes(self, tmp_path) -> None:
        dirty = tmp_path / "dirty.md"
        dirty.write_text(f"{CAP} Polly\n", encoding="utf-8")
        clean = tmp_path / "clean.md"
        clean.write_text("AWS Polly\n", encoding="utf-8")
        assert self._run(str(dirty)).returncode == 1
        assert self._run(str(clean)).returncode == 0


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git to list tracked files")
def test_tracked_tree_is_clean() -> None:
    """The enforcing check: nothing tracked names the company outside the allowlist."""
    if not os.path.isdir(os.path.join(_REPO_ROOT, ".git")) and not os.path.isfile(
        os.path.join(_REPO_ROOT, ".git")
    ):
        pytest.skip("not a git checkout")
    found = gate.scan_paths(gate.tracked_files(), gate.load_rules())
    assert found == [], "\n".join(v.render() for v in found[:20])
