"""Tests for the select_agent MCP tool (junction.mcp_core._do_select_agent)."""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path

import junction.mcp_core as mcp_core


def _write_cfg(tmp_path: Path) -> Path:
    data = {
        "agents": {
            "default": {
                "kiro_agent": "junction",
                "workspace": "default",
                "memory_store": "default",
            },
            "oncall": {
                "kiro_agent": "ops-agent",
                "workspace": "oncall-ws",
                "memory_store": "oncall-mem",
                "triggers": "incident, prod outage",
            },
            "research": {"kiro_agent": "junction", "description": "deep research agent"},
        },
        "default_agent": "default",
        "workspaces": {"default": {"dir": "workspace"}, "oncall-ws": {"dir": "oncall"}},
        "memory_stores": {"default": {}, "oncall-mem": {}},
    }
    p = tmp_path / "config.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_roster_mode_lists_only_agents_with_triggers(tmp_path):
    p = _write_cfg(tmp_path)
    with unittest.mock.patch("junction.config.loader.config_path", return_value=p):
        out = json.loads(mcp_core._do_select_agent(""))
    assert out["default_agent"] == "default"
    agents = {c["name"]: c for c in out["agents"]}
    # The default agent is the caller — never in the roster.
    assert "default" not in agents
    # An agent WITH triggers is selectable, listed by its raw triggers.
    assert agents["oncall"]["triggers"] == "incident, prod outage"
    # An agent with NO triggers is not a routing candidate — excluded entirely
    # (no fallback to its description).
    assert "research" not in agents
    # The response carries the default fallback + high-confidence guidance.
    assert "default" in out["default_agent"]
    assert "guidance" in out and "high confidence" in out["guidance"]


def test_named_agent_returns_bindings(tmp_path):
    p = _write_cfg(tmp_path)
    with unittest.mock.patch("junction.config.loader.config_path", return_value=p):
        out = json.loads(mcp_core._do_select_agent("oncall"))
    assert out["agent"] == "oncall"
    assert out["bound"]["kiro_agent"] == "ops-agent"
    assert out["bound"]["memory_store"] == "oncall-mem"
    assert out["bound"]["workspace"].endswith("oncall")


def test_unknown_agent_returns_error(tmp_path):
    p = _write_cfg(tmp_path)
    with unittest.mock.patch("junction.config.loader.config_path", return_value=p):
        out = json.loads(mcp_core._do_select_agent("ghost"))
    assert "error" in out
    assert "ghost" in out["error"]
    assert "oncall" in out["available"]


def test_schema_accepts_agent_names_with_spaces_and_dots():
    # Agent creation only strips the name (no regex), so the select_agent schema
    # must not reject a legitimately-named agent — otherwise it would list the
    # agent in its roster but fail to bind it. The membership check in
    # _do_select_agent is the real deny-by-default gate.
    from junction.validation import SELECT_AGENT_SCHEMA, validate_tool_args

    for name in ("on call", "agent.v2", "team-a"):
        cleaned = validate_tool_args({"agent": name}, SELECT_AGENT_SCHEMA)
        assert cleaned["agent"] == name
