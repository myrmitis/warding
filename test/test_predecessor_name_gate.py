"""Unit tests for scripts/check_predecessor_name.py.

The gate fails on spellings of the retired predecessor identity and leaves the
Windows directory-junction term alone. Both directions get tests: a rule that
stops matching turns the gate into a rubber stamp, and one that widens starts
flagging correct platform code. The name is assembled from fragments here, so
this file is clean under the gate it tests.
"""

from __future__ import annotations

import importlib.util
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT_PATH = os.path.join(_REPO_ROOT, "scripts", "check_predecessor_name.py")


def _load():
    spec = importlib.util.spec_from_file_location("check_predecessor_name", _SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_predecessor_name"] = module
    spec.loader.exec_module(module)
    return module


gate = _load()

LOW = "junc" + "tion"
CAP = LOW.capitalize()


def test_self_test_probes_pass() -> None:
    assert gate.self_test() == 0


def test_identity_spelling_reports_its_line() -> None:
    text = f"fine line\nSet {LOW.upper()}_HOME first.\nA directory {LOW} is fine."
    found = gate.scan_text("docs/a.md", text)
    assert [(v.line_no, v.rule) for v in found] == [(2, "retired environment prefix")]


def test_dated_history_is_exempt() -> None:
    assert gate.scan_text("docs/adr/0001-x.md", f"get{LOW}.dev") == []
    assert gate.scan_text("CHANGELOG.md", f"get{LOW}.dev") == []
    assert gate.scan_text("docs/adr.md", f"get{LOW}.dev")


def test_tracked_tree_is_clean() -> None:
    assert gate.scan_paths(gate.tracked_files()) == []
