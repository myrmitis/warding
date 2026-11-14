"""Fail-closed invariants: a gate that delivers no verdict refuses the call.

Each test injects one fault at one decision point and asserts a deny with a logged
reason on a turn that is not marked attended, through the gate's public entry
point (``HookManager.on_tool_call``, ``run_script_hook``, ``load_security_policy``).
"""

from __future__ import annotations

import asyncio
import logging
import platform
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import warding.hooks as hooks_mod
import warding.platform.governance_profiles as gp
from warding.hooks import (
    HOOK_EVENT_PRE_TOOL_USE,
    TOOL_DENY,
    HookManager,
    ScriptHook,
    Verdict,
    attended_turn,
    run_script_hook,
    script_hook_verdict,
    tool_result_verdict,
)
from warding.platform.context import PlatformCompositionError
from warding.platform.governance import load_security_policy, parse_policy

_CRON_SESSION = "cron:fail-closed:run"


def _boom(*_a, **_k):
    raise RuntimeError("injected fault")


class TestGateWrapper:
    def test_a_raising_decision_point_denies_with_a_logged_reason(self, monkeypatch, caplog):
        monkeypatch.setattr(hooks_mod, "is_sensitive_path", _boom)
        with caplog.at_level(logging.ERROR, logger="warding.hooks"):
            result = HookManager().on_tool_call("code", session_key=_CRON_SESSION)
        assert result.action == TOOL_DENY
        assert "tool gate failed" in result.reason
        assert any("refusing the call" in r.getMessage() for r in caplog.records)

    def test_a_composition_error_at_the_gate_denies(self, monkeypatch):
        def _compose(*_a, **_k):
            raise PlatformCompositionError("cannot compose")

        monkeypatch.setattr(hooks_mod, "is_sensitive_path", _compose)
        result = HookManager().on_tool_call("code", session_key=_CRON_SESSION)
        assert result.action == TOOL_DENY

    def test_none_and_wrong_types_are_not_verdicts(self):
        assert tool_result_verdict(None) is Verdict.UNDECIDED
        assert tool_result_verdict("allow") is Verdict.UNDECIDED


class TestGovernanceUndecided:
    @pytest.fixture(autouse=True)
    def _fault_and_capture(self, monkeypatch):
        self.degrades: list[dict] = []
        monkeypatch.setattr(gp, "resolve_active_scope", _boom)
        monkeypatch.setattr(
            gp,
            "audit_governance_degraded",
            lambda chokepoint, **kw: self.degrades.append({"chokepoint": chokepoint, **kw}),
        )

    def test_unattended_turn_denies_and_audits_a_failed_closed_degrade(self):
        result = HookManager().on_tool_call("code", session_key=_CRON_SESSION)
        assert result.action == TOOL_DENY
        assert "could not be evaluated" in result.reason
        assert self.degrades and self.degrades[0]["failed_closed"] is True

    def test_attended_turn_steps_aside(self):
        with attended_turn(True):
            result = HookManager().on_tool_call("code", session_key="dashboard:s", tool_kind="read")
        assert result.action != TOOL_DENY
        assert self.degrades and self.degrades[0]["failed_closed"] is False

    def test_attended_mark_does_not_outlive_its_block(self):
        with attended_turn(True):
            pass
        result = HookManager().on_tool_call("code", session_key=_CRON_SESSION)
        assert result.action == TOOL_DENY

    def test_script_hook_capability_check_refuses_when_unattended(self, monkeypatch):
        monkeypatch.setattr(gp, "governance_permits", _boom)
        assert hooks_mod._script_hooks_capability_denied(_CRON_SESSION)

    def test_script_hook_capability_check_treats_a_missing_verdict_as_undecided(self, monkeypatch):
        monkeypatch.setattr(gp, "governance_permits", lambda *a, **k: None)
        assert hooks_mod._script_hooks_capability_denied(_CRON_SESSION)


_IS_WINDOWS = platform.system() == "Windows"


class TestScriptHookVerdict:
    @pytest.fixture(autouse=True)
    def _passthrough_sandbox(self, monkeypatch):
        monkeypatch.setattr("warding.sandbox.wrap_argv", lambda argv, **k: (list(argv), None))

    @staticmethod
    def _hook(command: str, timeout: int = 30) -> ScriptHook:
        return ScriptHook(
            id="fc",
            name="fc",
            event=HOOK_EVENT_PRE_TOOL_USE,
            command=command,
            timeout=timeout,
        )

    @pytest.mark.asyncio
    async def test_only_exit_zero_allows_and_only_exit_two_denies(self):
        assert script_hook_verdict(await run_script_hook(self._hook("exit 0"))) is Verdict.ALLOW
        assert script_hook_verdict(await run_script_hook(self._hook("exit 2"))) is Verdict.DENY

    @pytest.mark.asyncio
    async def test_a_failing_hook_delivers_no_verdict(self):
        result = await run_script_hook(self._hook("exit 1"))
        assert script_hook_verdict(result) is Verdict.UNDECIDED

    @pytest.mark.asyncio
    async def test_an_unexecutable_hook_delivers_no_verdict(self):
        result = await run_script_hook(self._hook("warding-no-such-command-for-test"))
        assert script_hook_verdict(result) is Verdict.UNDECIDED

    @pytest.mark.skipif(_IS_WINDOWS, reason="sleep is a POSIX command")
    @pytest.mark.asyncio
    async def test_a_timed_out_hook_delivers_no_verdict(self):
        result = await run_script_hook(self._hook("sleep 30", timeout=1))
        assert result.error.startswith("Timed out")
        assert script_hook_verdict(result) is Verdict.UNDECIDED

    def test_a_missing_or_foreign_result_delivers_no_verdict(self):
        assert script_hook_verdict(None) is Verdict.UNDECIDED
        assert script_hook_verdict(object()) is Verdict.UNDECIDED


class TestPolicyLoader:
    def test_a_misspelled_sandbox_key_raises_instead_of_leaving_the_floor_ungoverned(self):
        body = {"version": 1, "boot": {"fail_closed": True}, "sandbox": {"min_levl": "strict"}}
        with pytest.raises(PlatformCompositionError, match="min_level"):
            parse_policy(body)

    def test_the_two_reserved_sandbox_names_still_load(self):
        body = {
            "version": 1,
            "boot": {"fail_closed": True},
            "sandbox": {"min_level": "cc", "require_isolation": True},
        }
        assert parse_policy(body).get("sandbox.min_level") is not None

    def test_any_loader_failure_is_a_composition_error(self, monkeypatch):
        monkeypatch.delenv("WARDING_SECURITY_POLICY", raising=False)

        def _bad_bundle():
            raise ValueError("corrupt bundle")

        with pytest.raises(PlatformCompositionError, match="refuses to start"):
            load_security_policy(bundled_loader=_bad_bundle)


class _SpyHooks:
    """Records whether the turn was marked attended when the gate was consulted.

    ``on_tool_call`` may run in a worker thread, so the reading is taken there:
    it proves the marker survives the thread hop and is not merely set on the
    caller's side of it.
    """

    def __init__(self) -> None:
        self.attended: list[bool] = []

    def effective_denied_regexes(self, **_k):
        return []

    def on_tool_call(self, *_a, **_k):
        self.attended.append(hooks_mod.is_attended_turn())
        return hooks_mod.ToolHookResult.allow()


class _Event(SimpleNamespace):
    def __init__(self, **kw):
        super().__init__(
            title="Reading notes.txt",
            tool_kind="read",
            raw_tool_params={"path": "notes.txt"},
            shell_command=None,
            shell_classified=True,
            is_shell=False,
            mcp_server_name="",
            tool_name="",
            tool_input="",
            request_id="req-1",
            options=[],
            **kw,
        )


class _Provider:
    def __init__(self) -> None:
        self.approved: list[str] = []
        self.rejected: list[str] = []

    async def approve_tool(self, request_id, **_kw):
        self.approved.append(request_id)

    async def reject_tool(self, request_id, **_kw):
        self.rejected.append(request_id)


class TestAttendedMarkerPerSurface:
    def test_the_default_context_is_unattended(self):
        assert hooks_mod.is_attended_turn() is False

    @pytest.mark.asyncio
    async def test_the_marker_reaches_a_worker_thread(self):
        spy = _SpyHooks()
        with attended_turn(True):
            await asyncio.to_thread(spy.on_tool_call)
        await asyncio.to_thread(spy.on_tool_call)
        assert spy.attended == [True, False]

    @pytest.mark.asyncio
    async def test_the_cli_chat_gate_is_attended_through_its_thread_hop(self):
        from warding import cli_chat

        spy = _SpyHooks()
        gate = cli_chat._ToolGate(hooks=spy)
        await cli_chat._answer_permission(_Provider(), _Event(), interactive=False, gate=gate)
        assert spy.attended == [True]

    def test_a_channel_gate_is_attended_for_a_person_and_not_for_a_bot(self):
        from warding.messaging.dispatch import build_tool_gate

        for attended in (True, False):
            spy = _SpyHooks()
            builder = SimpleNamespace(hooks=spy)
            gate = build_tool_gate(builder, session_key="slack:c", agent="a", attended=attended)
            gate(_Event())
            assert spy.attended == [attended]

    @pytest.mark.asyncio
    async def test_cron_and_heartbeat_turns_are_never_attended(self):
        from warding.llm_helpers import ToolApprovalPolicy, _resolve_permission

        spy = _SpyHooks()
        with patch("warding.sel.sel", return_value=MagicMock()):
            await _resolve_permission(
                _Provider(),
                _Event(),
                ToolApprovalPolicy.HOOK_BASED,
                hooks=spy,
                session_key=_CRON_SESSION,
            )
        assert spy.attended == [False]


class TestLoadFailureRemedy:
    def test_the_error_text_names_the_file_and_doctor_not_validate(self, tmp_path, monkeypatch):
        policy = tmp_path / "security_policy.json"
        policy.write_text(
            '{"version": 1, "boot": {"fail_closed": true}, "sandbox": {"min_levl": "strict"}}',
            encoding="utf-8",
        )
        monkeypatch.setenv("WARDING_SECURITY_POLICY", str(policy))
        with pytest.raises(PlatformCompositionError) as err:
            load_security_policy()
        message = str(err.value)
        assert str(policy) in message
        assert "warding doctor" in message
        assert "policy validate" not in message

    def test_a_missing_override_file_gets_an_actionable_message(self, tmp_path, monkeypatch):
        missing = tmp_path / "absent.json"
        monkeypatch.setenv("WARDING_SECURITY_POLICY", str(missing))
        with pytest.raises(PlatformCompositionError) as err:
            load_security_policy()
        message = str(err.value)
        assert str(missing) in message
        assert "unset WARDING_SECURITY_POLICY" in message
        assert "warding doctor" in message

    def test_doctor_still_runs_and_reports_it_while_validate_dies_with_the_same_error(
        self, tmp_path
    ):
        import os
        import subprocess
        import sys

        (tmp_path / "security_policy.json").write_text(
            '{"version": 1, "boot": {"fail_closed": true}, "sandbox": {"min_levl": "strict"}}',
            encoding="utf-8",
        )
        import warding

        src_root = str(Path(warding.__file__).resolve().parent.parent)
        env = {**os.environ, "WARDING_HOME": str(tmp_path), "PYTHONPATH": src_root}
        env.pop("WARDING_SECURITY_POLICY", None)

        def run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [sys.executable, "-m", "warding", *args],
                env=env,
                cwd=str(tmp_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
            )

        validate = run("policy", "validate")
        assert validate.returncode != 0
        assert "PlatformCompositionError" in validate.stderr
        doctor = run("doctor")
        assert "composition failed" in doctor.stdout
        assert "sandbox.min_levl" in doctor.stdout
        assert "warding doctor" in doctor.stdout


class _RecordingDriver:
    """Stands in for ``TurnDriver`` and keeps the PreToolUse gate it was handed."""

    gates: list = []

    def __init__(self, *_a, tool_gate=None, **_k) -> None:
        type(self).gates.append(tool_gate)

    async def run(self, _text: str) -> str:
        return ""


@pytest.fixture
def recording_driver():
    _RecordingDriver.gates = []
    return _RecordingDriver


class TestAutomatedChannelTurnsAreUnattended:
    """The gateway's own nudge turns reach the channel dispatchers as synthetic
    inbound messages. The gate each dispatcher builds must see them as unattended,
    and a message a person sends must still be attended."""

    @pytest.mark.asyncio
    async def test_a_discord_nudge_is_unattended_and_a_persons_dm_is_attended(
        self, monkeypatch, recording_driver
    ):
        from test_discord import _dispatcher, _inbound
        from test_slack_gateway_coverage import _discord_orchestrator, _loop

        monkeypatch.setattr("warding.discord.transport_dispatch.TurnDriver", recording_driver)
        dispatcher, _client, _sessions = _dispatcher({"U9"})
        spy = _SpyHooks()
        spy.auto_approve_subagent_spawn = False
        dispatcher.ctx_builder.hooks = spy
        transport = SimpleNamespace(
            dispatcher=dispatcher,
            resolve_conversation=AsyncMock(return_value="DM123"),
        )
        orch = _discord_orchestrator(transport)
        key = dispatcher.current_session_key("U9")

        assert await orch._fire_discord_nudge(_loop(key)) is True
        recording_driver.gates[-1](_Event())
        assert spy.attended == [False]

        await dispatcher.handle_message(_inbound("hello", user_id="U9"))
        recording_driver.gates[-1](_Event())
        assert spy.attended == [False, True]

    @pytest.mark.asyncio
    async def test_a_webex_nudge_is_unattended_and_a_persons_dm_is_attended(
        self, monkeypatch, recording_driver
    ):
        from test_slack_gateway_coverage import _discord_orchestrator, _loop
        from test_webex_dispatch import (
            _EMAIL,
            FakeClient,
            FakeCtx,
            FakeProvider,
            FakeSessions,
            _dispatcher,
            _inbound,
        )

        monkeypatch.setattr("warding.messaging.dispatch.TurnDriver", recording_driver)
        ctx = FakeCtx()
        spy = _SpyHooks()
        spy.auto_approve_subagent_spawn = False
        ctx.hooks = spy
        sessions = FakeSessions(FakeProvider([]))
        sessions.get_origin_link = lambda _key: None  # type: ignore[attr-defined]
        dispatcher = _dispatcher(sessions, ctx, FakeClient())
        transport = SimpleNamespace(
            dispatcher=dispatcher,
            is_authorized=lambda _email: True,
            resolve_conversation=AsyncMock(return_value=_EMAIL),
        )
        orch = _discord_orchestrator(None)
        orch.sessions = sessions
        orch.dashboard_state.channel_transports = {"webex": transport}
        key = dispatcher.current_session_key(_EMAIL)

        assert await orch._fire_webex_nudge(_loop(key)) is True
        recording_driver.gates[-1](_Event())
        assert spy.attended == [False]

        await dispatcher.handle_message(_inbound("hello"))
        recording_driver.gates[-1](_Event())
        assert spy.attended == [False, True]


class TestApiClientTurnsAreUnattended:
    @pytest.mark.asyncio
    async def test_the_openai_compatible_endpoint_never_marks_a_turn_attended(self):
        from test_openai_compat import _make_request, _make_slot, _make_state

        from warding.dashboard.openai_compat import api_completions

        slot = _make_slot()
        state = _make_state(slot)
        request = _make_request(
            {"model": "m", "messages": [{"role": "user", "content": "hi"}], "stream": False}, state
        )
        seen: dict = {}

        async def fake_run_chat(_state, _slot, _prompt, **kwargs):
            seen.update(kwargs)
            slot._pending.append({"role": "assistant", "content": "ok"})
            slot._pending.append({"cls": "done"})
            slot.event.set()

        with patch("warding.dashboard.openai_compat._run_chat", side_effect=fake_run_chat):
            await api_completions(request)
        assert seen["_person_attended"] is False

    def test_only_a_secretless_appless_request_is_a_person_at_the_dashboard(self):
        from warding.dashboard.origin import request_is_dashboard_person

        def request(headers: dict, app: str = ""):
            return SimpleNamespace(headers=headers, get=lambda k, d="": app if k == "app" else d)

        assert request_is_dashboard_person(request({})) is True
        assert request_is_dashboard_person(request({"X-Internal-Secret": "s"})) is False
        assert request_is_dashboard_person(request({}, app="notes")) is False


class TestLinkedThreadFromATrustedBot:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("from_bot", [False, True])
    async def test_a_bot_message_is_neither_a_persons_directive_nor_attended(
        self, monkeypatch, from_bot
    ):
        from warding.slack import handler as h

        slot = MagicMock(key="slot-1", running=False)
        state = MagicMock()
        state.get_linked_slot.return_value = slot
        state._background_tasks = set()
        monkeypatch.setattr(h, "_dashboard_state", state)
        monkeypatch.setattr(h, "is_allowed_user", lambda _u: True)
        seen: dict = {}

        async def fake_run_chat(_state, _slot, _text, **kwargs):
            seen.update(kwargs)

        monkeypatch.setattr("warding.dashboard.chat._run_chat", fake_run_chat)
        routed = await h.maybe_route_linked_thread(
            "do it", "t1", "U1", "C1", MagicMock(), "t1", from_trusted_bot=from_bot
        )
        await asyncio.sleep(0)
        assert routed is True
        assert seen["_directive_user_origin"] is (not from_bot)
        assert seen["_person_attended"] is (not from_bot)


class TestANudgeThatLosesTheRaceIsNeverReplayedAsAttended:
    """A person's turn can start between the fire path's busy check and the
    dispatcher's. The nudge then reaches the busy branch. It must be dropped: a
    queued entry is bare text, and its drain would replay it as a person's turn."""

    @staticmethod
    def _busy_after_the_first_check(sessions):
        calls = {"n": 0}

        def is_busy(_key):
            calls["n"] += 1
            busy = calls["n"] > 1  # idle for the fire path's check, busy afterwards
            sessions._busy = busy  # so ``enqueue`` accepts the entry, as a real busy session does
            return busy

        sessions.is_busy = is_busy

    @pytest.mark.asyncio
    async def test_discord(self, monkeypatch, recording_driver):
        from test_discord import _dispatcher, _inbound
        from test_slack_gateway_coverage import _discord_orchestrator, _loop

        monkeypatch.setattr("warding.discord.transport_dispatch.TurnDriver", recording_driver)
        dispatcher, _client, sessions = _dispatcher({"U9"})
        dispatcher.cfg.messaging.queue_mode = "queue"
        transport = SimpleNamespace(
            dispatcher=dispatcher, resolve_conversation=AsyncMock(return_value="DM123")
        )
        orch = _discord_orchestrator(transport)
        key = dispatcher.current_session_key("U9")
        self._busy_after_the_first_check(sessions)

        await orch._fire_discord_nudge(_loop(key))

        assert sessions.queued == []
        assert recording_driver.gates == []

        sessions._busy = True
        sessions.is_busy = lambda _key: True
        await dispatcher.handle_message(_inbound("hello", user_id="U9"))
        assert [text for _ts, text, _kw in sessions.queued] != []

    @pytest.mark.asyncio
    async def test_webex(self, monkeypatch, recording_driver):
        from test_slack_gateway_coverage import _discord_orchestrator, _loop
        from test_webex_dispatch import (
            _EMAIL,
            FakeClient,
            FakeCtx,
            FakeProvider,
            FakeSessions,
            _cfg_queue,
            _dispatcher,
            _inbound,
        )

        monkeypatch.setattr("warding.messaging.dispatch.TurnDriver", recording_driver)
        sessions = FakeSessions(FakeProvider([]))
        sessions.get_origin_link = lambda _key: None  # type: ignore[attr-defined]
        dispatcher = _dispatcher(sessions, FakeCtx(), FakeClient(), cfg=_cfg_queue())
        transport = SimpleNamespace(
            dispatcher=dispatcher,
            is_authorized=lambda _email: True,
            resolve_conversation=AsyncMock(return_value=_EMAIL),
        )
        orch = _discord_orchestrator(None)
        orch.sessions = sessions
        orch.dashboard_state.channel_transports = {"webex": transport}
        key = dispatcher.current_session_key(_EMAIL)
        self._busy_after_the_first_check(sessions)

        await orch._fire_webex_nudge(_loop(key))

        assert sessions.queued == []
        assert recording_driver.gates == []

        sessions.is_busy = lambda _key: True
        await dispatcher.handle_message(_inbound("hello"))
        assert sessions.queued != []


class TestNestedAttendedTurns:
    def test_an_unattended_block_inside_an_attended_one_is_unattended(self):
        with attended_turn(True):
            assert hooks_mod.is_attended_turn() is True
            with attended_turn(False):
                assert hooks_mod.is_attended_turn() is False
            assert hooks_mod.is_attended_turn() is True
        assert hooks_mod.is_attended_turn() is False
