"""ACP ``auth_required`` (-32000 "Authentication required") on the handshake.

A spec-family agent that has no account answers ``initialize`` / ``session/new``
with ACP's reserved auth-required error. ``AcpClient`` turns that into the
non-retryable ``AcpAuthRequired`` carrying the harness and its own sign-in
command, instead of a raw JSON-RPC error that ``ensure_ready`` respawns the
process for. kiro-cli and KAS keep the generic behaviour (harness-parity H13).
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from warding.acp.client import (
    AcpAuthRequired,
    AcpClient,
    AcpError,
    _is_acp_auth_required,
    _raise_acp_error,
)
from warding.acp.types import (
    ACP_BACKEND_CLAUDE,
    ACP_BACKEND_CODEX,
    ACP_BACKEND_CURSOR,
    ACP_BACKEND_KAS,
    ACP_BACKEND_KIMI,
    ACP_BACKEND_KIRO,
    ACP_ERROR_AUTH_REQUIRED,
    JsonRpcMessage,
)

AUTH_FRAME: dict[str, Any] = {"code": -32000, "message": "Authentication required"}

# (backend, sign-in command published by the connect setup)
SIGN_IN = [
    (ACP_BACKEND_CLAUDE, "claude auth login"),
    (ACP_BACKEND_CODEX, "codex login"),
    (ACP_BACKEND_CURSOR, "cursor-agent login"),
]


def _client(tmp_path, backend: str) -> AcpClient:
    client = AcpClient(work_dir=tmp_path, acp_backend=backend)
    return client


class _Adapter:
    """Scripted agent: answers each request by method with a result or an error."""

    def __init__(self, client: AcpClient, replies: dict[str, dict[str, Any]]) -> None:
        self.client = client
        self.replies = replies
        self.methods: list[str] = []
        self._next_id = 0
        self._last_method = ""
        self._last_id = 0
        client._send_request = self.send  # type: ignore[method-assign]
        client._read_message = self.read  # type: ignore[method-assign]

    async def send(self, method: str, params: dict) -> int:
        self._next_id += 1
        self._last_id, self._last_method = self._next_id, method
        self.methods.append(method)
        return self._next_id

    async def read(self, timeout: float = 0.0) -> JsonRpcMessage:
        reply = self.replies[self._last_method]
        if "error" in reply:
            return JsonRpcMessage(id=self._last_id, error=reply["error"])
        return JsonRpcMessage(id=self._last_id, result=reply["result"])


def _wire_lifecycle(client: AcpClient) -> list[int]:
    """Replace spawn/kill/reset with counters; return the spawn counter."""
    spawns: list[int] = []

    async def spawn() -> None:
        spawns.append(1)
        client._process = MagicMock()
        client._process.returncode = None

    def reset() -> None:
        client._process = None
        client._session_id = None

    client._spawn = spawn  # type: ignore[method-assign]
    client._kill_process = AsyncMock()  # type: ignore[method-assign]
    client._reset_state = reset  # type: ignore[method-assign]
    client._snapshot_process_tree = AsyncMock()  # type: ignore[method-assign]
    client._drain_notifications = AsyncMock()  # type: ignore[method-assign]
    client._apply_startup_model = AsyncMock()  # type: ignore[method-assign]
    return spawns


INIT_OK = {"result": {"protocolVersion": 1, "agentCapabilities": {}}}
NEW_OK = {"result": {"sessionId": "sid-1", "modes": {}}}


class TestFrameRecognition:
    def test_the_sdk_frame_is_recognised(self) -> None:
        assert _is_acp_auth_required(AUTH_FRAME)

    def test_a_detail_suffix_is_recognised(self) -> None:
        frame = {"code": ACP_ERROR_AUTH_REQUIRED, "message": "Authentication required: expired"}
        assert _is_acp_auth_required(frame)

    @pytest.mark.parametrize(
        "frame",
        [
            {"code": -32603, "message": "Authentication required"},
            {"code": -32000, "message": "backend unavailable"},
            {"code": -32000, "message": "Please note: Authentication required"},
            {"code": -32000},
            {"message": "Authentication required"},
            "Authentication required",
            None,
        ],
    )
    def test_anything_else_is_not(self, frame: object) -> None:
        assert not _is_acp_auth_required(frame)


class TestWaitForResponse:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("backend", "login"), SIGN_IN)
    async def test_spec_family_raises_auth_required(self, tmp_path, backend, login) -> None:
        client = _client(tmp_path, backend)
        client._read_message = AsyncMock(  # type: ignore[method-assign]
            return_value=JsonRpcMessage(id=5, error=AUTH_FRAME)
        )

        with pytest.raises(AcpAuthRequired) as info:
            await client._wait_for_response(5, timeout=5.0)

        exc = info.value
        assert exc.backend == backend
        assert exc.login == login
        assert exc.transient is False
        assert f"`{login}`" in str(exc)
        assert "JSON-RPC" not in str(exc)
        assert "-32000" not in str(exc)

    @pytest.mark.asyncio
    async def test_a_harness_without_a_published_command_names_none(self, tmp_path) -> None:
        """No command is invented, and kiro-cli's is never borrowed."""
        client = _client(tmp_path, ACP_BACKEND_KIMI)
        client._read_message = AsyncMock(  # type: ignore[method-assign]
            return_value=JsonRpcMessage(id=5, error=AUTH_FRAME)
        )

        with pytest.raises(AcpAuthRequired) as info:
            await client._wait_for_response(5, timeout=5.0)

        assert info.value.backend == ACP_BACKEND_KIMI
        assert info.value.login == ""
        assert "kiro-cli" not in str(info.value)
        assert "`" not in str(info.value)

    @pytest.mark.asyncio
    async def test_adapter_detail_never_reaches_the_message_and_the_log_is_redacted(
        self, tmp_path, caplog: pytest.LogCaptureFixture
    ) -> None:
        secret = "AKIAIOSFODNN7EXAMPLE"
        frame = {
            "code": -32000,
            "message": f"Authentication required: key {secret} via https://evil.example/x?token={secret}",
        }
        client = _client(tmp_path, ACP_BACKEND_CODEX)
        client._read_message = AsyncMock(  # type: ignore[method-assign]
            return_value=JsonRpcMessage(id=5, error=frame)
        )

        with caplog.at_level(logging.WARNING, logger="warding.acp.client"):
            with pytest.raises(AcpAuthRequired) as info:
                await client._wait_for_response(5, timeout=5.0)

        assert secret not in str(info.value)
        assert "evil.example" not in str(info.value)  # nothing the adapter wrote is shown
        assert secret not in caplog.text
        assert "reported auth_required" in caplog.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "frame",
        [
            {"code": -32603, "message": "Authentication required"},
            {"code": -32000, "message": "backend unavailable"},
            {"code": -32000, "message": "Please note: Authentication required"},
        ],
    )
    async def test_other_errors_keep_the_generic_error(self, tmp_path, frame) -> None:
        client = _client(tmp_path, ACP_BACKEND_CODEX)
        client._read_message = AsyncMock(  # type: ignore[method-assign]
            return_value=JsonRpcMessage(id=5, error=frame)
        )

        with pytest.raises(AcpError, match="JSON-RPC error") as info:
            await client._wait_for_response(5, timeout=5.0)

        assert not isinstance(info.value, AcpAuthRequired)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("backend", [ACP_BACKEND_KIRO, ACP_BACKEND_KAS])
    async def test_kiro_and_kas_are_unchanged(self, tmp_path, backend) -> None:
        """H13: the frame is the generic JSON-RPC error on the kiro-cli and KAS paths."""
        client = _client(tmp_path, ACP_BACKEND_KIRO)
        client._acp_backend = backend
        client._read_message = AsyncMock(  # type: ignore[method-assign]
            return_value=JsonRpcMessage(id=5, error=AUTH_FRAME)
        )

        with pytest.raises(AcpError, match="JSON-RPC error: ") as info:
            await client._wait_for_response(5, timeout=5.0)

        assert not isinstance(info.value, AcpAuthRequired)


class TestPromptResponse:
    """A credential that expires in a live session is refused on ``session/prompt``.

    The frame arrives through ``_prompt_loop`` and ``_raise_acp_error``, not the
    handshake's ``_wait_for_response``, and must reach the same handler.
    """

    @pytest.mark.parametrize(("backend", "login"), SIGN_IN)
    def test_raise_acp_error_classifies_the_frame(self, backend: str, login: str) -> None:
        with pytest.raises(AcpAuthRequired) as info:
            _raise_acp_error(AUTH_FRAME, ["m1"], backend=backend)

        assert info.value.backend == backend
        assert info.value.login == login
        assert info.value.transient is False
        assert f"`{login}`" in str(info.value)
        assert "session has expired" not in str(info.value)

    @pytest.mark.parametrize(
        "frame",
        [
            {"code": -32603, "message": "Authentication required"},
            {"code": -32000, "message": "backend unavailable"},
            {"code": -32000, "message": "Please note: Authentication required"},
        ],
    )
    def test_other_prompt_errors_keep_their_formatting(self, frame: dict[str, Any]) -> None:
        with pytest.raises(AcpError) as info:
            _raise_acp_error(frame, None, backend=ACP_BACKEND_CODEX)

        assert not isinstance(info.value, AcpAuthRequired)

    @pytest.mark.parametrize("backend", [ACP_BACKEND_KIRO, ACP_BACKEND_KAS, None])
    def test_kiro_kas_and_an_unnamed_backend_are_unchanged(self, backend: str | None) -> None:
        """H13: the runtime path names no backend, and kiro-cli and KAS are not spec-family."""
        with pytest.raises(AcpError) as info:
            _raise_acp_error(AUTH_FRAME, None, backend=backend)

        assert not isinstance(info.value, AcpAuthRequired)
        assert info.value.transient is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("backend", "login"), SIGN_IN)
    async def test_read_prompt_response_raises_auth_required(
        self, tmp_path, backend, login
    ) -> None:
        client = _client(tmp_path, backend)
        client._read_message = AsyncMock(  # type: ignore[method-assign]
            return_value=JsonRpcMessage(id=7, error=AUTH_FRAME)
        )

        with pytest.raises(AcpAuthRequired) as info:
            await client._read_prompt_response(7, 5.0)

        assert info.value.login == login

    @pytest.mark.asyncio
    async def test_send_message_stream_raises_auth_required(self, tmp_path) -> None:
        client = _client(tmp_path, ACP_BACKEND_CODEX)
        client.ensure_ready = AsyncMock()  # type: ignore[method-assign]
        client._send_prompt = AsyncMock(return_value=7)  # type: ignore[method-assign]
        client._read_message = AsyncMock(  # type: ignore[method-assign]
            return_value=JsonRpcMessage(id=7, error=AUTH_FRAME)
        )

        with pytest.raises(AcpAuthRequired):
            async for _chunk in client.send_message_stream("hi"):
                pass

    @pytest.mark.asyncio
    async def test_stream_events_raises_auth_required(self, tmp_path) -> None:
        """The path the dashboard chat takes."""
        client = _client(tmp_path, ACP_BACKEND_CLAUDE)
        client.ensure_ready = AsyncMock()  # type: ignore[method-assign]
        client._send_prompt = AsyncMock(return_value=7)  # type: ignore[method-assign]
        client._read_message = AsyncMock(  # type: ignore[method-assign]
            return_value=JsonRpcMessage(id=7, error=AUTH_FRAME)
        )

        with pytest.raises(AcpAuthRequired) as info:
            async for _event in client.stream_events("hi"):
                pass

        assert info.value.backend == ACP_BACKEND_CLAUDE
        assert info.value.login == "claude auth login"

    @pytest.mark.asyncio
    async def test_a_kiro_cli_client_keeps_the_generic_prompt_error(self, tmp_path) -> None:
        client = _client(tmp_path, ACP_BACKEND_KIRO)
        client.ensure_ready = AsyncMock()  # type: ignore[method-assign]
        client._send_prompt = AsyncMock(return_value=7)  # type: ignore[method-assign]
        client._read_message = AsyncMock(  # type: ignore[method-assign]
            return_value=JsonRpcMessage(id=7, error=AUTH_FRAME)
        )

        with pytest.raises(AcpError) as info:
            async for _event in client.stream_events("hi"):
                pass

        assert not isinstance(info.value, AcpAuthRequired)


class TestEnsureReady:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("backend", "login"), SIGN_IN)
    async def test_refused_session_new_is_one_spawn_and_one_error(
        self, tmp_path, backend, login, caplog: pytest.LogCaptureFixture
    ) -> None:
        client = _client(tmp_path, backend)
        spawns = _wire_lifecycle(client)
        adapter = _Adapter(client, {"initialize": INIT_OK, "session/new": {"error": AUTH_FRAME}})

        with caplog.at_level(logging.WARNING, logger="warding.acp.client"):
            with pytest.raises(AcpAuthRequired) as info:
                await client.ensure_ready()

        assert len(spawns) == 1
        assert adapter.methods == ["initialize", "session/new"]
        assert info.value.backend == backend
        assert info.value.login == login
        assert "retrying with fresh process" not in caplog.text
        client._kill_process.assert_awaited_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("backend", "login"), SIGN_IN)
    async def test_refused_initialize_is_one_spawn_and_one_error(
        self, tmp_path, backend, login
    ) -> None:
        client = _client(tmp_path, backend)
        spawns = _wire_lifecycle(client)
        adapter = _Adapter(client, {"initialize": {"error": AUTH_FRAME}})

        with pytest.raises(AcpAuthRequired) as info:
            await client.ensure_ready()

        assert len(spawns) == 1
        assert adapter.methods == ["initialize"]
        assert info.value.login == login

    @pytest.mark.asyncio
    async def test_a_resume_refused_for_sign_in_still_ends_in_one_spawn(self, tmp_path) -> None:
        """session/load swallows the error and session/new raises it: still one process."""
        client = _client(tmp_path, ACP_BACKEND_CODEX)
        client._resume_session_id = "old-session"
        spawns = _wire_lifecycle(client)
        init = {"result": {"protocolVersion": 1, "agentCapabilities": {"loadSession": True}}}
        _Adapter(
            client,
            {
                "initialize": init,
                "session/load": {"error": AUTH_FRAME},
                "session/new": {"error": AUTH_FRAME},
            },
        )

        with pytest.raises(AcpAuthRequired):
            await client.ensure_ready()

        assert len(spawns) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("backend", "login", "started_in", "modes"),
        [
            (ACP_BACKEND_CLAUDE, "claude auth login", "acceptEdits", ["default", "acceptEdits"]),
            (ACP_BACKEND_CODEX, "codex login", "agent", ["read-only", "agent"]),
        ],
    )
    async def test_a_sign_in_refusal_of_the_permission_pin_keeps_its_own_error(
        self, tmp_path, backend, login, started_in, modes
    ) -> None:
        """H17's fail-closed pin must not re-wrap a sign-in refusal as a generic error.

        The pin's ``set_mode`` is awaited after ``session/new``, so a credential that
        lapses between the two reaches ``_pin_permission_mode``. It still refuses to
        run the session, but as the non-retryable ``AcpAuthRequired`` the sign-in
        card and ``ensure_ready`` key on, not as "Could not set ... permission mode".
        """
        client = _client(tmp_path, backend)
        spawns = _wire_lifecycle(client)
        new = {
            "result": {
                "sessionId": "sid-1",
                "modes": {
                    "currentModeId": started_in,
                    "availableModes": [{"id": mode_id} for mode_id in modes],
                },
            }
        }
        adapter = _Adapter(
            client,
            {
                "initialize": INIT_OK,
                "session/new": new,
                "session/set_mode": {"error": AUTH_FRAME},
            },
        )

        with pytest.raises(AcpAuthRequired) as info:
            await client.ensure_ready()

        assert adapter.methods == ["initialize", "session/new", "session/set_mode"]
        assert len(spawns) == 1
        assert info.value.backend == backend
        assert info.value.login == login
        assert "permission mode" not in str(info.value)

    @pytest.mark.asyncio
    async def test_another_error_is_still_retried_once_on_a_fresh_process(self, tmp_path) -> None:
        """Only the sign-in error skips the retry; every other failure keeps it."""
        client = _client(tmp_path, ACP_BACKEND_CODEX)
        spawns = _wire_lifecycle(client)
        boom = {"code": -32603, "message": "Internal error"}
        _Adapter(client, {"initialize": INIT_OK, "session/new": {"error": boom}})

        with pytest.raises(AcpError, match="JSON-RPC error") as info:
            await client.ensure_ready()

        assert not isinstance(info.value, AcpAuthRequired)
        assert len(spawns) == 2

    @pytest.mark.asyncio
    async def test_kiro_cli_frame_is_still_retried_as_a_generic_error(self, tmp_path) -> None:
        """H13: the same frame on the kiro-cli path keeps its two-spawn behaviour."""
        client = _client(tmp_path, ACP_BACKEND_KIRO)
        spawns = _wire_lifecycle(client)
        _Adapter(client, {"initialize": INIT_OK, "session/new": {"error": AUTH_FRAME}})

        with pytest.raises(AcpError, match="JSON-RPC error") as info:
            await client.ensure_ready()

        assert not isinstance(info.value, AcpAuthRequired)
        assert len(spawns) == 2

    @pytest.mark.asyncio
    async def test_a_signed_in_agent_starts_normally(self, tmp_path) -> None:
        client = _client(tmp_path, ACP_BACKEND_CODEX)
        spawns = _wire_lifecycle(client)
        adapter = _Adapter(
            client,
            {
                "initialize": INIT_OK,
                "session/new": NEW_OK,
                # Codex is pinned to an asking mode before any prompt (H17).
                "session/set_mode": {"result": {}},
            },
        )

        await client.ensure_ready()

        assert len(spawns) == 1
        assert client._session_id == "sid-1"
        assert adapter.methods == ["initialize", "session/new", "session/set_mode"]


class TestExceptionShape:
    def test_existing_raise_sites_keep_their_defaults(self) -> None:
        exc = AcpAuthRequired("kiro-cli is not logged in.")
        assert exc.backend == ACP_BACKEND_KIRO
        assert exc.login == ""
        assert exc.transient is None
        assert isinstance(exc, AcpError)
