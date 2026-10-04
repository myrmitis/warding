"""Routing endpoint validation, responses, and cooldown scope."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from junction.harness_router import api


@pytest.mark.asyncio
@pytest.mark.parametrize("lane", [" CODEX ", "", "bad/id"])
async def test_clear_cooldown_normalizes_valid_ids_and_rejects_invalid_ids(monkeypatch, lane):
    router = MagicMock()
    router.ledger.clear_cooldown.return_value = ["codex"]
    monkeypatch.setattr(api, "get_router", lambda: router)
    request = SimpleNamespace(json=AsyncMock(return_value={"lane": lane}))
    response = await api.api_clear_cooldown(request)
    if lane == "bad/id":
        assert response.status == 400 and json.loads(response.body)["code"] == "invalid_lane"
        router.ledger.clear_cooldown.assert_not_called()
    else:
        assert json.loads(response.body) == {"code": "ok", "cleared": ["codex"]}
        router.ledger.clear_cooldown.assert_called_once_with("codex" if lane.strip() else None)


@pytest.mark.asyncio
async def test_clear_invalid_json_uses_documented_all_lane_default(monkeypatch):
    router = MagicMock()
    router.ledger.clear_cooldown.return_value = []
    monkeypatch.setattr(api, "get_router", lambda: router)
    response = await api.api_clear_cooldown(
        SimpleNamespace(json=AsyncMock(side_effect=ValueError("json")))
    )
    assert response.status == 200
    router.ledger.clear_cooldown.assert_called_once_with(None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload,code",
    [
        (None, "invalid_lane_edit"),
        ({}, "invalid_lane_edit"),
        ([], "invalid_lane_edit"),
        ("broken", "invalid_json"),
    ],
)
async def test_lane_edit_rejects_malformed_body_before_writing(monkeypatch, payload, code):
    save = MagicMock()
    monkeypatch.setattr(api, "save_lane_edit", save)
    request = SimpleNamespace(match_info={"harness": "codex"}, json=AsyncMock(return_value=payload))
    if payload == "broken":
        request.json.side_effect = ValueError("json")
    response = await api.api_edit_lane(request)
    assert response.status == 400 and json.loads(response.body)["code"] == code
    save.assert_not_called()


@pytest.mark.asyncio
async def test_harness_view_and_registered_routes(monkeypatch):
    payload = {"harnesses": [], "code": "ok"}
    router = MagicMock()
    router.harnesses_view.return_value = payload
    monkeypatch.setattr(api, "get_router", lambda: router)
    assert json.loads((await api.api_harnesses(make_mocked_request("GET", "/"))).body) == payload
    app = web.Application()
    api.register(app)
    paths = {resource.canonical for resource in app.router.resources()}
    assert paths == {
        "/api/routing/status",
        "/api/routing/decide",
        "/api/routing/cooldown/clear",
        "/api/routing/harnesses",
        "/api/routing/harnesses/{harness}/check",
        "/api/routing/harnesses/{harness}/lane",
        "/api/routing/settings",
    }
