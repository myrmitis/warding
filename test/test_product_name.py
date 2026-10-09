"""Warding's displayed product name and primary CLI."""

from __future__ import annotations

from pathlib import Path

from warding.constants import CLI_BIN, CLI_CONSOLE_STEMS, PRODUCT_NAME, TAGLINE

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_product_name_is_warding() -> None:
    assert PRODUCT_NAME == "Warding"
    assert TAGLINE == "The lamp stays on. The rules stay shut."


def test_pyproject_declares_the_warding_console_script() -> None:
    text = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'warding = "warding._bootstrap:main"' in text
    scripts = text.split("[project.scripts]", 1)[1].split("\n[", 1)[0]
    declared = [line.split("=", 1)[0].strip() for line in scripts.splitlines() if "=" in line]
    assert declared == ["warding"]
    cfg = (_REPO_ROOT / "setup.cfg").read_text(encoding="utf-8")
    assert "warding = warding._bootstrap:main" in cfg
    assert CLI_BIN == "warding"
    assert CLI_CONSOLE_STEMS == ("warding",)
