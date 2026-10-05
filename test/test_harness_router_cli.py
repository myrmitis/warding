"""Terminal routing behavior, with every harness and filesystem confined to the test."""

from __future__ import annotations

import argparse
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from junction.harness_router import cli, connect, limits
from junction.harness_router.lanes import parse_settings
from junction.harness_router.service import RoutingError


@pytest.fixture
def router(monkeypatch):
    value = MagicMock()
    monkeypatch.setattr(cli, "HarnessRouter", lambda: value)
    monkeypatch.setattr(cli.gc, "collect", lambda: None)
    return value


def args(**changes):
    return argparse.Namespace(
        **dict(
            kind="implement", cwd="test-workspace", no_prompt=True, harness="route", prompt="work"
        )
        | changes
    )


def test_command_parser_and_status_dispatch(router, monkeypatch):
    parser = argparse.ArgumentParser()
    cli.add_arguments(parser)
    parsed = parser.parse_args(["run", "hello", "--no-prompt", "-k", "review"])
    assert parsed.kind == "review" and parsed.no_prompt and parsed.harness == "route"
    assert parser.parse_args(["check", "one", "two"]).lanes == ["one", "two"]
    printer = MagicMock()
    monkeypatch.setattr(cli, "_print_status", printer)
    cli.run_route_command(argparse.Namespace(route_action=None))
    printer.assert_called_once_with(router, as_json=False)


@pytest.mark.parametrize("action", ["run", "check"])
@pytest.mark.parametrize("code", [0, 1])
def test_dispatch_warms_the_sandbox_and_propagates_failure(router, monkeypatch, action, code):
    warm = MagicMock()
    monkeypatch.setattr(cli, "_warm_sandbox_probe", warm)
    run = MagicMock(return_value=code)
    check = AsyncMock(return_value=code)
    monkeypatch.setattr(cli, "_run_sync", run)
    monkeypatch.setattr(cli, "_check", check)
    command = argparse.Namespace(route_action=action, lanes=["codex"])
    if code:
        with pytest.raises(SystemExit) as caught:
            cli.run_route_command(command)
        assert caught.value.code == code
    else:
        cli.run_route_command(command)
    warm.assert_called_once_with()
    if action == "run":
        run.assert_called_once_with(router, command)
    else:
        check.assert_awaited_once_with(router, ["codex"])


def test_other_dispatches_and_unknown_action(router, monkeypatch, capsys):
    pick, initialize = MagicMock(), MagicMock()
    monkeypatch.setattr(cli, "_print_pick", pick)
    monkeypatch.setattr(cli, "_init", initialize)
    cli.run_route_command(
        argparse.Namespace(route_action="pick", kind="test", prefer="codex", as_json=True)
    )
    pick.assert_called_once_with(router, "test", prefer="codex", as_json=True)
    cli.run_route_command(argparse.Namespace(route_action="init", force=False, all_harnesses=True))
    initialize.assert_called_once_with(router, force=False, all_harnesses=True)
    router.ledger.clear_cooldown.return_value = ["codex"]
    cli.run_route_command(argparse.Namespace(route_action="clear", lane="codex"))
    router.ledger.clear_cooldown.assert_called_once_with("codex")
    assert "cleared: codex" in capsys.readouterr().out
    router.ledger.clear_cooldown.return_value = []
    cli.run_route_command(argparse.Namespace(route_action="clear", lane=""))
    assert "nothing was resting" in capsys.readouterr().out
    with pytest.raises(SystemExit) as caught:
        cli.run_route_command(argparse.Namespace(route_action="unknown"))
    assert caught.value.code == 2
    assert "unknown route action" in capsys.readouterr().err


def test_status_reports_lane_readiness_and_error_without_hiding_disabled_lanes(
    router, capsys, monkeypatch
):
    monkeypatch.setattr(cli.time, "time", lambda: 1000)
    base = dict(
        id="ready",
        harness="codex",
        billing="subscription",
        enabled=True,
        installed=True,
        cooldown_until=0,
        cooldown_reason="",
        window_limit=0,
        window_used=2,
        day_used=3,
        model="",
        last_error="",
    )
    status = dict(
        enabled=True,
        source="config",
        path="routing.json",
        warnings=["check config"],
        lanes=[
            base,
            base | {"id": "disabled", "enabled": False},
            base | {"id": "missing", "installed": False},
            base
            | {
                "id": "resting",
                "cooldown_until": 4660,
                "cooldown_reason": "usage_limit",
                "model": "served",
                "last_error": "limit",
            },
        ],
        unrouted_installed=["grok"],
        kinds=["test", "review"],
        preview={"test": "ready"},
    )
    router.status.return_value = status
    cli._print_status(router, as_json=True)
    assert json.loads(capsys.readouterr().out) == status
    cli._print_status(router, as_json=False)
    out = capsys.readouterr().out
    for text in (
        "check config",
        "disabled",
        "not installed",
        "resting 1h01m",
        "model=served",
        "last error: limit",
        "grok",
        "(none)",
    ):
        assert text in out
    router.status.return_value = status | {
        "enabled": False,
        "source": "auto",
        "path": "",
        "lanes": [],
    }
    cli._print_status(router, as_json=False)
    out = capsys.readouterr().out
    assert "OFF" in out and "auto-detected" in out and "No lanes" in out
    assert cli._fmt_until(1065) == "1m05s"
    assert cli._fmt_until(900) == "0m00s"


def test_pick_reports_ranked_exclusions_and_no_lane(router, capsys, monkeypatch):
    monkeypatch.setattr(cli.time, "time", lambda: 1000)
    lane = SimpleNamespace(id="codex", billing="subscription")
    decision = SimpleNamespace(
        lane=lane,
        reason="headroom",
        candidates=[
            SimpleNamespace(
                lane=lane,
                score=1.0,
                affinity=1.0,
                headroom=0.5,
                excluded="cooldown",
                cooldown_until=1065,
                note="usage_limit",
            )
        ],
        to_dict=lambda: {"lane": "codex"},
    )
    router.decide.return_value = decision
    cli._print_pick(router, "review", prefer="codex", as_json=True)
    assert json.loads(capsys.readouterr().out) == {"lane": "codex"}
    router.decide.assert_called_with("review", prefer=["codex"])
    cli._print_pick(router, "review", prefer="", as_json=False)
    out = capsys.readouterr().out
    assert "pick: codex" in out and "resting 1m05s" in out and "50%" in out
    decision.lane = None
    decision.candidates[0].excluded = ""
    cli._print_pick(router, "review", prefer="", as_json=False)
    assert "no lane: headroom" in capsys.readouterr().out


def test_warm_probe_and_provider_factory_stay_on_selected_harness(monkeypatch):
    from junction import sandbox
    from junction.config import JunctionConfig, loader

    warm = MagicMock(side_effect=RuntimeError("no backend"))
    monkeypatch.setattr(sandbox, "warm_backend", warm)
    cli._warm_sandbox_probe()
    warm.assert_called_once_with()
    factory = MagicMock(return_value="provider")
    monkeypatch.setattr(JunctionConfig, "load", lambda: "config")
    build = MagicMock(return_value=factory)
    monkeypatch.setattr(loader, "build_provider_factory", build)
    lane = SimpleNamespace(model="served", harness="codex")
    assert cli._make_provider(lane, "workspace") == "provider"
    build.assert_called_once_with("config")
    assert factory.call_args.args[0].startswith(cli.RUN_SESSION_PREFIX + ":")
    assert factory.call_args.kwargs == dict(
        agent="junction", cwd="workspace", model_override="served", acp_backend_override="codex"
    )


@pytest.mark.asyncio
async def test_stream_outputs_text_and_routes_permissions_through_gate(monkeypatch, capsys):
    from junction import cli_chat
    from junction.providers.base import EVENT_COMPLETE, EVENT_PERMISSION_REQUEST, EVENT_TEXT_CHUNK

    permission = SimpleNamespace(kind=EVENT_PERMISSION_REQUEST)

    async def stream(prompt):
        assert prompt == "hello"
        for event in [
            SimpleNamespace(kind=EVENT_TEXT_CHUNK, text="answer"),
            permission,
            permission,
            SimpleNamespace(kind=EVENT_COMPLETE),
            SimpleNamespace(kind=EVENT_TEXT_CHUNK, text="after complete"),
        ]:
            yield event

    provider = SimpleNamespace(stream=stream)
    gate = MagicMock(return_value="gate")
    answer = AsyncMock()
    monkeypatch.setattr(cli_chat, "_build_tool_gate", gate)
    monkeypatch.setattr(cli_chat, "_answer_permission", answer)
    progress = cli._TurnProgress()
    reply = await cli._stream_once(provider, "hello", interactive=False, progress=progress)
    assert reply == "answer"
    assert progress.produced is True
    assert capsys.readouterr().out == "answer\n"
    gate.assert_called_once_with("junction")
    assert answer.await_count == 2
    answer.assert_awaited_with(provider, permission, interactive=False, gate="gate")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,routed,move",
    [
        (limits.FAILURE_USAGE_LIMIT, True, True),
        (limits.FAILURE_OTHER, True, False),
        (limits.FAILURE_USAGE_LIMIT, False, False),
    ],
)
async def test_run_moves_only_routed_lane_failures_and_shuts_down_each_provider(
    router, monkeypatch, failure, routed, move
):
    lane = SimpleNamespace(id="first", label="First", model="", harness="codex")
    second = SimpleNamespace(id="second", label="Second", model="", harness="grok")
    router.resolve.return_value = SimpleNamespace(lane=lane, routed=routed, decision=None)
    router.settings.return_value = SimpleNamespace(max_failover=1)
    router.record_failure.return_value = failure
    router.next_lane.return_value = second
    first_provider = SimpleNamespace(start=AsyncMock(), shutdown=AsyncMock())
    second_provider = SimpleNamespace(
        start=AsyncMock(), shutdown=AsyncMock(side_effect=RuntimeError("closed"))
    )
    factory = MagicMock(side_effect=[first_provider, second_provider])
    monkeypatch.setattr(cli, "_make_provider", factory)
    stream = AsyncMock(side_effect=[RuntimeError("failed"), "done"])
    monkeypatch.setattr(cli, "_stream_once", stream)
    assert await cli._run(router, args()) == (0 if move else 1)
    first_provider.shutdown.assert_awaited_once()
    if move:
        router.next_lane.assert_called_once_with("implement", ["first", "second"])
        assert router.record_dispatch.call_count == 2
        second_provider.shutdown.assert_awaited_once()
        router.record_success.assert_called_once_with("second", harness="grok")
    else:
        router.next_lane.assert_not_called()
        router.record_success.assert_not_called()


@pytest.mark.asyncio
async def test_notice_only_run_fails_and_resolution_errors_are_usage_errors(router, monkeypatch):
    router.resolve.side_effect = RoutingError("no lane", code="no_lane")
    assert await cli._run(router, args()) == 2
    router.record_dispatch.assert_not_called()
    router.resolve.side_effect = None
    lane = SimpleNamespace(id="codex", label="Codex", harness="codex")
    router.resolve.return_value = SimpleNamespace(
        lane=lane, routed=True, decision=SimpleNamespace(reason="best")
    )
    router.settings.return_value = SimpleNamespace(max_failover=0)
    router.record_failure.return_value = limits.FAILURE_USAGE_LIMIT
    provider = SimpleNamespace(start=AsyncMock(), shutdown=AsyncMock())
    monkeypatch.setattr(cli, "_make_provider", lambda *_: provider)
    monkeypatch.setattr(cli, "_stream_once", AsyncMock(return_value="You've hit your usage limit."))
    assert await cli._run(router, args()) == 1
    assert isinstance(router.record_failure.call_args.kwargs["exc"], limits.HarnessLaneFailure)
    router.next_lane.assert_not_called()
    provider.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancelled_run_is_not_recorded_as_a_lane_failure(router, monkeypatch):
    lane = SimpleNamespace(id="codex", label="Codex", harness="codex")
    router.resolve.return_value = SimpleNamespace(lane=lane, routed=True, decision=None)
    router.settings.return_value = SimpleNamespace(max_failover=1)
    provider = SimpleNamespace(
        start=AsyncMock(side_effect=cli.asyncio.CancelledError()), shutdown=AsyncMock()
    )
    monkeypatch.setattr(cli, "_make_provider", lambda *_: provider)
    with pytest.raises(cli.asyncio.CancelledError):
        await cli._run(router, args())
    router.record_failure.assert_not_called()
    provider.shutdown.assert_awaited_once()


def test_sync_keyboard_interrupt_returns_shell_interrupt_code(router, monkeypatch):
    async def interrupted(*_):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_run", interrupted)
    assert cli._run_sync(router, args()) == 130


@pytest.mark.asyncio
async def test_check_filters_disabled_lanes_records_probes_and_prints_setup(
    router, monkeypatch, capsys
):
    settings = parse_settings(
        {
            "lanes": [
                {"id": "codex", "harness": "codex"},
                {"id": "grok", "harness": "grok"},
                {"id": "claude", "harness": "claude", "enabled": False},
            ]
        }
    )
    router.settings.return_value = settings
    router.installed.return_value = {"codex": "bin"}
    probe = AsyncMock(
        side_effect=[
            connect.ProbeResult("codex", connect.STATUS_NEEDS_LOGIN, detail="login"),
            connect.ProbeResult("grok", connect.STATUS_NOT_INSTALLED),
        ]
    )
    monkeypatch.setattr(connect, "probe_harness", probe)
    assert await cli._check(router, []) == 1
    out = capsys.readouterr().out
    assert "log in:" in out and "install:" in out
    assert router.probes.save.call_count == 2
    probe.reset_mock(side_effect=True)
    probe.return_value = connect.ProbeResult("codex", connect.STATUS_CONNECTED, models=3)
    assert await cli._check(router, ["codex"]) == 0
    assert "3 models" in capsys.readouterr().out
    assert await cli._check(router, ["missing"]) == 1
    assert "no lanes to check" in capsys.readouterr().out


def test_init_preserves_existing_config_unless_forced_and_disables_uninstalled_lanes(
    router, monkeypatch, tmp_path, capsys
):
    path = tmp_path / "routing.json"
    monkeypatch.setattr(cli, "routing_path", lambda: path)
    router.installed.return_value = {"codex": "bin"}
    cli._init(router, force=False, all_harnesses=False)
    assert [row["harness"] for row in json.loads(path.read_text(encoding="utf-8"))["lanes"]] == [
        "codex"
    ]
    original = path.read_bytes()
    with pytest.raises(SystemExit):
        cli._init(router, force=False, all_harnesses=True)
    assert path.read_bytes() == original
    cli._init(router, force=True, all_harnesses=True)
    rows = json.loads(path.read_text(encoding="utf-8"))["lanes"]
    assert len(rows) > 1
    assert all(row["enabled"] == (row["harness"] == "codex") for row in rows)
    assert "wrote" in capsys.readouterr().out
