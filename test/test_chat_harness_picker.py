"""The chat harness picker: the advertised list, the config write, the slot label.

Settings > Agents & plans offers every harness a new chat may start on, writes the
choice to ``agent.acp_backend``, and the composer names the harness a chat runs
on. These tests pin the three backend halves and that the Kiro harness keeps its
own treatment (H1, H13).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from warding.acp.types import (
    ACP_BACKEND_AUTO,
    ACP_BACKEND_CLAUDE,
    ACP_BACKEND_CODEX,
    ACP_BACKEND_KIRO,
    ACP_BACKENDS_SELECTABLE,
)
from warding.dashboard.state import DashboardState
from warding.harness_router.connect import ProbeResult
from warding.harness_router.lanes import backend_for_harness, harness_identity
from warding.harness_router.service import HarnessRouter

NOW = 1_800_000_000.0


def _router(tmp_path: Path, binaries: dict[str, str]) -> HarnessRouter:
    return HarnessRouter(home=tmp_path, which=binaries.get, env={})


_CLAUDE_AND_CODEX = {"claude": "/b/claude", "codex": "/b/codex", "npx": "/b/npx"}


def _ids(view: dict[str, Any]) -> list[str]:
    return [choice["id"] for choice in view["choices"]]


def _by_id(view: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {choice["id"]: choice for choice in view["choices"]}


# ── The advertised list ──


def test_choices_are_auto_then_featured_then_kiro(tmp_path: Path) -> None:
    view = _router(tmp_path, _CLAUDE_AND_CODEX).chat_view(ACP_BACKEND_AUTO)
    assert _ids(view) == ["auto", "claude", "codex", "cursor", "grok", "opencode", "kiro"]
    assert view["configured"] == "auto"
    # ``auto`` resolves by the provider factory's own rule: first installed.
    assert view["selected"] == "claude"


def test_auto_names_its_own_target_whichever_harness_is_configured(tmp_path: Path) -> None:
    router = _router(tmp_path, _CLAUDE_AND_CODEX)
    # Configured for Codex: a new chat runs Codex, but ``auto`` would still pick Claude Code.
    view = router.chat_view(ACP_BACKEND_CODEX)
    assert view["selected"] == "codex"
    assert _by_id(view)["auto"]["resolves_to"] == "claude"
    # Nothing installed: ``auto`` has no target, said as "".
    assert _by_id(_router(tmp_path, {}).chat_view(ACP_BACKEND_AUTO))["auto"]["resolves_to"] == ""


def test_installed_state_and_sign_in_status_per_choice(tmp_path: Path) -> None:
    router = _router(tmp_path, _CLAUDE_AND_CODEX)
    router.probes.save(ProbeResult("claude", "connected", models=3, checked_at=NOW))
    router.probes.save(ProbeResult("codex", "needs_login", detail="x", checked_at=NOW))
    by = _by_id(router.chat_view(ACP_BACKEND_AUTO))
    assert (by["claude"]["installed"], by["claude"]["status"]) == (True, "connected")
    assert (by["codex"]["installed"], by["codex"]["status"]) == (True, "needs_login")
    # Never probed: unknown, not a guess in either direction.
    router.probes.save(ProbeResult("claude", "unknown"))
    assert _by_id(router.chat_view(ACP_BACKEND_AUTO))["claude"]["status"] == "unknown"
    # A missing harness is not_installed whatever an old probe recorded.
    router.probes.save(ProbeResult("cursor", "connected", checked_at=NOW))
    assert _by_id(router.chat_view(ACP_BACKEND_AUTO))["cursor"] == {
        **by["cursor"],
        "installed": False,
        "status": "not_installed",
    }


def test_sign_in_command_comes_from_the_backend(tmp_path: Path) -> None:
    by = _by_id(_router(tmp_path, _CLAUDE_AND_CODEX).chat_view(ACP_BACKEND_AUTO))
    assert by["codex"]["setup"]["login"] == "codex login"
    assert by["claude"]["setup"]["login"] == "claude auth login"
    # A harness with no setup entry carries the runtime's own hint instead.
    assert by["kiro"]["setup"] is None and by["kiro"]["hint"]


def test_kiro_is_always_offered_even_on_an_empty_host(tmp_path: Path) -> None:
    view = _router(tmp_path, {}).chat_view(ACP_BACKEND_AUTO)
    kiro = _by_id(view)["kiro"]
    assert kiro["id"] == "kiro" and kiro["label"] == "Kiro CLI"
    assert kiro["installed"] is False and kiro["status"] == "not_installed"
    # Nothing installed: ``auto`` has nothing to resolve to, said as "" not a guess.
    assert view["selected"] == ""


def test_kiro_configured_is_spelled_kiro_not_empty(tmp_path: Path) -> None:
    view = _router(tmp_path, _CLAUDE_AND_CODEX).chat_view(ACP_BACKEND_KIRO)
    assert view["configured"] == "kiro" and view["selected"] == "kiro"
    assert "" not in _ids(view)


def test_every_choice_is_a_selectable_backend(tmp_path: Path) -> None:
    router = _router(tmp_path, {**_CLAUDE_AND_CODEX, "goose": "/b/goose", "kimi": "/b/kimi"})
    for configured in (ACP_BACKEND_AUTO, ACP_BACKEND_KIRO, "kas", "goose"):
        for choice in router.chat_view(configured)["choices"]:
            assert backend_for_harness(choice["id"]) in ACP_BACKENDS_SELECTABLE


def test_a_name_outside_the_selectable_set_is_never_offered(tmp_path: Path) -> None:
    router = _router(tmp_path, _CLAUDE_AND_CODEX)
    # An installed set carrying a name the loader would degrade to ``auto``.
    view = router.chat_view(ACP_BACKEND_AUTO, installed=("claude", "not-a-harness"), probes={})
    assert "not-a-harness" not in _ids(view)


def test_other_installed_harnesses_are_listed_after_the_featured_ones(tmp_path: Path) -> None:
    router = _router(tmp_path, {**_CLAUDE_AND_CODEX, "goose": "/b/goose"})
    ids = _ids(router.chat_view(ACP_BACKEND_AUTO))
    assert ids.index("goose") > ids.index("opencode")
    assert _by_id(router.chat_view(ACP_BACKEND_AUTO))["goose"]["installed"] is True


def test_the_configured_harness_is_listed_even_when_the_host_cannot_tell(tmp_path: Path) -> None:
    router = _router(tmp_path, _CLAUDE_AND_CODEX)
    view = router.chat_view("kas")
    kas = _by_id(view)["kas"]
    # KAS is outside the runtime registry: no install probe, so neither claim.
    assert kas["installed"] is None
    assert view["configured"] == "kas" and view["selected"] == "kas"


def test_an_explicit_harness_is_selected_as_configured_even_when_missing(tmp_path: Path) -> None:
    view = _router(tmp_path, {"claude": "/b/claude"}).chat_view(ACP_BACKEND_CODEX)
    assert view["selected"] == "codex"
    assert _by_id(view)["codex"]["installed"] is False


@pytest.mark.asyncio
async def test_harnesses_endpoint_carries_the_chat_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from aiohttp.test_utils import make_mocked_request

    from warding import planes
    from warding.harness_router import api

    monkeypatch.setattr(api, "get_router", lambda: _router(tmp_path, _CLAUDE_AND_CODEX))
    monkeypatch.setattr(planes, "configured_backend", lambda: ACP_BACKEND_CODEX)
    body = json.loads((await api.api_harnesses(make_mocked_request("GET", "/"))).body)
    assert body["chat"]["configured"] == "codex"
    assert body["chat"]["choices"][0]["id"] == "auto"
    # The rows the page already renders are untouched.
    assert [row["harness"] for row in body["harnesses"]][:2] == ["claude", "codex"]


# ── The config write ──


def _patch_app() -> web.Application:
    from warding.dashboard.handlers import api_warding_config_patch

    app = web.Application()
    app.router.add_patch("/api/config/warding", api_warding_config_patch)
    refresh = AsyncMock()
    app["state"] = SimpleNamespace(sessions=SimpleNamespace(refresh_defaults=refresh))
    return app


@pytest.fixture
def tmp_config(tmp_path: Path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"agent": {"approval_mode": "auto"}}), encoding="utf-8")
    with patch("warding.config.loader.config_path", return_value=cfg_path):
        yield cfg_path


async def _set(client: TestClient, value: Any) -> Any:
    return await client.patch(
        "/api/config/warding", json={"path": "agent.acp_backend", "value": value}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["codex", "claude", "auto", "kiro", "kas"])
async def test_a_selectable_harness_is_written(tmp_config: Path, value: str) -> None:
    app = _patch_app()
    async with TestClient(TestServer(app)) as client:
        resp = await _set(client, value)
        assert resp.status == 200
    data = json.loads(tmp_config.read_text(encoding="utf-8"))
    # The config writer stores the Kiro harness as its backend id, the empty string.
    assert data["agent"]["acp_backend"] == (ACP_BACKEND_KIRO if value == "kiro" else value)
    # The sibling keys survive, and the running gateway adopts the value now.
    assert data["agent"]["approval_mode"] == "auto"
    app["state"].sessions.refresh_defaults.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["not-a-harness", "Codex", "kiro-cli", "claude-code", " "])
async def test_an_unknown_harness_is_refused_with_a_code_and_nothing_written(
    tmp_config: Path, value: str
) -> None:
    before = tmp_config.read_text(encoding="utf-8")
    app = _patch_app()
    async with TestClient(TestServer(app)) as client:
        resp = await _set(client, value)
        body = await resp.json()
    assert resp.status == 400
    assert body["code"] == "unknown_harness" and body["error"]
    assert tmp_config.read_text(encoding="utf-8") == before
    app["state"].sessions.refresh_defaults.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, 3, ["codex"], True])
async def test_a_non_string_value_is_refused_with_the_same_code(
    tmp_config: Path, value: Any
) -> None:
    async with TestClient(TestServer(_patch_app())) as client:
        resp = await _set(client, value)
        body = await resp.json()
    assert resp.status == 400 and body["code"] == "unknown_harness"


@pytest.mark.asyncio
async def test_the_validator_is_the_one_config_set_uses(tmp_config: Path) -> None:
    from warding.config.loader import resolve_acp_backend_override

    async with TestClient(TestServer(_patch_app())) as client:
        for value in sorted(ACP_BACKENDS_SELECTABLE) + ["kiro", "nope"]:
            try:
                resolve_acp_backend_override(value)
                accepted = True
            except ValueError:
                accepted = False
            resp = await _set(client, value)
            assert (resp.status == 200) is accepted, value


@pytest.mark.asyncio
async def test_a_failed_adoption_does_not_fail_a_write_that_landed(tmp_config: Path) -> None:
    app = _patch_app()
    app["state"].sessions.refresh_defaults.side_effect = RuntimeError("factory build failed")
    async with TestClient(TestServer(app)) as client:
        resp = await _set(client, "codex")
        assert resp.status == 200
    assert json.loads(tmp_config.read_text(encoding="utf-8"))["agent"]["acp_backend"] == "codex"


@pytest.mark.asyncio
async def test_refusals_of_other_keys_still_carry_no_code(tmp_config: Path) -> None:
    """Only a key whose spec names a ``code`` gains one; every other body is as it was."""
    async with TestClient(TestServer(_patch_app())) as client:
        resp = await client.patch(
            "/api/config/warding", json={"path": "agent.approval_mode", "value": "bogus"}
        )
        body = await resp.json()
    assert resp.status == 400 and "code" not in body


def test_provider_stays_the_acp_only_enum() -> None:
    """The harness is chosen at ``agent.acp_backend``; ``agent.provider`` is never it (H2)."""
    from warding.dashboard.handlers.core import _EDITABLE_CONFIG

    assert _EDITABLE_CONFIG["agent.provider"] == {"type": "enum", "values": ["acp"]}
    assert _EDITABLE_CONFIG["agent.acp_backend"]["type"] == "str"


# ── The harness label on a slot ──


def _state(tmp_path: Path) -> Any:
    from warding.dashboard.state import DashboardState
    from warding.history import ConversationLog

    sessions = MagicMock(count=0)
    sessions.get_slack_link = MagicMock(return_value=(None, None))
    sessions.get_mirror_link = MagicMock(return_value=None)
    sessions.mirror_accepts_inbound = MagicMock(return_value=False)
    return DashboardState(
        sessions=sessions,
        crons=MagicMock(list_jobs=MagicMock(return_value=[]), status=MagicMock(return_value={})),
        lessons=MagicMock(load_all=MagicMock(return_value=[])),
        start_time=0.0,
        conversation_log=ConversationLog(base_dir=tmp_path),
    )


def test_a_slot_with_no_turn_has_no_harness_label(tmp_path: Path) -> None:
    state = _state(tmp_path)
    assert state.serialize_slot(state.get_or_create_slot("s1"))["harness"] is None


@pytest.mark.parametrize(
    ("backend", "expected"),
    [
        (ACP_BACKEND_CLAUDE, {"id": "claude", "label": "Claude Code"}),
        (ACP_BACKEND_CODEX, {"id": "codex", "label": "Codex (ChatGPT)"}),
        (ACP_BACKEND_KIRO, {"id": "kiro", "label": "Kiro CLI"}),
        (ACP_BACKEND_AUTO, None),
        (None, None),
    ],
)
def test_the_slot_label_names_the_recorded_backend(
    tmp_path: Path, backend: str | None, expected: dict[str, str] | None
) -> None:
    state = _state(tmp_path)
    slot = state.get_or_create_slot("s1")
    slot._harness_backend = backend
    assert state.serialize_slot(slot)["harness"] == expected
    assert harness_identity(backend) == expected


def _provider_on(backend: str) -> Any:
    from warding.providers.acp import AcpProvider

    provider = MagicMock(spec=AcpProvider)
    provider.client = SimpleNamespace(backend=backend)
    return provider


def _manager(targeted: Any) -> Any:
    """A stand-in for the state the helper reads: the manager's targeted backend, and the push."""
    sessions = SimpleNamespace(targeted_backend=targeted)
    return SimpleNamespace(sessions=sessions, push_slots_update=MagicMock())


def test_a_live_provider_names_its_own_backend_not_the_configured_one() -> None:
    from warding.dashboard.chat_runner import _note_slot_harness
    from warding.dashboard.state import _ChatSlot

    slot = _ChatSlot("s1")
    # The gateway is configured for Claude Code now; this chat started on Codex.
    state = _manager(lambda: ACP_BACKEND_CLAUDE)
    _note_slot_harness(state, slot, _provider_on(ACP_BACKEND_CODEX))
    assert slot._harness_backend == ACP_BACKEND_CODEX


def test_a_session_that_failed_to_start_is_labelled_with_the_backend_it_targeted() -> None:
    from warding.dashboard.chat_runner import _note_slot_harness
    from warding.dashboard.state import _ChatSlot

    slot = _ChatSlot("s1")
    state = _manager(lambda: ACP_BACKEND_CODEX)
    _note_slot_harness(state, slot, None)
    assert slot._harness_backend == ACP_BACKEND_CODEX


def test_an_unresolved_auto_that_spawned_nothing_is_not_labelled_at_all() -> None:
    from warding.dashboard.chat_runner import _note_slot_harness
    from warding.dashboard.state import _ChatSlot

    slot = _ChatSlot("s1")
    slot._harness_backend = ACP_BACKEND_CODEX  # an earlier session on Codex ended
    # ``auto`` with no installed runtime: nothing was attempted, so nothing is named.
    _note_slot_harness(_manager(lambda: None), slot, None)
    assert slot._harness_backend is None
    assert harness_identity(slot._harness_backend) is None


def test_a_provider_that_cannot_name_its_backend_clears_the_label() -> None:
    from warding.dashboard.chat_runner import _note_slot_harness
    from warding.dashboard.state import _ChatSlot

    slot = _ChatSlot("s1")
    slot._harness_backend = ACP_BACKEND_CODEX
    # Not guessed from config: the label states what runs, and the old session is over.
    _note_slot_harness(_manager(lambda: ACP_BACKEND_CLAUDE), slot, object())
    assert slot._harness_backend is None


def test_recording_a_harness_never_fails_a_turn() -> None:
    from warding.dashboard.chat_runner import _note_slot_harness
    from warding.dashboard.state import _ChatSlot

    def boom() -> str:
        raise RuntimeError("config unreadable")

    slot = _ChatSlot("s1")
    state = _manager(boom)
    _note_slot_harness(state, slot, None)
    assert slot._harness_backend is None
    state.push_slots_update.assert_not_called()

    # A push that raises must not mask the turn's own outcome either.
    pushing = _manager(lambda: ACP_BACKEND_CODEX)
    pushing.push_slots_update.side_effect = RuntimeError("no websocket")
    _note_slot_harness(pushing, slot, None)


def test_a_new_harness_is_pushed_once_and_an_unchanged_one_is_not() -> None:
    from warding.dashboard.chat_runner import _note_slot_harness
    from warding.dashboard.state import _ChatSlot

    slot = _ChatSlot("s1")
    state = _manager(lambda: ACP_BACKEND_CODEX)
    # The browser's snapshot predates the session, so the change is published now.
    _note_slot_harness(state, slot, _provider_on(ACP_BACKEND_CLAUDE))
    state.push_slots_update.assert_called_once_with()
    # The next turn on the same session changes nothing, so nothing is re-sent.
    _note_slot_harness(state, slot, _provider_on(ACP_BACKEND_CLAUDE))
    state.push_slots_update.assert_called_once_with()
    # A session on another harness is a change again.
    _note_slot_harness(state, slot, _provider_on(ACP_BACKEND_CODEX))
    assert state.push_slots_update.call_count == 2


# SessionManager.targeted_backend: what a cold start spawns, never the routing fallback.


def _manager_on(configured: str) -> Any:
    from warding.session import SessionManager

    manager = object.__new__(SessionManager)
    manager._cfg = SimpleNamespace(agent=SimpleNamespace(acp_backend=configured))
    manager._backend_resolution = None
    return manager


def test_targeted_backend_is_the_configured_harness_when_it_is_named() -> None:
    assert _manager_on(ACP_BACKEND_CODEX).targeted_backend() == ACP_BACKEND_CODEX
    # kiro-cli is the empty string, and an answer rather than "unknown".
    assert _manager_on(ACP_BACKEND_KIRO).targeted_backend() == ACP_BACKEND_KIRO


def test_targeted_backend_resolves_auto_the_way_the_provider_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from warding.acp import runtimes

    monkeypatch.setattr(
        runtimes, "select_runtime", lambda requested, **kw: SimpleNamespace(id="claude")
    )
    assert _manager_on(ACP_BACKEND_AUTO).targeted_backend() == "claude"


def test_targeted_backend_is_none_for_auto_with_nothing_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from warding.acp import runtimes

    def nothing_installed(requested: str, **kw: Any) -> Any:
        raise runtimes.RuntimeNotFoundError("No ACP runtime found.")

    monkeypatch.setattr(runtimes, "select_runtime", nothing_installed)
    manager = _manager_on(ACP_BACKEND_AUTO)
    assert manager.targeted_backend() is None
    # The routing answer for the same host is kiro-cli, the fallback the label must
    # not borrow: no kiro-cli was ever started for it.
    monkeypatch.setattr(runtimes, "resolve_backend", lambda configured, **kw: ACP_BACKEND_KIRO)
    assert manager.resolved_backend() == ACP_BACKEND_KIRO


def test_targeted_backend_is_none_for_an_unreadable_config() -> None:
    from warding.session import SessionManager

    manager = object.__new__(SessionManager)
    manager._cfg = SimpleNamespace()
    assert manager.targeted_backend() is None


# The label through the real turn and the eager spawn.


def _turn_state(tmp_path: Path, targeted: Any, provider: Any) -> tuple[Any, Any]:
    from chat_test_helpers import _make_state

    state = _make_state(tmp_path)
    state.sessions.get_or_create = (
        AsyncMock(side_effect=provider)
        if isinstance(provider, BaseException)
        else AsyncMock(return_value=(provider, False, False))
    )
    state.sessions.release = MagicMock()
    state.sessions.reset = AsyncMock()
    state.sessions.set_approval_policy = MagicMock()
    state.sessions.check_context_usage = MagicMock()
    state.sessions.get_slack_link = MagicMock(return_value=(None, None))
    state.sessions.record_failure = AsyncMock()
    state.sessions.targeted_backend = MagicMock(return_value=targeted)
    state.broadcast_ws = MagicMock()
    state.push_slots_update = MagicMock()
    state.is_yolo_active = MagicMock(return_value=False)
    state._background_tasks = set()
    slot = state.get_or_create_slot("harness-slot")
    slot.append("user", "hello", "msg msg-u")
    return state, slot


@pytest.mark.asyncio
async def test_a_turn_publishes_its_harness_before_the_response_ends(tmp_path: Path) -> None:
    from warding.dashboard.chat_runner import _run_chat

    client = MagicMock()
    client.shutdown = AsyncMock()
    state, slot = _turn_state(tmp_path, ACP_BACKEND_CLAUDE, client)
    seen: dict[str, Any] = {}

    async def _stream(msg: Any) -> Any:
        # Inside the live turn, as a long response would be.
        seen["backend"] = slot._harness_backend
        seen["pushed"] = state.push_slots_update.call_count
        return
        yield  # pragma: no cover - generator shape only

    client.stream = _stream
    client.stream_command = _stream
    with patch("warding.dashboard.chat_runner.provider_backend", return_value=ACP_BACKEND_CODEX):
        await _run_chat(state, slot, "test message")
    assert seen["backend"] == ACP_BACKEND_CODEX
    assert seen["pushed"] >= 1


@pytest.mark.asyncio
async def test_a_failed_start_on_a_named_harness_is_labelled_with_it(tmp_path: Path) -> None:
    from warding.dashboard.chat_runner import _run_chat

    state, slot = _turn_state(tmp_path, ACP_BACKEND_CODEX, RuntimeError("Authentication required"))
    await _run_chat(state, slot, "test message")
    assert slot._harness_backend == ACP_BACKEND_CODEX
    assert state.serialize_slot(slot)["harness"] == {"id": "codex", "label": "Codex (ChatGPT)"}


@pytest.mark.asyncio
async def test_a_failed_start_with_no_runtime_is_not_labelled_kiro(tmp_path: Path) -> None:
    from warding.dashboard.chat_runner import _run_chat

    # ``auto`` with nothing installed: get_or_create raises before any provider exists.
    state, slot = _turn_state(tmp_path, None, RuntimeError("No ACP runtime found."))
    await _run_chat(state, slot, "test message")
    assert slot._harness_backend is None
    assert state.serialize_slot(slot)["harness"] is None


def _eager_state(slot: Any, provider: Any, *, is_new: bool = True) -> Any:
    state = MagicMock(spec=DashboardState)
    state.get_slot = MagicMock(return_value=slot)
    state.sessions = MagicMock()
    state.sessions.get_or_create = AsyncMock(return_value=(provider, is_new, False))
    state.sessions.release = MagicMock()
    state.sessions.remove = AsyncMock()
    state.sessions.reset = AsyncMock()
    state.sessions.resumable_hint = MagicMock(return_value=False)
    return state


def _eager_cfg() -> Any:
    cfg = MagicMock()
    cfg.session.eager_spawn = True
    return MagicMock(return_value=cfg)


async def _run_eager(state: Any, slot: Any) -> None:
    from warding.dashboard import chat_runner

    bindings = MagicMock()
    bindings.kiro_agent = "warding"
    bindings.model = ""
    with (
        patch.object(chat_runner, "_EAGER_SPAWN_DEBOUNCE_SECS", 0),
        patch.object(chat_runner.WardingConfig, "load", _eager_cfg()),
        patch.object(chat_runner, "resolve_agent_bindings", return_value=bindings),
    ):
        await chat_runner._eager_spawn(state, slot)


@pytest.mark.asyncio
async def test_an_eager_session_that_survives_publishes_its_harness() -> None:
    from warding.dashboard.state import _ChatSlot

    slot = _ChatSlot("eager")
    state = _eager_state(slot, _provider_on(ACP_BACKEND_CLAUDE))
    await _run_eager(state, slot)
    assert slot._harness_backend == ACP_BACKEND_CLAUDE
    # The browser's snapshot predates the handshake, so it is sent now.
    state.push_slots_update.assert_called_once_with()


@pytest.mark.asyncio
async def test_an_eager_session_removed_for_a_deleted_slot_is_not_labelled() -> None:
    from warding.dashboard.state import _ChatSlot

    slot = _ChatSlot("eager")
    state = _eager_state(slot, _provider_on(ACP_BACKEND_CLAUDE))

    async def _create_then_delete(*a: Any, **kw: Any) -> Any:
        state.get_slot = MagicMock(return_value=None)
        return (_provider_on(ACP_BACKEND_CLAUDE), True, False)

    state.sessions.get_or_create = AsyncMock(side_effect=_create_then_delete)
    await _run_eager(state, slot)
    state.sessions.remove.assert_awaited_once()
    assert slot._harness_backend is None
    state.push_slots_update.assert_not_called()


@pytest.mark.asyncio
async def test_an_eager_session_removed_for_changed_bindings_is_not_labelled() -> None:
    from warding.dashboard.state import _ChatSlot

    slot = _ChatSlot("eager")
    slot.project = "/w/a"
    state = _eager_state(slot, None)

    async def _create_then_switch(*a: Any, **kw: Any) -> Any:
        slot.project = "/w/b"
        return (_provider_on(ACP_BACKEND_CLAUDE), True, False)

    state.sessions.get_or_create = AsyncMock(side_effect=_create_then_switch)
    await _run_eager(state, slot)
    state.sessions.remove.assert_awaited_once()
    assert slot._harness_backend is None
    state.push_slots_update.assert_not_called()


@pytest.mark.asyncio
async def test_a_lost_eager_race_leaves_the_label_to_the_winner() -> None:
    from warding.dashboard.state import _ChatSlot

    slot = _ChatSlot("eager")
    state = _eager_state(slot, _provider_on(ACP_BACKEND_CLAUDE), is_new=False)
    await _run_eager(state, slot)
    assert slot._harness_backend is None
    state.push_slots_update.assert_not_called()


# ── The Kiro harness keeps its own path (H1, H13) ──


def test_the_kiro_slot_label_is_the_same_shape_as_any_other() -> None:
    from warding.dashboard.chat_runner import _note_slot_harness
    from warding.dashboard.state import _ChatSlot

    slot = _ChatSlot("s1")
    state = _manager(lambda: ACP_BACKEND_CODEX)
    _note_slot_harness(state, slot, _provider_on(ACP_BACKEND_KIRO))
    # Kiro's backend is the empty string: recorded as a value, not read as "unknown".
    assert slot._harness_backend == ACP_BACKEND_KIRO
    assert harness_identity(slot._harness_backend) == {"id": "kiro", "label": "Kiro CLI"}


def test_provider_backend_answers_for_both_provider_shapes() -> None:
    from warding.acp.session_provider import AcpSessionProvider
    from warding.providers.acp import provider_backend

    shared = MagicMock(spec=AcpSessionProvider)
    shared.backend = ACP_BACKEND_KIRO
    assert provider_backend(shared) == ACP_BACKEND_KIRO
    assert provider_backend(_provider_on(ACP_BACKEND_CODEX)) == ACP_BACKEND_CODEX
    assert provider_backend(MagicMock()) is None
    assert provider_backend(None) is None


def test_the_picker_adds_no_branch_to_the_kiro_construction_path() -> None:
    """The picker only reads and writes ``agent.acp_backend``: the factory is untouched.

    ``create_provider_factory`` keeps one signature and no ``chat``/``picker``
    argument, and the loader's normalisation (``kiro`` -> kiro-cli, unknown ->
    ``auto``) is the one the picker's validator mirrors rather than replaces.
    """
    import inspect

    from warding.config import loader

    params = inspect.signature(loader.WardingConfig.create_provider_factory).parameters
    assert not any("chat" in name or "picker" in name for name in params)
    assert loader._normalize_acp_backend("kiro") == ACP_BACKEND_KIRO
    assert loader._normalize_acp_backend("not-a-harness") == ACP_BACKEND_AUTO
    assert loader.resolve_acp_backend_override("kiro") == ACP_BACKEND_KIRO
