"""Tests for the bare warding-lite fallback agent config."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from warding.agent import _LITE_AGENT_FILENAME, _install_lite_agent_fallback


@pytest.fixture
def agents_dir(tmp_path: Path) -> Path:
    """Temporary agents directory."""
    d = tmp_path / "agents"
    d.mkdir()
    return d


class TestLiteAgentFallback:
    """The bare warding-lite config backs the claude_code provider's cheap background agent."""

    def test_fallback_writes_bare_config(self, agents_dir: Path) -> None:
        with patch("warding.agent.KIRO_AGENTS_DIR", agents_dir):
            _install_lite_agent_fallback()

        bare = agents_dir / _LITE_AGENT_FILENAME
        assert bare.exists(), "the bare fallback is written when no config exists"
        assert json.loads(bare.read_text(encoding="utf-8"))["name"] == "warding-lite"

    def test_fallback_is_idempotent(self, agents_dir: Path) -> None:
        with patch("warding.agent.KIRO_AGENTS_DIR", agents_dir):
            _install_lite_agent_fallback()
            first = (agents_dir / _LITE_AGENT_FILENAME).read_text(encoding="utf-8")
            _install_lite_agent_fallback()

        assert (agents_dir / _LITE_AGENT_FILENAME).read_text(encoding="utf-8") == first
