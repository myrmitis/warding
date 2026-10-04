"""The readiness-gated dashboard endpoints on a harness other than kiro-cli.

``kiro_readiness`` gates the endpoints that act before a turn (destructive
reruns, the OpenAI-compatible endpoint) and the poll-driven kiro-cli spawn sites
(``/api/models``, ``/api/sessions/usage``). With Codex, Claude Code or OpenCode
as the active agent those must neither require kiro-cli nor spawn it:

* reruns are verified by the active agent's own connection probe;
* ``/api/models`` lists what that agent advertised;
* ``/api/sessions/usage`` reports "no Kiro credits" instead of scraping kiro-cli.

Every case here uses a signed-OUT Kiro prerequisite, so an accidental fall-back
onto the Kiro gate shows up as a ``kiro_prerequisite_required`` refusal.
"""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from junction.acp.types import ACP_BACKEND_KAS, ACP_BACKEND_KIRO, ACP_BACKEND_OPENCODE
from junction.dashboard import kiro_readiness
from junction.dashboard.chat_regenerate import api_chat_slot_regenerate
from junction.dashboard.handlers import agents, sessions
from junction.harness_router import connect, service
from junction.kiro_prerequisite import KiroPrerequisiteService
from junction.providers.acp import AcpProvider

_RESOLVE_TARGET = "junction.acp.client._resolve_kiro_bin_for_spawn"


class _SignedOut(KiroPrerequisiteService):
    async def session_ready(self) -> bool:
        return False

    async def verified_ready(self, *, max_age_secs: float) -> bool:
        del max_age_secs
        return False


def _signed_out() -> KiroPrerequisiteService:
    return object.__new__(_SignedOut)


def _live_provider(backend: str, models: list[dict[str, str]]) -> MagicMock:
    provider = MagicMock(spec=AcpProvider)
    provider.client = SimpleNamespace(backend=backend)
    provider.available_models = lambda: models
    return provider


def _request(backend: str, providers: list[Any] | None = None) -> MagicMock:
    state = SimpleNamespace(
        sessions=SimpleNamespace(
            resolved_backend=lambda: backend,
            active_providers=lambda: list(providers or []),
        ),
        kiro_prerequisite_service=_signed_out(),
        _background_tasks=set(),
    )
    request = MagicMock()
    request.app = {"state": state, "kiro_prerequisite_service": state.kiro_prerequisite_service}
    request.path = "/api/test"
    return request


@pytest.fixture(autouse=True)
def _fresh_router():
    service.reset_router()
    kiro_readiness._clear_refusal_warning()
    yield
    service.reset_router()
    kiro_readiness._clear_refusal_warning()


def _no_probe(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record probes instead of spawning an agent; each one reports needs_login."""
    calls: list[str] = []

    async def fake_probe(harness: str, *, installed: bool, model: str = "", timeout: float):
        calls.append(harness)
        return connect.ProbeResult(harness, connect.STATUS_NEEDS_LOGIN, checked_at=1.0)

    monkeypatch.setattr(service, "probe_harness", fake_probe)
    return calls


def _record_probe(harness: str, status: str, advertised: tuple = (), age: float = 0.0) -> None:
    import time

    service.get_router().probes.save(
        connect.ProbeResult(
            harness,
            status,
            models=len(advertised),
            checked_at=time.time() - age,
            advertised=advertised,
        )
    )


# ── the gate ──


@pytest.mark.asyncio
async def test_a_connected_agent_passes_without_kiro(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _no_probe(monkeypatch)
    _record_probe(ACP_BACKEND_OPENCODE, connect.STATUS_CONNECTED)
    assert await kiro_readiness.reject_if_agent_unverified(_request(ACP_BACKEND_OPENCODE)) is None
    assert calls == []  # a recent probe is reused, nothing spawned


@pytest.mark.asyncio
async def test_a_stale_probe_is_repeated_and_a_signed_out_agent_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _no_probe(monkeypatch)
    _record_probe(
        ACP_BACKEND_OPENCODE,
        connect.STATUS_CONNECTED,
        age=kiro_readiness._HARNESS_VERIFY_MAX_AGE_SECS + 60,
    )
    resp = await kiro_readiness.reject_if_agent_unverified(_request(ACP_BACKEND_OPENCODE))
    assert calls == [ACP_BACKEND_OPENCODE]
    assert resp is not None and resp.status == 503
    body = json.loads(resp.text)
    assert body["code"] == "harness_not_connected"
    assert body["harness"] == ACP_BACKEND_OPENCODE and body["status"] == "needs_login"


@pytest.mark.parametrize("backend", [ACP_BACKEND_KIRO, ACP_BACKEND_KAS])
@pytest.mark.asyncio
async def test_kiro_family_keeps_the_kiro_gate(
    monkeypatch: pytest.MonkeyPatch, backend: str
) -> None:
    calls = _no_probe(monkeypatch)
    resp = await kiro_readiness.reject_if_agent_unverified(_request(backend))
    assert resp is not None and json.loads(resp.text)["code"] == "kiro_prerequisite_required"
    assert calls == []


@pytest.mark.asyncio
async def test_an_unreadable_active_backend_fails_closed_on_the_kiro_gate() -> None:
    request = _request(ACP_BACKEND_OPENCODE)
    request.app["state"].sessions = MagicMock()  # resolved_backend() -> not a str
    resp = await kiro_readiness.reject_if_agent_unverified(request)
    assert resp is not None and json.loads(resp.text)["code"] == "kiro_prerequisite_required"


@pytest.mark.asyncio
async def test_regenerate_on_a_signed_out_agent_leaves_history_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_probe(monkeypatch)
    messages = [
        {"role": "user", "content": "question", "ts": "u1"},
        {"role": "assistant", "content": "answer", "ts": "a1"},
    ]
    original = copy.deepcopy(messages)
    persistence = MagicMock()
    state = SimpleNamespace(
        _slots={"s": SimpleNamespace(messages=messages)},
        sessions=SimpleNamespace(resolved_backend=lambda: ACP_BACKEND_OPENCODE),
        conversation_log=persistence,
    )
    app = web.Application()
    app["state"] = state
    app["kiro_prerequisite_service"] = _signed_out()
    app.router.add_post("/api/chat/slots/{slot}/regenerate", api_chat_slot_regenerate)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat/slots/s/regenerate", json={})
        body = await resp.json()
    assert resp.status == 503 and body["code"] == "harness_not_connected"
    assert messages == original and persistence.mock_calls == []


@pytest.mark.asyncio
async def test_openai_compat_names_the_agent_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    from junction.dashboard.openai_compat import api_completions

    _no_probe(monkeypatch)
    request = _request(ACP_BACKEND_OPENCODE)
    resp = await api_completions(request)
    body = json.loads(resp.text)
    assert resp.status == 503
    assert body["error"]["code"] == "harness_not_connected"
    assert body["error"]["type"] == "service_unavailable_error"
    assert "OpenCode" in body["error"]["message"]


# ── /api/models ──


@pytest.mark.asyncio
async def test_models_come_from_the_live_agent_session() -> None:
    older = _live_provider(ACP_BACKEND_OPENCODE, [{"modelId": "old/model"}])
    newer = _live_provider(
        ACP_BACKEND_OPENCODE,
        [
            {"modelId": "openrouter/deepseek-v4", "name": "DeepSeek V4"},
            {"modelId": "anthropic/claude-x"},
        ],
    )
    other = _live_provider("codex", [{"modelId": "gpt-x"}])
    request = _request(ACP_BACKEND_OPENCODE, [older, newer, other])
    with patch(_RESOLVE_TARGET, AsyncMock(return_value="/usr/bin/kiro-cli")) as resolve:
        with patch("asyncio.create_subprocess_exec", AsyncMock()) as spawn:
            resp = await agents.api_models(request)
    resolve.assert_not_called()
    spawn.assert_not_called()
    rows = json.loads(resp.text)
    assert resp.status == 200
    assert [r["model_name"] for r in rows] == [
        "auto",
        "openrouter/deepseek-v4",
        "anthropic/claude-x",
    ]
    assert rows[1]["display_name"] == "DeepSeek V4"
    assert rows[2]["display_name"] == "anthropic/claude-x"


@pytest.mark.asyncio
async def test_models_fall_back_to_the_last_probe() -> None:
    _record_probe(
        ACP_BACKEND_OPENCODE,
        connect.STATUS_CONNECTED,
        advertised=(connect.AdvertisedModel("opencode/big-pickle", "Big Pickle"),),
    )
    resp = await agents.api_models(_request(ACP_BACKEND_OPENCODE))
    rows = json.loads(resp.text)
    assert [r["model_name"] for r in rows] == ["auto", "opencode/big-pickle"]


@pytest.mark.asyncio
async def test_an_agent_that_advertises_nothing_offers_auto() -> None:
    _record_probe(ACP_BACKEND_OPENCODE, connect.STATUS_CONNECTED)
    resp = await agents.api_models(_request(ACP_BACKEND_OPENCODE))
    assert resp.status == 200
    assert [r["model_name"] for r in json.loads(resp.text)] == ["auto"]


@pytest.mark.asyncio
async def test_an_unseen_agent_is_the_degraded_503_without_a_spawn() -> None:
    with patch("asyncio.create_subprocess_exec", AsyncMock()) as spawn:
        resp = await agents.api_models(_request(ACP_BACKEND_OPENCODE))
    spawn.assert_not_called()
    assert resp.status == 503
    assert json.loads(resp.text)["code"] == "harness_models_pending"


# ── /api/sessions/usage ──


@pytest.mark.asyncio
async def test_usage_reports_no_kiro_credits_for_another_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sessions, "_usage_cache_ts", 0.0)
    fetch = AsyncMock()
    monkeypatch.setattr(sessions, "_fetch_usage_bg", fetch)
    resp = await sessions.api_sessions_usage(_request(ACP_BACKEND_OPENCODE))
    assert resp.status == 200
    assert json.loads(resp.text) == {"usage": {"available": False, "reason": "harness_not_kiro"}}
    fetch.assert_not_called()
