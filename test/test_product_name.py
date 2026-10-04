"""Warding's displayed product name and primary CLI."""

from __future__ import annotations

from pathlib import Path

from junction.constants import CLI_BIN, CLI_CONSOLE_STEMS, PRODUCT_NAME, TAGLINE

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_product_name_is_warding() -> None:
    assert PRODUCT_NAME == "Warding"
    assert TAGLINE == "The lamp stays on. The rules stay shut."


def test_pyproject_declares_warding_console_script_with_a_silent_alias() -> None:
    text = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'warding = "junction._bootstrap:main"' in text
    assert 'junction = "junction._bootstrap:main"' in text
    scripts = text.split("[project.scripts]", 1)[1].split("\n[", 1)[0]
    declared = [line.split("=", 1)[0].strip() for line in scripts.splitlines() if "=" in line]
    assert declared == ["warding", "junction"]
    cfg = (_REPO_ROOT / "setup.cfg").read_text(encoding="utf-8")
    assert "warding = junction._bootstrap:main" in cfg
    assert "junction = junction._bootstrap:main" in cfg
    assert CLI_BIN == "warding"
    assert CLI_CONSOLE_STEMS == ("warding", "junction")
    assert CLI_CONSOLE_STEMS[0] == CLI_BIN
