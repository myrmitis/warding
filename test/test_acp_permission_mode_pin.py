"""H17: an adapted harness is pinned to a mode that asks Warding about tool calls.

``HookManager.on_tool_call`` only decides on a call the harness raises a permission
request for, and the harness's own mode decides whether it does. The mode a session
starts in is the harness default or the user's own settings (Claude Code
``permissions.defaultMode``, Codex ``agent`` / ``agent-full-access``), so the client sets
it over ``session/set_mode`` and refuses to run the session when it cannot.

The tests drive ``AcpClient._initialize_session`` with a scripted backend, the same way
``test_acp_set_mode_all_agents`` does, and read the requests the client sent.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from warding.acp.client import AcpClient, AcpError, AcpTimeoutError
from warding.acp.types import (
    ACP_BACKEND_CLAUDE,
    ACP_BACKEND_CODEX,
    ACP_BACKEND_CURSOR,
    ACP_BACKEND_KAS,
    ACP_BACKEND_KIRO,
    ACP_PERMISSION_MODE_PINS,
    METHOD_INITIALIZE,
    METHOD_SESSION_LOAD,
    METHOD_SESSION_NEW,
    METHOD_SET_MODE,
    JsonRpcMessage,
)

_SESSION_ID = "sess-pin"

#: The mode vocabularies the two pinned adapters advertise.
_CLAUDE_MODES = ["default", "acceptEdits", "plan", "dontAsk"]
_CODEX_MODES = ["read-only", "agent", "agent-full-access"]

_MODEL_SUBSTITUTION_ADVISORY = {
    "code": -32603,
    "message": "Internal error",
    "data": {"details": 'Model "requested" is restricted by policy. Using served instead.'},
}


def _scripted_client(
    backend: str,
    tmp_path,
    *,
    advertised: list[str] | None,
    current: str = "",
    set_mode_error: Exception | None = None,
    resume: bool = False,
) -> tuple[AcpClient, list[tuple[str, dict[str, Any]]]]:
    """A client whose backend answers ``session/new`` with *advertised* modes.

    ``advertised=None`` models an adapter that sends no ``modes`` payload at all.
    ``resume`` makes the backend accept ``session/load`` for a remembered session, so the
    modes arrive on that response instead. Returns the client and the list every request
    is appended to, in order.
    """
    client = AcpClient(work_dir=tmp_path, acp_backend=backend)
    if resume:
        client._resume_session_id = _SESSION_ID
    sent: list[tuple[str, dict[str, Any]]] = []
    by_request: dict[int, str] = {}

    async def fake_send(method: str, params: dict[str, Any] | None = None) -> int:
        request_id = len(sent) + 1
        sent.append((method, params or {}))
        by_request[request_id] = method
        return request_id

    async def fake_wait(
        request_id,
        timeout=50.0,
        *,
        method="",
        expected_mcp=None,
        allow_model_substitution=True,
    ):
        sent_method = by_request[request_id]
        if sent_method == METHOD_INITIALIZE:
            return {"protocolVersion": 1, "agentCapabilities": {"loadSession": resume}}
        if sent_method in (METHOD_SESSION_NEW, METHOD_SESSION_LOAD):
            response: dict[str, Any] = {"sessionId": _SESSION_ID}
            if advertised is not None:
                response["modes"] = {
                    "currentModeId": current,
                    "availableModes": [{"id": mode_id} for mode_id in advertised],
                }
            return response
        if sent_method == METHOD_SET_MODE and set_mode_error is not None:
            raise set_mode_error
        return {"protocolVersion": 1}

    client._send_request = fake_send  # type: ignore[method-assign]
    client._wait_for_response = fake_wait  # type: ignore[method-assign]
    client._drain_notifications = AsyncMock()  # type: ignore[method-assign]
    client._apply_startup_model = AsyncMock()  # type: ignore[method-assign]
    return client, sent


def _set_mode_requests(sent: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    return [params for method, params in sent if method == METHOD_SET_MODE]


class TestClaudeIsPinnedToTheAskingMode:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("started_in", ["acceptEdits", "dontAsk", "plan", ""])
    async def test_a_session_that_started_elsewhere_is_moved_to_default(self, tmp_path, started_in):
        client, sent = _scripted_client(
            ACP_BACKEND_CLAUDE, tmp_path, advertised=_CLAUDE_MODES, current=started_in
        )

        await client._initialize_session()

        assert _set_mode_requests(sent) == [{"sessionId": _SESSION_ID, "modeId": "default"}]

    @pytest.mark.asyncio
    async def test_the_pin_precedes_the_model_and_any_prompt(self, tmp_path):
        client, sent = _scripted_client(
            ACP_BACKEND_CLAUDE, tmp_path, advertised=_CLAUDE_MODES, current="acceptEdits"
        )
        order: list[str] = []
        original_send = client._send_request

        async def recording_send(method, params=None):
            order.append(method)
            return await original_send(method, params)

        async def model_applied():
            order.append("apply_model")

        client._send_request = recording_send  # type: ignore[method-assign]
        client._apply_startup_model = model_applied  # type: ignore[method-assign]

        await client._initialize_session()

        assert order.index(METHOD_SET_MODE) < order.index("apply_model")

    @pytest.mark.asyncio
    async def test_a_session_already_in_default_costs_no_round_trip(self, tmp_path):
        client, sent = _scripted_client(
            ACP_BACKEND_CLAUDE, tmp_path, advertised=_CLAUDE_MODES, current="default"
        )

        await client._initialize_session()

        assert _set_mode_requests(sent) == []

    @pytest.mark.asyncio
    async def test_bypass_permissions_is_never_left_in_place(self, tmp_path):
        client, sent = _scripted_client(
            ACP_BACKEND_CLAUDE,
            tmp_path,
            advertised=[*_CLAUDE_MODES, "bypassPermissions"],
            current="bypassPermissions",
        )

        await client._initialize_session()

        assert _set_mode_requests(sent) == [{"sessionId": _SESSION_ID, "modeId": "default"}]
        assert client._current_mode_id == "default"


class TestAResumedSessionIsPinnedToo:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("backend", "modes", "started_in", "pinned"),
        [
            (ACP_BACKEND_CLAUDE, _CLAUDE_MODES, "acceptEdits", "default"),
            (ACP_BACKEND_CODEX, _CODEX_MODES, "agent-full-access", "read-only"),
        ],
    )
    async def test_session_load_does_not_skip_the_pin(
        self, tmp_path, backend, modes, started_in, pinned
    ):
        """A resumed conversation comes back in the mode its settings name, not the pin."""
        client, sent = _scripted_client(
            backend, tmp_path, advertised=modes, current=started_in, resume=True
        )

        await client._initialize_session()

        assert client._resumed is True
        assert [method for method, _ in sent if method == METHOD_SESSION_LOAD]
        assert _set_mode_requests(sent) == [{"sessionId": _SESSION_ID, "modeId": pinned}]


class TestCodexIsPinnedToTheAskingMode:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("started_in", ["agent", "agent-full-access"])
    async def test_agent_and_full_access_are_moved_to_read_only(self, tmp_path, started_in):
        """``agent`` approves what a model judges safe and ``agent-full-access`` never
        asks; neither reaches Warding's gate for those calls."""
        client, sent = _scripted_client(
            ACP_BACKEND_CODEX, tmp_path, advertised=_CODEX_MODES, current=started_in
        )

        await client._initialize_session()

        assert _set_mode_requests(sent) == [{"sessionId": _SESSION_ID, "modeId": "read-only"}]

    @pytest.mark.asyncio
    async def test_a_session_already_in_read_only_costs_no_round_trip(self, tmp_path):
        client, sent = _scripted_client(
            ACP_BACKEND_CODEX, tmp_path, advertised=_CODEX_MODES, current="read-only"
        )

        await client._initialize_session()

        assert _set_mode_requests(sent) == []


class TestTheSessionFailsClosed:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("backend", [ACP_BACKEND_CLAUDE, ACP_BACKEND_CODEX])
    @pytest.mark.parametrize(
        "wire_error",
        [
            _MODEL_SUBSTITUTION_ADVISORY,
            {"code": -32603, "message": "Invalid Mode"},
            {"code": -32601, "message": "Method not found"},
            {"code": -32602, "message": "Invalid params"},
            {},
            False,
            "",
            0,
            [],
        ],
        ids=[
            "model-advisory",
            "invalid-mode",
            "missing-method",
            "invalid-params",
            "empty-object",
            "false",
            "empty-string",
            "zero",
            "empty-list",
        ],
    )
    async def test_every_wire_error_refuses_the_pin(self, tmp_path, backend, wire_error):
        """Exercise the real response decoder; an advisory cannot confirm a mode change.

        Falsy malformed error payloads are also rejected rather than interpreted as an
        empty successful response. These are scripted wire shapes, not adapter evidence.
        """
        client = AcpClient(work_dir=tmp_path, acp_backend=backend)
        client._session_id = _SESSION_ID
        client._current_mode_id = "unsafe-starting-mode"
        client._send_request = AsyncMock(return_value=1)  # type: ignore[method-assign]
        client._read_message = AsyncMock(  # type: ignore[method-assign]
            return_value=JsonRpcMessage.from_dict({"jsonrpc": "2.0", "id": 1, "error": wire_error})
        )

        with pytest.raises(AcpError, match="Refusing to run"):
            await client._pin_permission_mode(ACP_PERMISSION_MODE_PINS[backend])

        assert client._current_mode_id == "unsafe-starting-mode"
        assert client._last_substitution_model is None
        client._send_request.assert_awaited_once_with(
            METHOD_SET_MODE,
            {"sessionId": _SESSION_ID, "modeId": ACP_PERMISSION_MODE_PINS[backend]},
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("backend", [ACP_BACKEND_CLAUDE, ACP_BACKEND_CODEX])
    async def test_a_wire_success_confirms_the_pin(self, tmp_path, backend):
        client = AcpClient(work_dir=tmp_path, acp_backend=backend)
        client._session_id = _SESSION_ID
        client._current_mode_id = "unsafe-starting-mode"
        client._send_request = AsyncMock(return_value=1)  # type: ignore[method-assign]
        client._read_message = AsyncMock(  # type: ignore[method-assign]
            return_value=JsonRpcMessage.from_dict({"jsonrpc": "2.0", "id": 1, "result": {}})
        )

        await client._pin_permission_mode(ACP_PERMISSION_MODE_PINS[backend])

        assert client._current_mode_id == ACP_PERMISSION_MODE_PINS[backend]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("backend", "advertised", "current"),
        [
            (ACP_BACKEND_CLAUDE, ["acceptEdits", "plan"], "acceptEdits"),
            (ACP_BACKEND_CODEX, ["agent", "agent-full-access"], "agent-full-access"),
            (ACP_BACKEND_CLAUDE, [], ""),
        ],
    )
    async def test_a_backend_that_does_not_offer_the_mode_is_refused(
        self, tmp_path, backend, advertised, current
    ):
        client, sent = _scripted_client(backend, tmp_path, advertised=advertised, current=current)

        with pytest.raises(AcpError, match="Refusing to run"):
            await client._initialize_session()

        assert _set_mode_requests(sent) == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("backend", [ACP_BACKEND_CLAUDE, ACP_BACKEND_CODEX])
    async def test_a_rejected_set_mode_is_refused(self, tmp_path, backend):
        modes = _CLAUDE_MODES if backend == ACP_BACKEND_CLAUDE else _CODEX_MODES
        client, _ = _scripted_client(
            backend,
            tmp_path,
            advertised=modes,
            current=modes[1],
            set_mode_error=AcpError("JSON-RPC error: {'code': -32603, 'message': 'Invalid Mode'}"),
        )

        with pytest.raises(AcpError, match="Refusing to run") as caught:
            await client._initialize_session()

        assert backend in str(caught.value)
        assert client._current_mode_id != ACP_PERMISSION_MODE_PINS[backend]

    @pytest.mark.asyncio
    async def test_a_set_mode_that_never_answers_is_refused(self, tmp_path):
        client, _ = _scripted_client(
            ACP_BACKEND_CLAUDE,
            tmp_path,
            advertised=_CLAUDE_MODES,
            current="acceptEdits",
            set_mode_error=AcpTimeoutError(message="ACP session/set_mode timed out after 30s"),
        )

        with pytest.raises(AcpError, match="Refusing to run"):
            await client._initialize_session()

    @pytest.mark.asyncio
    async def test_an_adapter_that_reports_no_modes_is_still_pinned(self, tmp_path):
        """With nothing advertised the current mode is unknown, so the pin is sent."""
        client, sent = _scripted_client(ACP_BACKEND_CLAUDE, tmp_path, advertised=None)

        await client._initialize_session()

        assert _set_mode_requests(sent) == [{"sessionId": _SESSION_ID, "modeId": "default"}]

    @pytest.mark.asyncio
    async def test_an_adapter_that_reports_no_modes_and_rejects_the_pin_is_refused(self, tmp_path):
        client, _ = _scripted_client(
            ACP_BACKEND_CODEX,
            tmp_path,
            advertised=None,
            set_mode_error=AcpError("JSON-RPC error: method not found"),
        )

        with pytest.raises(AcpError, match="Refusing to run"):
            await client._initialize_session()


class TestOtherHarnessesAreUntouched:
    @pytest.mark.asyncio
    async def test_an_ordinary_wait_keeps_the_model_substitution_advisory(self, tmp_path):
        """The stricter mode-pin contract does not change an ordinary Kiro response wait."""
        client = AcpClient(work_dir=tmp_path, acp_backend=ACP_BACKEND_KIRO)
        client._read_message = AsyncMock(  # type: ignore[method-assign]
            return_value=JsonRpcMessage.from_dict(
                {"jsonrpc": "2.0", "id": 1, "error": _MODEL_SUBSTITUTION_ADVISORY}
            )
        )

        result = await client._wait_for_response(1)

        assert result == {}
        assert client._last_substitution_model == "served"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("backend", [ACP_BACKEND_CURSOR])
    async def test_a_harness_outside_the_mapping_sends_no_set_mode(self, tmp_path, backend):
        client, sent = _scripted_client(
            backend, tmp_path, advertised=["agent", "ask"], current="agent"
        )

        await client._initialize_session()

        assert _set_mode_requests(sent) == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("backend", [ACP_BACKEND_KIRO, ACP_BACKEND_KAS])
    async def test_kiro_family_keeps_only_its_own_agent_activation(self, tmp_path, backend):
        """H13: the Kiro path gains no new request. Its one ``set_mode`` names the agent."""
        client, sent = _scripted_client(
            backend, tmp_path, advertised=["warding"], current="warding"
        )

        await client._initialize_session()

        assert all(
            params["modeId"] not in {"default", "read-only"} for params in _set_mode_requests(sent)
        )


class TestThePinTable:
    def test_only_claude_and_codex_are_pinned(self):
        assert dict(ACP_PERMISSION_MODE_PINS) == {
            ACP_BACKEND_CLAUDE: "default",
            ACP_BACKEND_CODEX: "read-only",
        }

    def test_the_table_cannot_be_edited_at_runtime(self):
        with pytest.raises(TypeError):
            ACP_PERMISSION_MODE_PINS[ACP_BACKEND_KIRO] = "default"  # type: ignore[index]
