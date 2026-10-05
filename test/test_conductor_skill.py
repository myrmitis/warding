"""Tests for junction.conductor_skill — conductor SKILL.md generation.

The conductor is a STATIC delegation guide: the agent roster is resolved at
call time via the `select_agent` tool, not inlined here. So the skill neither
reads config nor lists individual agents.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def skills_loader(tmp_path):
    loader = MagicMock()
    loader._dir = tmp_path
    return loader


def _read_skill(tmp_path: Path) -> str:
    return (tmp_path / "conductor" / "SKILL.md").read_text(encoding="utf-8")


def _gen(skills_loader) -> str:
    from junction.conductor_skill import generate_conductor_skill

    generate_conductor_skill(skills_loader)
    return _read_skill(skills_loader._dir)


def test_points_at_select_agent(skills_loader):
    content = _gen(skills_loader)
    assert "select_agent" in content
    assert "spawn_run" in content


def test_has_always_true_and_delegation_guidelines(skills_loader):
    content = _gen(skills_loader)
    assert "always: true" in content
    assert "How to delegate" in content
    assert "When NOT to delegate" in content
    assert "Default behavior" in content


def test_does_not_inline_an_agent_roster(skills_loader):
    # The roster lives in select_agent; the always-on skill must not dump agents.
    content = _gen(skills_loader)
    assert "Available Agents" not in content
    assert "### " not in content


def test_is_static_and_stable(skills_loader):
    # No config read, so two generations are byte-identical.
    first = _gen(skills_loader)
    second = _gen(skills_loader)
    assert first == second
