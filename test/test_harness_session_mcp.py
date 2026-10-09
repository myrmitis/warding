"""Managed MCP servers for docked harnesses (harness-parity H16).

A spec-family harness reads no Warding agent spec, so the ``mcpServers`` array of
``session/new`` / ``session/load`` is the only way ``warding-core`` and
``warding-cron`` reach it. These tests pin who gets them (an opt-in membership
set), what the entries look like (the ACP stdio shape both adapters accept, with
the caller's identity and no pre-authorization key), and that the Kiro path is
byte-identical.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from warding import agent
from warding.acp.client import AcpClient
from warding.acp.types import (
    ACP_BACKEND_AUTO,
    ACP_BACKEND_CLAUDE,
    ACP_BACKEND_CODEX,
    ACP_BACKEND_KAS,
    ACP_BACKEND_KIRO,
    ACP_BACKENDS_KNOWN,
    ACP_BACKENDS_MANAGED_MCP,
    ACP_BACKENDS_SPEC_FAMILY,
)

# Absolute on every host: a POSIX-style literal has no drive letter, so Windows does not
# treat it as absolute and the builder (rightly) refuses it.
_BIN = str(Path(sys.executable).resolve().parent / "warding")
_MEMBERS = sorted(ACP_BACKENDS_MANAGED_MCP)
_NON_MEMBERS = sorted(ACP_BACKENDS_KNOWN - ACP_BACKENDS_MANAGED_MCP)
_ENTRY_KEYS = {"name", "command", "args", "env"}
_ALLOWED_ENV = {"WARDING_HOME", "WARDING_SESSION_KEY", "WARDING_CHANNEL_ID"}


@pytest.fixture(autouse=True)
def _resolved_launcher(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the launcher so the entries do not depend on how this checkout is installed."""
    monkeypatch.setattr(agent, "_warding_mcp_invocation", lambda sub: (_BIN, [sub]))


def _client(backend: str, tmp_path: Path, **kwargs: object) -> AcpClient:
    return AcpClient(work_dir=tmp_path, acp_backend=backend, **kwargs)  # type: ignore[arg-type]


def _env_of(entry: dict) -> dict[str, str]:
    return {pair["name"]: pair["value"] for pair in entry["env"]}


# ---------------------------------------------------------------------------
# Who gets the servers
# ---------------------------------------------------------------------------


def test_membership_is_claude_and_codex_only() -> None:
    assert ACP_BACKENDS_MANAGED_MCP == frozenset({ACP_BACKEND_CLAUDE, ACP_BACKEND_CODEX})


@pytest.mark.parametrize("backend", _MEMBERS)
def test_members_get_exactly_the_two_managed_entries(backend: str, tmp_path: Path) -> None:
    client = _client(backend, tmp_path, session_key="sess-1", channel_id="chan-1")

    entries = client._claude_session_mcp_servers()

    assert [e["name"] for e in entries] == ["warding-cron", "warding-core"]
    by_name = {e["name"]: e for e in entries}
    assert by_name["warding-core"]["args"] == ["mcp-core"]
    assert by_name["warding-cron"]["args"] == ["mcp-cron"]
    for entry in entries:
        assert set(entry) == _ENTRY_KEYS
        assert entry["command"] == _BIN
        assert Path(entry["command"]).is_absolute()


@pytest.mark.parametrize("backend", _MEMBERS)
@pytest.mark.parametrize("key", [None, ""])
def test_a_client_without_a_session_key_gets_no_entries(
    backend: str, key: str | None, tmp_path: Path
) -> None:
    """A pre-warmed pool session starts before it has an identity, and ``rekey`` cannot reach
    the servers it already launched, so it gets none rather than tools that refuse every call."""
    client = _client(backend, tmp_path, session_key=key, channel_id="chan-1")

    assert client._claude_session_mcp_servers() == []


@pytest.mark.parametrize("backend", _NON_MEMBERS)
def test_non_members_get_nothing(
    backend: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kiro, KAS, auto and every other spec-family harness stay out until they opt in."""

    def _must_not_be_called(**_: object) -> list:
        raise AssertionError("a non-member must never reach the entry builder")

    monkeypatch.setattr("warding.acp.client.harness_session_mcp_servers", _must_not_be_called)

    assert _client(backend, tmp_path, session_key="sess-1")._claude_session_mcp_servers() == []


def test_the_non_member_sweep_covers_kiro_kas_and_every_other_spec_harness() -> None:
    assert {ACP_BACKEND_KIRO, ACP_BACKEND_KAS, ACP_BACKEND_AUTO} <= set(_NON_MEMBERS)
    assert ACP_BACKENDS_SPEC_FAMILY - ACP_BACKENDS_MANAGED_MCP <= set(_NON_MEMBERS)


# ---------------------------------------------------------------------------
# What the entries carry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("backend", _MEMBERS)
def test_entries_carry_the_callers_identity(
    backend: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WARDING_HOME", str(tmp_path / "home"))
    client = _client(backend, tmp_path, session_key="sess-1", channel_id="chan-1")

    for entry in client._claude_session_mcp_servers():
        env = _env_of(entry)
        assert env["WARDING_SESSION_KEY"] == "sess-1"
        assert env["WARDING_CHANNEL_ID"] == "chan-1"
        assert env["WARDING_HOME"] == str(tmp_path / "home")
        # ACP env is a list of name/value pairs; a mapping would be skipped by Codex.
        assert all(set(pair) == {"name", "value"} for pair in entry["env"])


def test_identity_is_per_client_and_nothing_is_shared(tmp_path: Path) -> None:
    first = _client(ACP_BACKEND_CLAUDE, tmp_path, session_key="sess-a")
    second = _client(ACP_BACKEND_CLAUDE, tmp_path, session_key="sess-b")

    a = first._claude_session_mcp_servers()
    b = second._claude_session_mcp_servers()

    assert {_env_of(e)["WARDING_SESSION_KEY"] for e in a} == {"sess-a"}
    assert {_env_of(e)["WARDING_SESSION_KEY"] for e in b} == {"sess-b"}
    a[0]["env"].append({"name": "X", "value": "1"})
    assert all(pair["name"] != "X" for pair in a[1]["env"]), "entries share one env list"


def test_absent_identity_is_omitted_rather_than_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WARDING_HOME", raising=False)

    entries = _client(
        ACP_BACKEND_CLAUDE, tmp_path, session_key="sess-1"
    )._claude_session_mcp_servers()

    assert [e["env"] for e in entries] == [[{"name": "WARDING_SESSION_KEY", "value": "sess-1"}]] * 2


def test_no_secret_or_foreign_variable_can_reach_the_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The env is built from named arguments, never from the process environment."""
    for name in ("SLACK_BOT_TOKEN", "WARDING_OWNER_ID", "ANTHROPIC_API_KEY", "GH_TOKEN"):
        monkeypatch.setenv(name, "must-not-travel")
    client = _client(ACP_BACKEND_CLAUDE, tmp_path, session_key="sess-1", channel_id="chan-1")

    for entry in client._claude_session_mcp_servers():
        assert {pair["name"] for pair in entry["env"]} <= _ALLOWED_ENV
        assert "must-not-travel" not in json.dumps(entry)


@pytest.mark.parametrize("backend", _MEMBERS)
def test_entries_pre_authorize_nothing(backend: str, tmp_path: Path) -> None:
    """No autoApprove (or a type that would make an adapter drop the entry).

    A pre-authorized MCP tool is approved inside the harness and never raises a
    permission request, so the PreToolUse gate would not see it. ``type`` is
    absent because the Claude adapter keeps a stdio entry only when the key is
    missing.
    """
    for entry in _client(backend, tmp_path, session_key="s")._claude_session_mcp_servers():
        text = json.dumps(entry).lower()
        assert "autoapprove" not in text and "auto_approve" not in text
        assert "type" not in entry


# ---------------------------------------------------------------------------
# Which managed servers are eligible
# ---------------------------------------------------------------------------


def _names(entries: list) -> list[str]:
    return [e["name"] for e in entries]


def test_computer_use_is_never_offered_even_with_its_gate_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(agent._MANAGED_MCP_SERVERS["warding-computer"], "spec_gate", lambda: True)

    names = _names(agent.harness_session_mcp_servers(session_key="s"))

    assert "warding-computer" not in names
    assert names == ["warding-cron", "warding-core"]


def test_opt_in_servers_are_never_offered() -> None:
    assert "warding-dashboard" not in _names(agent.harness_session_mcp_servers(session_key="s"))
    assert agent._MANAGED_MCP_SERVERS["warding-dashboard"].get("opt_in") is True


def test_a_closed_spec_gate_withholds_the_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(agent._MANAGED_MCP_SERVERS["warding-core"], "spec_gate", lambda: False)

    assert _names(agent.harness_session_mcp_servers()) == ["warding-cron"]


def test_a_gate_that_raises_is_treated_as_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> bool:
        raise RuntimeError("keystone unreadable")

    monkeypatch.setitem(agent._MANAGED_MCP_SERVERS["warding-cron"], "spec_gate", _boom)

    assert _names(agent.harness_session_mcp_servers()) == ["warding-core"]


def test_a_row_marked_opt_in_later_is_withheld(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(agent._MANAGED_MCP_SERVERS["warding-cron"], "opt_in", True)

    assert _names(agent.harness_session_mcp_servers()) == ["warding-core"]


def test_the_allowlist_names_only_always_on_rows_that_exist() -> None:
    for name in agent._HARNESS_SESSION_MCP_SERVERS:
        spec = agent._MANAGED_MCP_SERVERS[name]
        assert not spec.get("opt_in")
        assert "spec_gate" not in spec


# ---------------------------------------------------------------------------
# An unresolvable launcher degrades to no tools, never to a failed session
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "invocation",
    [
        # python -m warding puts the project directory on sys.path
        (sys.executable, ["-m", "warding", "mcp-core"]),
        # the unresolved sentinel
        ("warding", ["mcp-core"]),
    ],
)
def test_unresolved_launcher_yields_nothing_and_warns(
    invocation: tuple[str, list[str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(agent, "_warding_mcp_invocation", lambda sub: invocation)
    caplog.set_level(logging.WARNING, logger="warding.agent")

    entries = _client(ACP_BACKEND_CLAUDE, tmp_path, session_key="s")._claude_session_mcp_servers()

    assert entries == []
    assert any("absolute standalone warding launcher" in r.getMessage() for r in caplog.records)


def test_unwrapped_windows_shim_invocation_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """``-P -s -m warding`` keeps the working directory off sys.path, so it is safe."""
    monkeypatch.setattr(
        agent,
        "_warding_mcp_invocation",
        lambda sub: (sys.executable, ["-P", "-s", "-m", "warding", sub]),
    )

    entries = agent.harness_session_mcp_servers()

    assert _names(entries) == ["warding-cron", "warding-core"]


def test_a_resolver_that_raises_never_blocks_session_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def _boom(sub: str) -> tuple[str, list[str]]:
        raise OSError("launcher vanished")

    monkeypatch.setattr(agent, "_warding_mcp_invocation", _boom)
    caplog.set_level(logging.WARNING, logger="warding.acp.client")

    entries = _client(ACP_BACKEND_CLAUDE, tmp_path, session_key="s")._claude_session_mcp_servers()

    assert entries == []
    assert any("Managed MCP servers unavailable" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# session/new and session/load carry the entries
# ---------------------------------------------------------------------------


class _Wire:
    """Records every request the client sends and answers the handshake."""

    def __init__(self, client: AcpClient, *, can_load: bool = False) -> None:
        self.sent: list[tuple[str, dict]] = []
        self.can_load = can_load
        proc = MagicMock()
        proc.returncode = None
        client._process = proc
        client._send_request = AsyncMock(side_effect=self._send)  # type: ignore[method-assign]
        client._wait_for_response = AsyncMock(side_effect=self._wait)  # type: ignore[method-assign]
        client._drain_notifications = AsyncMock()  # type: ignore[method-assign]
        self._ids: dict[int, str] = {}

    async def _send(self, method: str, params: dict) -> int:
        self.sent.append((method, params))
        req_id = len(self.sent)
        self._ids[req_id] = method
        return req_id

    async def _wait(self, req_id: int, timeout: float = 50.0, **_: object) -> dict:
        method = self._ids[req_id]
        if method == "initialize":
            return {"protocolVersion": 1, "agentCapabilities": {"loadSession": self.can_load}}
        if method == "session/new":
            return {"sessionId": "new-sess"}
        if method == "session/load":
            return {"modes": []}
        return {}

    def params(self, method: str) -> dict:
        return next(p for m, p in self.sent if m == method)


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", _MEMBERS)
async def test_session_new_carries_the_entries(backend: str, tmp_path: Path) -> None:
    client = _client(backend, tmp_path, session_key="sess-1", channel_id="chan-1")
    wire = _Wire(client)

    await client._initialize_session()

    servers = wire.params("session/new")["mcpServers"]
    assert _names(servers) == ["warding-cron", "warding-core"]
    assert all(_env_of(s)["WARDING_SESSION_KEY"] == "sess-1" for s in servers)


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", _MEMBERS)
async def test_session_load_carries_the_entries(backend: str, tmp_path: Path) -> None:
    """``session/load`` re-initializes the harness's servers, so an empty list would drop them."""
    client = _client(backend, tmp_path, session_key="sess-1", channel_id="chan-1")
    client._resume_session_id = "old-sess"
    wire = _Wire(client, can_load=True)

    await client._initialize_session()

    assert client._resumed is True
    servers = wire.params("session/load")["mcpServers"]
    assert _names(servers) == ["warding-cron", "warding-core"]
    assert all(_env_of(s)["WARDING_SESSION_KEY"] == "sess-1" for s in servers)


@pytest.mark.asyncio
async def test_pooled_stubs_follow_the_managed_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A later same-named entry replaces an earlier one in both adapters' name-keyed maps."""
    client = _client(ACP_BACKEND_CLAUDE, tmp_path, session_key="s")
    wire = _Wire(client)
    stub = {"name": "warding-core", "command": "stub", "args": [], "env": []}
    monkeypatch.setattr(client, "_pooled_mcp_servers", lambda: [stub])

    await client._initialize_session()

    assert wire.params("session/new")["mcpServers"] == [
        *client._claude_session_mcp_servers(),
        stub,
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("can_load", [False, True])
async def test_kiro_session_params_are_unchanged(tmp_path: Path, can_load: bool) -> None:
    """Kiro takes its servers from ``--agent``: the array stays empty, with no new step."""
    client = _client(ACP_BACKEND_KIRO, tmp_path, session_key="sess-1")
    wire = _Wire(client, can_load=can_load)

    await client._initialize_session()

    assert wire.params("session/new")["mcpServers"] == []


@pytest.mark.asyncio
async def test_a_companion_override_still_replaces_the_default(tmp_path: Path) -> None:
    """The seam keeps its contract: an override supplies the whole array."""
    custom = [{"name": "companion", "command": "/x", "args": [], "env": []}]

    class _Companion(AcpClient):
        def _claude_session_mcp_servers(self) -> list:
            return custom

    client = _Companion(work_dir=tmp_path, acp_backend=ACP_BACKEND_CLAUDE, session_key="s")
    wire = _Wire(client)

    await client._initialize_session()

    assert wire.params("session/new")["mcpServers"] == custom
