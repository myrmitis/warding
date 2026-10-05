"""Tests for _validate_agent fallback chain in subagent.py.

We mock heavy dependencies at sys.modules level so subagent.py can be
imported without the full junction runtime.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest


@dataclass
class _FakeAgent:
    name: str


# Stub out heavy transitive imports before importing subagent
_STUBS = [
    "junction.context",
    "junction.hooks",
    "junction.providers",
    "junction.providers.base",
    "junction.sel",
    "junction.session",
    "junction.slack",
    "junction.slack.format",
    "junction.stats",
]


@pytest.fixture(autouse=True)
def _stub_modules():
    """Inject stub modules so subagent.py can be imported."""
    originals = {}
    for mod_name in _STUBS:
        originals[mod_name] = sys.modules.get(mod_name)
        stub = types.ModuleType(mod_name)
        # providers.base needs specific names
        if mod_name == "junction.providers.base":
            stub.EVENT_COMPLETE = "complete"
            stub.EVENT_PERMISSION_REQUEST = "permission"
            stub.EVENT_TEXT_CHUNK = "text"
            stub.LLMEvent = type("LLMEvent", (), {})
        if mod_name == "junction.hooks":
            stub.TOOL_AUTO_APPROVE = "auto"
            stub.TOOL_DENY = "deny"
        if mod_name == "junction.slack.format":
            stub.extract_options = lambda x: []
        if mod_name == "junction.stats":
            stub.Stats = MagicMock
        if mod_name == "junction.sel":
            stub.sel = MagicMock()
        if mod_name == "junction.context":
            stub.ContextBuilder = MagicMock
        if mod_name == "junction.session":
            stub.SessionManager = MagicMock
        sys.modules[mod_name] = stub

    # Clear cached subagent module so it reimports with stubs
    sys.modules.pop("junction.subagent", None)

    yield

    # Restore
    for mod_name in _STUBS:
        if originals[mod_name] is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = originals[mod_name]
    sys.modules.pop("junction.subagent", None)


def test_found_returns_requested():
    from junction.subagent import _validate_agent

    with patch(
        "junction.subagent.list_agents",
        return_value=[_FakeAgent("code-reviewer"), _FakeAgent("junction")],
    ):
        name, err = _validate_agent("code-reviewer")
        assert name == "code-reviewer"
        assert err == ""


def test_not_found_falls_back_to_junction():
    from junction.subagent import _validate_agent

    with patch(
        "junction.subagent.list_agents",
        return_value=[_FakeAgent("junction")],
    ):
        name, err = _validate_agent("nonexistent")
        assert name == ""
        assert err == ""


def test_unknown_agent_falls_back_silently():
    from junction.subagent import _validate_agent

    with patch(
        "junction.subagent.list_agents",
        return_value=[_FakeAgent("junction")],
    ):
        name, err = _validate_agent("nonexistent")
        assert name == ""
        assert err == ""


def test_empty_input_returns_empty():
    from junction.subagent import _validate_agent

    name, err = _validate_agent("")
    assert name == ""
    assert err == ""
