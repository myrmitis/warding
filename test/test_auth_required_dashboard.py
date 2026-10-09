"""What the dashboard does with a harness that is not signed in.

``AcpAuthRequired`` from a spec-family harness (Codex, Claude Code, ...) reaches
the dashboard as: an error row whose ``meta`` carries ``code: "auth_required"``
and the harness, agent label and login command; a persisted ``needs_login``
connection result that ``/api/models`` and Settings > Agents & plans read; and
NO latch on the Kiro prerequisite service, which belongs to kiro-cli alone.
The kiro-cli raise sites keep the established behaviour (harness-parity H13).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from chat_test_helpers import _make_state

from warding.acp.client import AcpAuthRequired
from warding.acp.types import (
    ACP_BACKEND_CLAUDE,
    ACP_BACKEND_CODEX,
    ACP_BACKEND_KAS,
    ACP_BACKEND_KIMI,
    ACP_BACKEND_KIRO,
    AUTH_REQUIRED_CODE,
)
from warding.dashboard import chat_runner
from warding.dashboard.chat_runner import (
    _auth_required_card_meta,
    _eager_spawn,
    _record_auth_required,
    _run_chat,
)
from warding.dashboard.handlers import agents
from warding.dashboard.handlers.side import _run_side_turn
from warding.dashboard.state import _ChatSlot
from warding.harness_router import connect, service
from warding.kiro_prerequisite import KiroPrerequisiteService
from warding.providers.acp import AcpProvider


@pytest.fixture(autouse=True)
def _fresh_router():
    service.reset_router()
    yield
    service.reset_router()


def _signed_in_kiro_service(tmp_path: Path) -> KiroPrerequisiteService:
    kiro = KiroPrerequisiteService(
        platform_name="linux",
        environ={"HOME": str(tmp_path), "PATH": ""},
        home=tmp_path,
        audit_writer=lambda *_a, **_k: None,
    )
    kiro._has_probed = True
    kiro._status.ready = True
    kiro._status.authenticated = True
    return kiro


def _codex_error() -> AcpAuthRequired:
    return AcpAuthRequired(
        "Codex (ChatGPT) is not signed in. Run `codex login` in a terminal, "
        "then send your message again.",
        backend=ACP_BACKEND_CODEX,
        login="codex login",
        transient=False,
    )


def _probe(harness: str) -> connect.ProbeResult | None:
    return service.get_router().probes.load().get(harness)


class TestCardMeta:
    @pytest.mark.parametrize(
        ("backend", "agent", "login"),
        [
            (ACP_BACKEND_CODEX, "Codex (ChatGPT)", "codex login"),
            (ACP_BACKEND_CLAUDE, "Claude Code", "claude auth login"),
            (ACP_BACKEND_KIMI, "Kimi Code", ""),
        ],
    )
    def test_spec_family_carries_code_harness_agent_and_login(
        self, backend: str, agent: str, login: str
    ) -> None:
        exc = AcpAuthRequired("x", backend=backend, login=login)
        assert _auth_required_card_meta(exc) == {
            "code": AUTH_REQUIRED_CODE,
            "harness": backend,
            "agent": agent,
            "login": login,
        }

    def test_the_wire_code_is_auth_required(self) -> None:
        assert AUTH_REQUIRED_CODE == "auth_required"

    @pytest.mark.parametrize("backend", [ACP_BACKEND_KIRO, ACP_BACKEND_KAS])
    def test_kiro_cli_and_kas_get_no_card_meta(self, backend: str) -> None:
        assert _auth_required_card_meta(AcpAuthRequired("not logged in", backend=backend)) is None
        assert _auth_required_card_meta(AcpAuthRequired("not logged in")) is None


class TestRecordAuthRequired:
    @pytest.mark.asyncio
    async def test_a_spec_family_harness_is_recorded_not_latched(self, tmp_path: Path) -> None:
        kiro = _signed_in_kiro_service(tmp_path)
        state = SimpleNamespace(kiro_prerequisite_service=kiro)

        await _record_auth_required(state, _codex_error())

        probe = _probe("codex")
        assert probe is not None
        assert probe.status == connect.STATUS_NEEDS_LOGIN
        assert probe.checked_at > 0
        # One harness's sign-out never marks kiro-cli's signed out.
        assert kiro._status.ready is True
        assert kiro._status.authenticated is True

    @pytest.mark.asyncio
    async def test_a_kiro_cli_failure_latches_the_service_and_records_no_probe(
        self, tmp_path: Path
    ) -> None:
        kiro = _signed_in_kiro_service(tmp_path)
        state = SimpleNamespace(kiro_prerequisite_service=kiro)

        await _record_auth_required(state, AcpAuthRequired("kiro-cli is not logged in."))

        assert kiro._status.ready is False
        assert kiro._status.authenticated is False
        assert service.get_router().probes.load() == {}

    @pytest.mark.asyncio
    async def test_an_unwritable_record_never_disrupts_the_turn(self, tmp_path: Path) -> None:
        state = SimpleNamespace(kiro_prerequisite_service=_signed_in_kiro_service(tmp_path))
        with patch.object(
            connect.ProbeStore, "save", MagicMock(side_effect=OSError("read-only home"))
        ):
            await _record_auth_required(state, _codex_error())  # must not raise


class TestChatTurn:
    def _state(self, tmp_path: Path, exc: AcpAuthRequired) -> tuple[Any, _ChatSlot]:
        state = _make_state(tmp_path)
        state.kiro_prerequisite_service = _signed_in_kiro_service(tmp_path)
        state.slack_client = MagicMock()
        state.slack_client.post_message = AsyncMock()
        state.broadcast_ws = MagicMock()
        state.push_slots_update = MagicMock()
        state.push_refresh = MagicMock()
        state.context_builder = None
        state.consolidator = None
        state._hook_store = None
        state._yolo = False

        async def stream(_message: str):
            raise exc
            yield  # pragma: no cover - generator shape only

        client = MagicMock()
        client.stream = stream
        client.stream_command = stream
        client.context_usage_pct = MagicMock(return_value=1.0)
        state.sessions.get_or_create = AsyncMock(return_value=(client, True, False))
        state.sessions.record_failure = AsyncMock()
        state.sessions.get_slack_link = MagicMock(return_value=("", ""))
        slot = state.get_or_create_slot("signed-out")
        slot._titled = True
        return state, slot

    @staticmethod
    def _error_rows(slot: _ChatSlot) -> list[dict[str, Any]]:
        return [m for m in slot.messages if m.get("role") == "error"]

    @pytest.mark.asyncio
    async def test_the_error_row_carries_the_card_fields(self, tmp_path: Path) -> None:
        state, slot = self._state(tmp_path, _codex_error())

        await _run_chat(state, slot, "hello")

        rows = self._error_rows(slot)
        assert len(rows) == 1
        row = rows[0]
        assert row["content"].startswith("Codex (ChatGPT) is not signed in.")
        assert "JSON-RPC" not in row["content"]
        meta = row["meta"]
        assert {k: meta[k] for k in ("code", "harness", "agent", "login")} == {
            "code": "auth_required",
            "harness": "codex",
            "agent": "Codex (ChatGPT)",
            "login": "codex login",
        }
        assert meta["mid"]
        # The harness is recorded, the Kiro service is left alone.
        probe = _probe("codex")
        assert probe is not None and probe.status == connect.STATUS_NEEDS_LOGIN
        assert state.kiro_prerequisite_service._status.ready is True
        state.sessions.get_or_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_the_card_content_is_redacted(self, tmp_path: Path) -> None:
        secret = "AKIAIOSFODNN7EXAMPLE"
        exc = AcpAuthRequired(
            f"Codex is not signed in (https://evil.example/x?token={secret})",
            backend=ACP_BACKEND_CODEX,
            login="codex login",
        )
        state, slot = self._state(tmp_path, exc)

        await _run_chat(state, slot, "hello")

        content = self._error_rows(slot)[0]["content"]
        assert secret not in content
        assert "https://evil.example/x" not in content
        assert "[REDACTED" in content

    @pytest.mark.asyncio
    async def test_a_kiro_cli_failure_is_the_same_plain_row_and_latch(self, tmp_path: Path) -> None:
        state, slot = self._state(tmp_path, AcpAuthRequired("kiro-cli is not logged in."))

        await _run_chat(state, slot, "hello")

        rows = self._error_rows(slot)
        assert [r["content"] for r in rows] == ["kiro-cli is not logged in."]
        assert "code" not in rows[0]["meta"]
        assert state.kiro_prerequisite_service._status.ready is False
        assert service.get_router().probes.load() == {}


class TestSideTurn:
    @pytest.mark.asyncio
    async def test_a_spec_family_sign_out_is_recorded_and_not_latched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from warding.dashboard.side_state import SideState

        state = _make_state(tmp_path)
        state.kiro_prerequisite_service = _signed_in_kiro_service(tmp_path)
        parent = state.get_or_create_slot("parent")
        parent._side = SideState()
        parent._side.last_run_id = "run-auth"

        async def exploding_stream(*_a: Any, **_k: Any):
            raise _codex_error()
            yield  # pragma: no cover - generator shape only

        client = MagicMock()
        client.stream = exploding_stream
        client.stream_command = exploding_stream
        state.sessions.get_or_create = AsyncMock(return_value=(client, True, False))
        state.sessions.release = MagicMock()
        broadcasts: list[dict] = []
        monkeypatch.setattr(
            "warding.dashboard.handlers.side.broadcast_side_result",
            lambda state, **kw: broadcasts.append(kw),
        )

        await _run_side_turn(state, parent, "run-auth", "what is going on?", is_first_turn=True)

        errors = [b for b in broadcasts if b.get("is_error")]
        assert errors and "codex login" in errors[-1]["content"]
        probe = _probe("codex")
        assert probe is not None and probe.status == connect.STATUS_NEEDS_LOGIN
        assert state.kiro_prerequisite_service._status.ready is True


class TestEagerSpawn:
    @staticmethod
    def _state(slot: _ChatSlot, exc: Exception) -> MagicMock:
        state = MagicMock()
        state.get_slot = MagicMock(return_value=slot)
        state.sessions = MagicMock()
        state.sessions.get_or_create = AsyncMock(side_effect=exc)
        state.sessions.release = MagicMock()
        state.sessions.reset = AsyncMock()
        return state

    @pytest.mark.asyncio
    async def test_a_signed_out_harness_is_recorded_without_a_traceback(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(chat_runner, "_EAGER_SPAWN_DEBOUNCE_SECS", 0)
        slot = _ChatSlot("t1")
        state = self._state(slot, _codex_error())

        with caplog.at_level(logging.INFO, logger="warding.dashboard.chat_runner"):
            await _eager_spawn(state, slot)  # must not raise

        probe = _probe("codex")
        assert probe is not None and probe.status == connect.STATUS_NEEDS_LOGIN
        failures = [r for r in caplog.records if "Eager spawn failed" in r.getMessage()]
        assert failures == []

    @pytest.mark.asyncio
    async def test_a_kiro_cli_sign_out_keeps_its_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(chat_runner, "_EAGER_SPAWN_DEBOUNCE_SECS", 0)
        slot = _ChatSlot("t1")
        state = self._state(slot, AcpAuthRequired("kiro-cli is not logged in."))

        with caplog.at_level(logging.WARNING, logger="warding.dashboard.chat_runner"):
            await _eager_spawn(state, slot)

        failures = [r for r in caplog.records if "Eager spawn failed" in r.getMessage()]
        assert len(failures) == 1 and failures[0].exc_info is not None
        assert service.get_router().probes.load() == {}


def _request(
    backend: str,
    providers: list[Any] | None = None,
    started: dict[int, float] | None = None,
) -> MagicMock:
    """*started* maps ``id(provider)`` to the time its session registered."""
    times = started or {}
    state = SimpleNamespace(
        sessions=SimpleNamespace(
            resolved_backend=lambda: backend,
            active_providers=lambda: list(providers or []),
            provider_started_at=lambda provider: times.get(id(provider)),
        ),
        _background_tasks=set(),
    )
    request = MagicMock()
    request.app = {"state": state}
    request.path = "/api/models"
    return request


def _record(
    harness: str, status: str, advertised: tuple[connect.AdvertisedModel, ...] = ()
) -> None:
    service.get_router().probes.save(
        connect.ProbeResult(
            harness=harness,
            status=status,
            models=len(advertised),
            checked_at=1.0,
            advertised=advertised,
        )
    )


class TestApiModels:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("backend", "agent", "login"),
        [
            (ACP_BACKEND_CODEX, "Codex (ChatGPT)", "codex login"),
            (ACP_BACKEND_CLAUDE, "Claude Code", "claude auth login"),
        ],
    )
    async def test_a_signed_out_harness_answers_the_structured_body(
        self, backend: str, agent: str, login: str
    ) -> None:
        _record(backend, connect.STATUS_NEEDS_LOGIN)

        with patch("asyncio.create_subprocess_exec", AsyncMock()) as spawn:
            resp = await agents.api_models(_request(backend))

        spawn.assert_not_called()
        # Still the degraded 503 every /api/models consumer already polls through.
        assert resp.status == 503
        body = json.loads(resp.text)
        assert body["code"] == "auth_required"
        assert body["harness"] == backend
        assert body["agent"] == agent
        assert body["login"] == login
        assert "JSON-RPC" not in body["error"]

    @staticmethod
    def _resident(backend: str = ACP_BACKEND_CODEX) -> Any:
        provider = MagicMock(spec=AcpProvider)
        provider.client = SimpleNamespace(backend=backend)
        provider.available_models = lambda: [{"modelId": "gpt-live", "name": "Live"}]
        return provider

    @pytest.mark.asyncio
    async def test_a_session_that_started_after_the_refusal_wins(self) -> None:
        """It proved the agent can authenticate now, so its list is current."""
        _record(ACP_BACKEND_CODEX, connect.STATUS_NEEDS_LOGIN)  # checked_at == 1.0
        provider = self._resident()

        resp = await agents.api_models(
            _request(ACP_BACKEND_CODEX, [provider], {id(provider): 50.0})
        )

        assert resp.status == 200
        assert [r["model_name"] for r in json.loads(resp.text)] == ["auto", "gpt-live"]

    @pytest.mark.asyncio
    async def test_a_session_that_predates_the_refusal_does_not_hide_it(self) -> None:
        """Its list came from a login that a later start showed is gone."""
        _record(ACP_BACKEND_CODEX, connect.STATUS_NEEDS_LOGIN)  # checked_at == 1.0
        provider = self._resident()

        resp = await agents.api_models(_request(ACP_BACKEND_CODEX, [provider], {id(provider): 0.5}))

        assert resp.status == 503
        body = json.loads(resp.text)
        assert body["code"] == "auth_required"
        assert body["harness"] == ACP_BACKEND_CODEX
        assert body["login"] == "codex login"

    @pytest.mark.asyncio
    async def test_a_session_with_no_known_start_does_not_hide_the_refusal(self) -> None:
        _record(ACP_BACKEND_CODEX, connect.STATUS_NEEDS_LOGIN)
        provider = self._resident()

        resp = await agents.api_models(_request(ACP_BACKEND_CODEX, [provider]))

        assert resp.status == 503
        assert json.loads(resp.text)["code"] == "auth_required"

    @pytest.mark.asyncio
    async def test_a_newer_session_is_chosen_over_a_stale_one(self) -> None:
        _record(ACP_BACKEND_CODEX, connect.STATUS_NEEDS_LOGIN)
        stale, fresh = self._resident(), self._resident()
        stale.available_models = lambda: [{"modelId": "gpt-stale"}]
        fresh.available_models = lambda: [{"modelId": "gpt-fresh"}]

        resp = await agents.api_models(
            _request(
                ACP_BACKEND_CODEX,
                [stale, fresh],
                {id(stale): 0.5, id(fresh): 50.0},
            )
        )

        assert [r["model_name"] for r in json.loads(resp.text)] == ["auto", "gpt-fresh"]

    @pytest.mark.asyncio
    async def test_without_a_refusal_a_resident_list_needs_no_timestamp(self) -> None:
        provider = self._resident()

        resp = await agents.api_models(_request(ACP_BACKEND_CODEX, [provider]))

        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_a_connected_probe_does_not_discard_an_older_session(self) -> None:
        _record(ACP_BACKEND_CODEX, connect.STATUS_CONNECTED)
        provider = self._resident()

        resp = await agents.api_models(_request(ACP_BACKEND_CODEX, [provider], {id(provider): 0.5}))

        assert resp.status == 200
        assert [r["model_name"] for r in json.loads(resp.text)] == ["auto", "gpt-live"]

    @pytest.mark.asyncio
    async def test_a_later_connected_check_replaces_the_sign_in_state(self) -> None:
        _record(ACP_BACKEND_CODEX, connect.STATUS_NEEDS_LOGIN)
        _record(
            ACP_BACKEND_CODEX,
            connect.STATUS_CONNECTED,
            (connect.AdvertisedModel("gpt-probe", "Probe"),),
        )

        resp = await agents.api_models(_request(ACP_BACKEND_CODEX))

        assert resp.status == 200
        assert [r["model_name"] for r in json.loads(resp.text)] == ["auto", "gpt-probe"]

    @pytest.mark.asyncio
    async def test_other_failed_checks_stay_pending(self) -> None:
        _record(ACP_BACKEND_CODEX, connect.STATUS_ERROR)

        resp = await agents.api_models(_request(ACP_BACKEND_CODEX))

        assert resp.status == 503
        assert json.loads(resp.text)["code"] == "harness_models_pending"

    @pytest.mark.asyncio
    async def test_a_harness_without_a_published_command_names_none(self) -> None:
        _record(ACP_BACKEND_KIMI, connect.STATUS_NEEDS_LOGIN)

        resp = await agents.api_models(_request(ACP_BACKEND_KIMI))

        body = json.loads(resp.text)
        assert body["code"] == "auth_required"
        assert body["login"] == ""
