"""Tests for api_agent_detail PATCH model_managed marker behavior.

An explicit model pick must freeze the choice (model_managed=False); clearing
the model (auto) must resume tracking the shipped default (model_managed=True).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import web

from warding import agent_state
from warding.dashboard.handlers.agents import api_agent_detail


@pytest.fixture(autouse=True)
def _owner_caller(monkeypatch):
    """Run as the dashboard owner: these tests exercise handler behavior PAST
    the owner boundary on the agents module's mutating endpoints, which has
    its own enumerate-the-invariant coverage in
    test_agents_endpoints_owner_auth.py."""
    monkeypatch.setattr(
        "warding.dashboard.handlers.agents.is_owner_dashboard_request",
        lambda request: True,
    )


def _patch_request(name: str, body: dict):
    request = MagicMock(spec=web.Request)
    request.method = "PATCH"
    request.match_info = {"name": name}
    request.app = {"state": MagicMock()}

    async def _json():
        return body

    request.json = _json
    return request


@pytest.mark.asyncio
async def test_patch_explicit_model_freezes(tmp_path):
    cfg = tmp_path / "warding.json"
    cfg.write_text(json.dumps({"name": "warding", "model": "claude-old", "model_managed": True}))
    request = _patch_request("warding", {"model": "claude-new"})

    with patch("warding.agent.KIRO_AGENTS_DIR", tmp_path):
        resp = await api_agent_detail(request)

    assert resp.status == 200
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["model"] == "claude-new"
    # Spec stays schema-clean; managed-state goes to the sidecar.
    assert "model_managed" not in data
    assert agent_state.get_model_managed("warding") is False


@pytest.mark.asyncio
async def test_patch_clear_model_resumes_tracking(tmp_path):
    cfg = tmp_path / "warding.json"
    cfg.write_text(
        json.dumps({"name": "warding", "model": "claude-pinned", "model_managed": False})
    )
    request = _patch_request("warding", {"model": ""})

    with patch("warding.agent.KIRO_AGENTS_DIR", tmp_path):
        resp = await api_agent_detail(request)

    assert resp.status == 200
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "model" not in data
    assert "model_managed" not in data
    assert agent_state.get_model_managed("warding") is True


@pytest.mark.asyncio
async def test_patch_without_model_lifts_stale_bookkeeping_keys(tmp_path):
    """A PATCH that never touches ``model`` still runs the shared strip/lift rule.

    Regression: this PATCH handler used
    to unconditionally ``data.pop(...)`` these two keys, discarding a legacy
    value already on disk instead of lifting it into the sidecar the way the
    other writers (PUT, _refresh_dynamic_fields) do.
    Routing through ``agent_state.lift_and_strip_bookkeeping`` closes that gap.
    """
    cfg = tmp_path / "warding.json"
    cfg.write_text(
        json.dumps({"name": "warding", "model_managed": False, "cc_model": "claude-sonnet-4.6"})
    )
    request = _patch_request("warding", {})

    with patch("warding.agent.KIRO_AGENTS_DIR", tmp_path):
        resp = await api_agent_detail(request)

    assert resp.status == 200
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "model_managed" not in data
    assert "cc_model" not in data
    assert agent_state.get_model_managed("warding") is False
    assert agent_state.get_cc_model("warding") == "claude-sonnet-4.6"
