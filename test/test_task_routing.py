"""Task-runner steps routed through the harness router (routing.json route_tasks).

Pins the rules in ``junction.task_routing`` and their wiring in
``task_executor``: a step asks the router for a lane, runs on that lane's
harness and model, keeps it across ordinary retries, and leaves it on a
lane-level failure — for free before any tool ran, at the cost of an attempt
after. Every dispatch and outcome lands in the routing ledger. With routing off
(the default) nothing changes: no override reaches the session layer.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from junction import task_executor
from junction.acp.client import AcpError, AcpProcessDied
from junction.harness_router import service
from junction.harness_router.service import HarnessRouter
from junction.providers.base import EVENT_COMPLETE, EVENT_TEXT_CHUNK, EVENT_TOOL_CALL, LLMEvent
from junction.task_models import SESSION_PREFIX, Project, Task
from junction.task_routing import (
    CONFIGURED_AGENT_LANE,
    LANE_UNAVAILABLE,
    LaneBinding,
    StepRoute,
    route_tasks_enabled,
)

_BINS = {"claude": "/b/claude", "codex": "/b/codex", "npx": "/b/npx", "grok": "/b/grok"}
_USAGE_LIMIT = "You've hit your usage limit. Try again in 3 hours."


def _router(tmp_path: Path, *, route_tasks: bool = True, harnesses=("codex", "claude")) -> Any:
    lanes = [{"id": h, "harness": h} for h in harnesses]
    doc = {"enabled": True, "max_failover": 2, "route_tasks": route_tasks, "lanes": lanes}
    (tmp_path / "routing.json").write_text(json.dumps(doc), encoding="utf-8")
    return HarnessRouter(home=tmp_path, which=_BINS.get, env={})


@pytest.fixture
def router(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    r = _router(tmp_path)
    monkeypatch.setattr(service, "get_router", lambda: r)
    return r


# ── StepRoute ──


@pytest.mark.asyncio
async def test_a_step_takes_the_best_lane_for_its_kind_and_keeps_it(router: Any) -> None:
    route = StepRoute("", router=router)  # unnamed kind routes as implement
    first = await route.pick()
    assert first.harness == "codex"
    assert (await route.pick()).id == first.id  # sticky across attempts
    assert router.ledger.snapshot()["codex"].count_since(0) == 2  # one dispatch per attempt
    review = await StepRoute("review", router=router).pick()
    assert review.harness == "claude"


@pytest.mark.asyncio
async def test_sticky_retry_refuses_a_lane_at_its_daily_cap(tmp_path: Path) -> None:
    document = {
        "lanes": [{"id": "codex", "harness": "codex", "daily_limit": 1}],
    }
    (tmp_path / "routing.json").write_text(json.dumps(document), encoding="utf-8")
    router = HarnessRouter(home=tmp_path, which=_BINS.get, env={})
    route = StepRoute("implement", router=router)
    first = await route.pick()
    assert not await route.failed(RuntimeError("tests failed"), tool_ran=True)
    with pytest.raises(service.RoutingError) as error:
        await route.pick()
    assert error.value.code == "daily_cap"
    assert route.lane is first
    assert router.ledger.snapshot()[first.id].count_since(0) == 1


@pytest.mark.asyncio
async def test_parallel_steps_reserve_usage_before_the_next_choice(
    router: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio
    import threading

    doc = json.loads((router.home / "routing.json").read_text(encoding="utf-8"))
    for lane in doc["lanes"]:
        lane["window_limit"] = 1
    (router.home / "routing.json").write_text(json.dumps(doc), encoding="utf-8")
    original = router.resolve
    parallel = threading.Barrier(2)

    def slow_resolve(*args, **kwargs):
        resolution = original(*args, **kwargs)
        # Concurrent resolvers share a snapshot; a reserved dispatch prevents
        # the second resolver from entering until this bounded wait completes.
        try:
            parallel.wait(timeout=1)
        except threading.BrokenBarrierError:
            pass
        return resolution

    monkeypatch.setattr(router, "resolve", slow_resolve)
    lanes = await asyncio.gather(*(StepRoute("implement", router=router).pick() for _ in range(2)))
    assert {lane.id for lane in lanes} == {"codex", "claude"}
    assert all(usage.count_since(0) == 1 for usage in router.ledger.snapshot().values())


@pytest.mark.asyncio
async def test_a_limit_before_any_tool_is_a_free_move(router: Any) -> None:
    route = StepRoute("implement", router=router)
    await route.pick()
    assert await route.failed(RuntimeError(_USAGE_LIMIT), tool_ran=False) is True
    assert route.lane is None
    moved = await route.pick()
    assert moved.harness == "claude"
    assert router.ledger.snapshot()["codex"].cooldown_reason == "usage_limit"


@pytest.mark.asyncio
async def test_a_limit_after_tool_use_releases_the_lane_but_costs_an_attempt(
    router: Any,
) -> None:
    route = StepRoute("implement", router=router)
    await route.pick()
    assert await route.failed(RuntimeError(_USAGE_LIMIT), tool_ran=True) is False
    assert route.lane is None  # the next attempt still moves
    assert (await route.pick()).harness == "claude"


@pytest.mark.asyncio
async def test_an_ordinary_failure_stays_on_the_lane(router: Any) -> None:
    route = StepRoute("implement", router=router)
    lane = await route.pick()
    assert await route.failed(ValueError("tests still red"), tool_ran=False) is False
    assert route.lane is lane
    assert not router.ledger.snapshot()["codex"].cooling(time.time())


@pytest.mark.asyncio
async def test_free_moves_are_bounded_by_max_failover(tmp_path: Path) -> None:
    router = _router(tmp_path, harnesses=("codex", "claude", "grok"))
    doc = json.loads((tmp_path / "routing.json").read_text(encoding="utf-8"))
    doc["max_failover"] = 1
    (tmp_path / "routing.json").write_text(json.dumps(doc), encoding="utf-8")
    route = StepRoute("implement", router=router)
    await route.pick()
    assert await route.failed(RuntimeError(_USAGE_LIMIT), tool_ran=False) is True
    await route.pick()
    assert await route.failed(RuntimeError(_USAGE_LIMIT), tool_ran=False) is False


@pytest.mark.asyncio
async def test_exhausted_lanes_do_not_retry_the_configured_agent(tmp_path: Path) -> None:
    router = _router(tmp_path, harnesses=("codex",))
    route = StepRoute("implement", router=router)
    await route.pick()
    await route.failed(RuntimeError(_USAGE_LIMIT), tool_ran=False)
    with pytest.raises(service.RoutingError, match="No eligible task lane remains"):
        await route.pick()


@pytest.mark.asyncio
async def test_initially_no_eligible_lane_runs_unrouted(tmp_path: Path) -> None:
    router = _router(tmp_path, harnesses=("codex",))
    router.record_failure("codex", exc=RuntimeError(_USAGE_LIMIT))
    assert await StepRoute("implement", router=router).pick() is None


@pytest.mark.asyncio
async def test_a_review_prefers_another_agent_but_accepts_the_same_one(tmp_path: Path) -> None:
    router = _router(tmp_path)
    assert (await StepRoute("review", router=router, avoid=["claude"]).pick()).harness == "codex"
    solo_home = tmp_path / "solo"
    solo_home.mkdir()
    alone = _router(solo_home, harnesses=("claude",))
    assert (await StepRoute("review", router=alone, avoid=["claude"]).pick()).harness == "claude"


def test_route_tasks_is_off_unless_switched_on(tmp_path: Path, monkeypatch) -> None:
    off = _router(tmp_path, route_tasks=False)
    monkeypatch.setattr(service, "get_router", lambda: off)
    assert route_tasks_enabled() is False
    on_home = tmp_path / "on"
    on_home.mkdir()
    on = _router(on_home, route_tasks=True)
    monkeypatch.setattr(service, "get_router", lambda: on)
    assert route_tasks_enabled() is True


# ── execute_task wiring ──


class _Client:
    """One scripted turn per instance: raise, or run a tool, reply and complete."""

    def __init__(
        self, error: Exception | None = None, *, tool: bool = False, reply: str = ""
    ) -> None:
        self._error = error
        self._tool = tool
        self._reply = reply

    async def stream(self, _prompt: str):
        if self._tool:
            yield LLMEvent(kind=EVENT_TOOL_CALL, title="edit")
        if self._error is not None:
            raise self._error
        if self._reply:
            yield LLMEvent(kind=EVENT_TEXT_CHUNK, text=self._reply)
        yield LLMEvent(kind=EVENT_COMPLETE)


def _sessions(clients: list[_Client]) -> MagicMock:
    sessions = MagicMock()
    opened: list[dict[str, Any]] = []

    async def _open(_parent: str, _key: str, **kwargs: Any):
        opened.append(kwargs)
        return clients.pop(0), True, False

    sessions.open_task_session = _open
    sessions.opened = opened
    sessions.record_success = MagicMock()
    sessions.record_failure = AsyncMock()
    sessions.check_context_usage = MagicMock()
    sessions.release = MagicMock()
    sessions.reset = AsyncMock()
    return sessions


def _quiet_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(task_executor, "check_context", AsyncMock())
    monkeypatch.setattr(task_executor, "build_task_prompt", AsyncMock(return_value="PROMPT"))
    monkeypatch.setattr(task_executor, "sel", lambda: MagicMock())
    monkeypatch.setattr(task_executor, "fire_tool_hooks", AsyncMock())
    monkeypatch.setattr(task_executor, "get_global_hook_store", MagicMock())
    fake_config = MagicMock()
    fake_config.load.return_value = MagicMock()
    monkeypatch.setattr(task_executor, "JunctionConfig", fake_config)


async def _execute(run: Project, task: Task, sessions: MagicMock) -> bool:
    return await task_executor.execute_task(
        run,
        task,
        sessions,
        None,
        "",
        None,
        False,
        None,
        "",
        AsyncMock(),
        f"{SESSION_PREFIX}:{run.task_id}:task{task.index}",
    )


def _run(task: Task, *, route_steps: bool | None) -> Project:
    run = Project(spec_path="spec.md", spec_content="body")
    run.task_id = "routed"
    run.tasks = [task]
    run.route_steps = route_steps
    return run


@pytest.mark.asyncio
async def test_a_limited_step_moves_agents_without_spending_an_attempt(
    router: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _quiet_executor(monkeypatch)
    task = Task(index=1, title="build it", description="d", kind="implement")
    sessions = _sessions([_Client(RuntimeError(_USAGE_LIMIT)), _Client()])
    assert await _execute(_run(task, route_steps=True), task, sessions) is True
    assert [o["acp_backend_override"] for o in sessions.opened] == ["codex", "claude"]
    assert task.harness == "claude"
    assert task.attempts == 1
    usage = router.ledger.snapshot()
    assert usage["codex"].cooldown_reason == "usage_limit"
    assert usage["claude"].ok == 1


@pytest.mark.asyncio
async def test_a_limit_after_tool_use_moves_on_the_next_attempt(
    router: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _quiet_executor(monkeypatch)
    task = Task(index=1, title="build it", description="d", kind="implement")
    sessions = _sessions([_Client(RuntimeError(_USAGE_LIMIT), tool=True), _Client()])
    assert await _execute(_run(task, route_steps=True), task, sessions) is True
    assert [o["acp_backend_override"] for o in sessions.opened] == ["codex", "claude"]
    assert task.attempts == 2


@pytest.mark.asyncio
async def test_a_limit_notice_reply_is_a_lane_failure_not_a_result(
    router: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _quiet_executor(monkeypatch)
    task = Task(index=1, title="build it", description="d", kind="implement")
    sessions = _sessions([_Client(reply=_USAGE_LIMIT), _Client(reply="done")])
    assert await _execute(_run(task, route_steps=True), task, sessions) is True
    assert [o["acp_backend_override"] for o in sessions.opened] == ["codex", "claude"]
    assert task.attempts == 1
    assert task.result == "done"
    usage = router.ledger.snapshot()
    assert usage["codex"].cooldown_reason == "usage_limit"
    assert usage["codex"].ok == 0


@pytest.mark.asyncio
async def test_exhausting_all_lanes_cannot_pass_a_limit_notice(
    router: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _quiet_executor(monkeypatch)
    task = Task(index=1, title="build it", description="d", kind="implement")
    sessions = _sessions([_Client(reply=_USAGE_LIMIT) for _ in range(8)])
    assert await _execute(_run(task, route_steps=True), task, sessions) is False
    assert [o["acp_backend_override"] for o in sessions.opened] == ["codex", "claude"]
    assert task.result != _USAGE_LIMIT
    assert task.attempts == 0  # Both pre-tool lane failures were free moves.
    assert all(usage.ok == 0 for usage in router.ledger.snapshot().values())


@pytest.mark.asyncio
async def test_a_notice_after_tool_use_is_the_steps_result(
    router: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The notice check applies only to a turn that did no work.
    _quiet_executor(monkeypatch)
    task = Task(index=1, title="build it", description="d", kind="implement")
    sessions = _sessions([_Client(tool=True, reply=_USAGE_LIMIT)])
    assert await _execute(_run(task, route_steps=True), task, sessions) is True
    assert [o["acp_backend_override"] for o in sessions.opened] == ["codex"]
    assert router.ledger.snapshot()["codex"].ok == 1


@pytest.mark.asyncio
async def test_unrouted_runs_pass_no_override(router: Any, monkeypatch) -> None:
    _quiet_executor(monkeypatch)
    monkeypatch.setattr(
        "junction.model_router.routing.apply_role_model", AsyncMock(return_value="auto")
    )
    for route_steps in (False, None):
        task = Task(index=1, title="build it", description="d", kind="implement")
        sessions = _sessions([_Client()])
        assert await _execute(_run(task, route_steps=route_steps), task, sessions) is True
        assert sessions.opened == [{"agent": None, "cwd": None}]
        assert task.harness == ""
    assert router.ledger.snapshot() == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback", [False, True])
async def test_failed_self_review_keeps_the_execution_lane_and_accounting(
    router: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fallback: bool
) -> None:
    _quiet_executor(monkeypatch)
    task = Task(index=1, title="build it", description="d", kind="implement")
    run = _run(task, route_steps=True)
    run.branch_name = ""
    if fallback:
        for lane in ("codex", "claude"):
            router.record_failure(lane, exc=RuntimeError(_USAGE_LIMIT))
    # SessionManager reuses the existing execution provider for the retry.
    client = _Client()
    sessions = _sessions([client, client])

    async def reject_review(*args):
        # Another turn can change lane headroom during the review. A new route
        # would now pick Claude, while this step's live provider remains Codex.
        if fallback:
            router.ledger.clear_cooldown()
        else:
            router.record_failure("codex", exc=RuntimeError(_USAGE_LIMIT))
        return False

    monkeypatch.setattr(task_executor, "self_review", reject_review)
    assert (
        await task_executor.execute_single_task(
            run,
            task,
            "history",
            sessions,
            None,
            "",
            AsyncMock(),
            None,
            None,
            False,
            None,
            tmp_path,
            MagicMock(),
            AsyncMock(),
        )
        is True
    )
    expected = None if fallback else "codex"
    assert [opened.get("acp_backend_override") for opened in sessions.opened] == [
        expected,
        expected,
    ]
    assert task.harness == ("" if fallback else "codex")
    usage = router.ledger.snapshot()
    assert usage["codex"].ok == (0 if fallback else 2)
    if fallback:
        assert usage["claude"].ok == 0
    else:
        assert "claude" not in usage


def _review_sessions() -> tuple[MagicMock, list[tuple[str, dict[str, Any]]]]:
    opened: list[tuple[str, dict[str, Any]]] = []

    async def _open(_parent: str, key: str, **kwargs: Any):
        opened.append((key, kwargs))
        return MagicMock(), True, False

    sessions = MagicMock()
    sessions.open_task_session = _open
    sessions.release = MagicMock()
    sessions.reset = AsyncMock()
    return sessions, opened


def _review_run(task: Task) -> Project:
    run = _run(task, route_steps=True)
    run.branch_name = ""
    return run


@pytest.mark.asyncio
async def test_a_routed_review_uses_its_own_lane_and_session(
    router: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(task_executor, "stream_and_collect", AsyncMock(return_value='{"ok": true}'))
    task = Task(index=3, title="build it", description="d", harness="claude")
    sessions, opened = _review_sessions()
    assert await task_executor.self_review(_review_run(task), task, sessions, "") is True
    key, kwargs = opened[0]
    assert key == f"{SESSION_PREFIX}:routed:review3"
    # Claude did the work, so the review goes to the other agent.
    assert kwargs["acp_backend_override"] == "codex"
    sessions.reset.assert_awaited_with(key)


@pytest.mark.asyncio
async def test_a_routed_review_moves_lanes_after_a_lane_failure(
    router: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies = AsyncMock(side_effect=[RuntimeError(_USAGE_LIMIT), '{"ok": false, "issue": "typo"}'])
    monkeypatch.setattr(task_executor, "stream_and_collect", replies)
    task = Task(index=2, title="build it", description="d", harness="claude")
    sessions, opened = _review_sessions()
    # The second agent's verdict counts: the review is not waved through.
    assert await task_executor.self_review(_review_run(task), task, sessions, "") is False
    assert [kw["acp_backend_override"] for _key, kw in opened] == ["codex", "claude"]
    assert task.error == "Self-review: typo"
    usage = router.ledger.snapshot()
    assert usage["codex"].cooldown_reason == "usage_limit"
    assert usage["claude"].ok == 1
    # Every session the review opened is released.
    assert sessions.release.call_count == len(opened)


@pytest.mark.asyncio
async def test_a_routed_review_treats_a_notice_reply_as_a_lane_failure(
    router: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies = AsyncMock(side_effect=[_USAGE_LIMIT, '{"ok": true}'])
    monkeypatch.setattr(task_executor, "stream_and_collect", replies)
    task = Task(index=2, title="build it", description="d", harness="claude")
    sessions, opened = _review_sessions()
    assert await task_executor.self_review(_review_run(task), task, sessions, "") is True
    assert [kw["acp_backend_override"] for _key, kw in opened] == ["codex", "claude"]
    assert router.ledger.snapshot()["codex"].ok == 0


@pytest.mark.asyncio
async def test_an_ordinary_review_failure_stays_non_blocking(
    router: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies = AsyncMock(side_effect=ValueError("bad json"))
    monkeypatch.setattr(task_executor, "stream_and_collect", replies)
    task = Task(index=2, title="build it", description="d", harness="claude")
    sessions, opened = _review_sessions()
    assert await task_executor.self_review(_review_run(task), task, sessions, "") is True
    assert len(opened) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool, max_failover, message, expected_attempts, expected_harness",
    [
        (False, 2, "failed to spawn", 1, "claude"),
        (True, 2, "failed to spawn", 2, "claude"),
        (False, 0, "failed to spawn", 2, "claude"),
        (False, 2, "worker exited unexpectedly", 1, "codex"),
    ],
)
async def test_process_recovery_respects_lane_retry_cost(
    router: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tool: bool,
    max_failover: int,
    message: str,
    expected_attempts: int,
    expected_harness: str,
) -> None:
    _quiet_executor(monkeypatch)
    p = tmp_path / "routing.json"
    document = json.loads(p.read_text())
    document["max_failover"] = max_failover
    p.write_text(json.dumps(document))
    task = Task(index=1, title="build it", description="d", kind="implement")
    sessions = _sessions([_Client(AcpProcessDied(message), tool=tool), _Client()])
    assert await _execute(_run(task, route_steps=True), task, sessions) is True
    assert [o["acp_backend_override"] for o in sessions.opened] == ["codex", expected_harness]
    assert task.attempts == expected_attempts
    assert router.ledger.snapshot()[expected_harness].ok == 1


@pytest.mark.asyncio
async def test_free_lane_moves_do_not_spend_the_process_recovery_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _quiet_executor(monkeypatch)
    monkeypatch.setitem(_BINS, "opencode", "/b/opencode")
    router = _router(tmp_path, harnesses=("codex", "claude", "grok", "opencode"))
    monkeypatch.setattr(service, "get_router", lambda: router)
    path = tmp_path / "routing.json"
    document = json.loads(path.read_text())
    document["max_failover"] = 3
    path.write_text(json.dumps(document))
    task = Task(index=1, title="build it", description="d", kind="implement")
    sessions = _sessions(
        [*[_Client(AcpProcessDied("failed to spawn")) for _ in range(3)], _Client()]
    )

    assert await _execute(_run(task, route_steps=True), task, sessions) is True
    assert len(sessions.opened) == 4
    assert len({opened["acp_backend_override"] for opened in sessions.opened}) == 4
    assert task.attempts == 1
    usage = router.ledger.snapshot()
    assert len(usage) == 4
    assert sum(lane.ok for lane in usage.values()) == 1


@pytest.mark.asyncio
async def test_daily_cap_refusal_is_terminal_and_records_no_dispatch_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _quiet_executor(monkeypatch)
    document = {
        "enabled": True,
        "route_tasks": True,
        "lanes": [{"id": "codex", "harness": "codex", "daily_limit": 1}],
    }
    (tmp_path / "routing.json").write_text(json.dumps(document), encoding="utf-8")
    router = HarnessRouter(home=tmp_path, which=_BINS.get, env={})
    monkeypatch.setattr(service, "get_router", lambda: router)
    failures = MagicMock(wraps=router.record_failure)
    monkeypatch.setattr(router, "record_failure", failures)
    task = Task(index=1, title="build it", description="d", kind="implement")
    sessions = _sessions([_Client(RuntimeError("tests failed"), tool=True), _Client()])

    assert await _execute(_run(task, route_steps=True), task, sessions) is False
    assert len(sessions.opened) == 1
    assert task.attempts == 1
    assert task.harness == "codex"
    assert "daily dispatch cap" in task.error
    assert router.ledger.snapshot()["codex"].count_since(0) == 1
    assert failures.call_count == 1
    assert sessions.record_failure.await_count == 1
    assert sessions.reset.await_count == 1


@pytest.mark.asyncio
async def test_review_retry_daily_cap_preserves_the_attempt_that_ran(
    router: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _quiet_executor(monkeypatch)
    path = tmp_path / "routing.json"
    document = json.loads(path.read_text())
    document["lanes"][0]["daily_limit"] = 1
    path.write_text(json.dumps(document))
    task = Task(index=1, title="build it", description="d", kind="implement")
    run = _run(task, route_steps=True)
    run.branch_name = ""
    sessions = _sessions([_Client()])
    monkeypatch.setattr(task_executor, "self_review", AsyncMock(return_value=False))

    assert (
        await task_executor.execute_single_task(
            run,
            task,
            "history",
            sessions,
            None,
            "",
            AsyncMock(),
            None,
            None,
            False,
            None,
            tmp_path,
            MagicMock(),
            AsyncMock(),
        )
        is False
    )
    assert len(sessions.opened) == 1
    assert task.attempts == 1
    assert task.harness == "codex"
    usage = router.ledger.snapshot()["codex"]
    assert usage.count_since(0) == 1
    assert usage.ok == 1
    assert usage.failed == 0
    sessions.record_failure.assert_not_awaited()
    sessions.reset.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", [False, True])
@pytest.mark.parametrize("failure", ["exception", "notice", "transient"])
async def test_review_does_not_replay_tools_after_a_lane_failure(
    router: Any, monkeypatch: pytest.MonkeyPatch, tool: bool, failure: str
) -> None:
    _quiet_executor(monkeypatch)
    task = Task(index=2, title="build it", description="d", harness="claude")
    failed = _Client(
        (
            None
            if failure == "notice"
            else (
                AcpError(_USAGE_LIMIT, transient=True)
                if failure == "transient"
                else RuntimeError(_USAGE_LIMIT)
            )
        ),
        tool=tool,
        reply=_USAGE_LIMIT if failure == "notice" else "",
    )
    sessions = _sessions([failed, _Client(reply='{"ok": false, "issue": "typo"}')])
    assert await task_executor.self_review(_review_run(task), task, sessions, "") is tool
    harnesses = [kw["acp_backend_override"] for kw in sessions.opened]
    assert harnesses == (["codex"] if tool else ["codex", "claude"])
    assert router.ledger.snapshot()["codex"].cooldown_reason == "usage_limit"


@pytest.mark.parametrize("cooling", [False, True])
@pytest.mark.asyncio
async def test_fresh_step_cannot_bypass_a_daily_cap(tmp_path: Path, cooling: bool) -> None:
    document = {"lanes": [{"id": "codex", "harness": "codex", "daily_limit": 1}]}
    (tmp_path / "routing.json").write_text(json.dumps(document), encoding="utf-8")
    router = HarnessRouter(home=tmp_path, which=_BINS.get, env={})
    await StepRoute("implement", router=router).pick()
    if cooling:
        router.record_failure("codex", exc=RuntimeError(_USAGE_LIMIT))
    with pytest.raises(service.RoutingError) as error:
        await StepRoute("implement", router=router).pick()
    assert error.value.code == "daily_cap"
    assert router.ledger.snapshot()["codex"].count_since(0) == 1


@pytest.mark.parametrize(
    "event_kind, activity, expected_attempts",
    [
        ("permission_request", True, 2),
        ("permission_request", False, 1),
        ("subagent_activity", True, 2),
        ("subagent_activity", False, 1),
    ],
)
@pytest.mark.asyncio
async def test_child_tool_activity_charges_the_lane_move(
    router: Any,
    monkeypatch: pytest.MonkeyPatch,
    event_kind: str,
    activity: bool,
    expected_attempts: int,
) -> None:
    _quiet_executor(monkeypatch)

    class ChildClient(_Client):
        approve_tool = AsyncMock()
        reject_tool = AsyncMock()

        def context_usage_pct(self):
            return 0

        async def stream(self, _prompt: str):
            yield LLMEvent(
                kind=event_kind,
                title="edit",
                request_id=7,
                sub_session_id="child",
                tool_call_id="child-edit" if activity else "",
            )
            raise RuntimeError(_USAGE_LIMIT)

    task = Task(index=1, title="Child work", description="Work")
    sessions = _sessions([ChildClient(), _Client()])
    run = _run(task, route_steps=True)
    assert await task_executor.execute_task(
        run,
        task,
        sessions,
        None,
        "",
        AsyncMock(return_value=activity),
        False,
        None,
        "",
        AsyncMock(),
    )
    assert task.attempts == expected_attempts
    assert [entry["acp_backend_override"] for entry in sessions.opened] == ["codex", "claude"]


@pytest.mark.parametrize("child_tool", [False, True])
@pytest.mark.parametrize("parent_refusal", [False, True])
@pytest.mark.asyncio
async def test_review_does_not_replay_native_child_tools(
    router: Any, monkeypatch: pytest.MonkeyPatch, child_tool: bool, parent_refusal: bool
) -> None:
    _quiet_executor(monkeypatch)

    class NativeChild(_Client):
        reject_tool = AsyncMock()

        async def stream(self, _prompt: str):
            if parent_refusal:
                yield LLMEvent(
                    kind="permission_request",
                    request_id="r1",
                    tool_call_id="child-edit",
                    title="rm -rf /",
                )
            yield LLMEvent(
                kind="subagent_activity",
                sub_session_id="child",
                tool_call_id="child-edit" if child_tool else "",
                title="edit",
            )
            raise RuntimeError(_USAGE_LIMIT)

    task = Task(index=2, title="build it", description="d", harness="claude")
    sessions = _sessions([NativeChild(), _Client(reply='{"ok": false, "issue": "typo"}')])
    assert await task_executor.self_review(_review_run(task), task, sessions, "") is child_tool
    assert [kw["acp_backend_override"] for kw in sessions.opened] == (
        ["codex"] if child_tool else ["codex", "claude"]
    )


@pytest.mark.parametrize("test_output", ["red", _USAGE_LIMIT])
@pytest.mark.asyncio
async def test_automatic_test_failure_records_a_failed_attempt_on_the_sticky_lane(
    router: Any, monkeypatch: pytest.MonkeyPatch, test_output: str
) -> None:
    _quiet_executor(monkeypatch)
    monkeypatch.setattr(
        task_executor, "run_tests", AsyncMock(side_effect=[(False, test_output), (True, "green")])
    )
    task = Task(index=1, title="build it", description="d")
    sessions = _sessions([_Client(), _Client()])
    assert await task_executor.execute_task(
        _run(task, route_steps=True),
        task,
        sessions,
        None,
        "",
        None,
        True,
        ["pytest"],
        "",
        AsyncMock(),
    )
    assert task.attempts == 2
    assert [kw["acp_backend_override"] for kw in sessions.opened] == ["codex", "codex"]
    usage = router.ledger.snapshot()["codex"]
    assert (usage.ok, usage.failed, usage.count_since(0)) == (1, 1, 2)
    assert not usage.cooling(time.time())


@pytest.mark.parametrize("review", [False, True])
@pytest.mark.asyncio
async def test_limit_notice_failure_redacts_credentials_before_logging(
    router: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    review: bool,
) -> None:
    _quiet_executor(monkeypatch)
    monkeypatch.setattr(task_executor, "MAX_RETRIES", 1)
    caplog.set_level("DEBUG", logger="junction.task_executor")
    document = json.loads((router.home / "routing.json").read_text())
    document["max_failover"] = 0
    (router.home / "routing.json").write_text(json.dumps(document))
    credential = "sk-proj-" + "a" * 45
    notice = _USAGE_LIMIT + " API key: " + credential
    task = Task(index=2, title="build it", description="d", harness="claude")
    sessions = _sessions([_Client(reply=notice)])
    if review:
        assert await task_executor.self_review(_review_run(task), task, sessions, "")
    else:
        assert not await _execute(_run(task, route_steps=True), task, sessions)
        assert "usage_limit" in task.error
    assert credential not in caplog.text
    assert credential not in task.error


# ── Resume: a step's lane outlives the process ──


def _crowd(router: Any, lane_id: str, dispatches: int = 30) -> None:
    """Use up *lane_id*'s headroom, as the step's own earlier dispatches do."""
    for _ in range(dispatches):
        router.record_dispatch(lane_id, "implement")


def _edit_routing(router: Any, edit: Any) -> None:
    path = router.home / "routing.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    edit(doc)
    path.write_text(json.dumps(doc), encoding="utf-8")


@pytest.mark.asyncio
async def test_a_restored_route_keeps_its_lane_when_headroom_would_move_it(router: Any) -> None:
    _crowd(router, "codex")
    # Premise: scored fresh, the step would now cross to the other harness.
    assert (await StepRoute("implement", router=router).pick()).harness == "claude"
    route = StepRoute("implement", router=router, restore=LaneBinding("codex", "", "codex"))
    lane = await route.pick()
    assert lane.id == "codex"
    assert route.binding == ("codex", "")
    assert (await route.pick()).id == "codex"  # sticky from then on
    # Each resumed attempt is a real dispatch and is accounted to its lane.
    assert router.ledger.snapshot()["codex"].count_since(0) == 32


@pytest.mark.asyncio
async def test_a_restored_route_keeps_the_model_the_step_started_on(router: Any) -> None:
    _edit_routing(router, lambda doc: doc["lanes"][0].update(model="gpt-new"))
    route = StepRoute("implement", router=router, restore=LaneBinding("codex", "gpt-old", "codex"))
    lane = await route.pick()
    assert (lane.id, lane.model) == ("codex", "gpt-old")
    assert route.binding == ("codex", "gpt-old")
    # A step first dispatched on the harness default keeps it too.
    default = StepRoute("implement", router=router, restore=LaneBinding("codex", "", "codex"))
    assert (await default.pick()).model == ""


def _remove_codex(router: Any) -> None:
    _edit_routing(
        router, lambda doc: doc.update(lanes=[ln for ln in doc["lanes"] if ln["id"] != "codex"])
    )


def _repoint_codex(router: Any) -> None:
    _edit_routing(router, lambda doc: doc["lanes"][0].update(harness="claude"))


def _disable_codex(router: Any) -> None:
    _edit_routing(router, lambda doc: doc["lanes"][0].update(enabled=False))


def _rest_codex(router: Any) -> None:
    router.record_failure("codex", exc=RuntimeError(_USAGE_LIMIT))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("damage", "reason"),
    [
        (_remove_codex, "no longer configured"),
        (_repoint_codex, "now runs claude, not codex"),
        (_disable_codex, "disabled"),
        (_rest_codex, "resting after usage_limit"),
    ],
)
async def test_a_restored_route_refuses_a_lane_that_cannot_take_its_step_back(
    router: Any, damage: Any, reason: str
) -> None:
    damage(router)
    route = StepRoute("implement", router=router, restore=LaneBinding("codex", "", "codex"))
    with pytest.raises(service.RoutingError, match=reason) as error:
        await route.pick()
    assert error.value.code == LANE_UNAVAILABLE
    # Fail closed: nothing was dispatched, least of all to the other harness.
    assert route.lane is None
    assert "claude" not in router.ledger.snapshot()
    assert router.ledger.snapshot().get("codex") is None or all(
        usage.count_since(0) == 0 for usage in router.ledger.snapshot().values()
    )


@pytest.mark.asyncio
async def test_a_restored_route_refuses_an_uninstalled_harness(tmp_path: Path) -> None:
    lanes = [{"id": h, "harness": h} for h in ("codex", "claude")]
    (tmp_path / "routing.json").write_text(json.dumps({"lanes": lanes}), encoding="utf-8")
    router = HarnessRouter(home=tmp_path, which={"claude": "/b/claude"}.get, env={})
    route = StepRoute("implement", router=router, restore=LaneBinding("codex", "", "codex"))
    with pytest.raises(service.RoutingError, match="no codex harness installed"):
        await route.pick()
    assert router.ledger.snapshot() == {}


@pytest.mark.asyncio
async def test_a_restored_route_still_obeys_the_daily_cap(tmp_path: Path) -> None:
    lanes = [
        {"id": "codex", "harness": "codex", "daily_limit": 1},
        {"id": "claude", "harness": "claude"},
    ]
    (tmp_path / "routing.json").write_text(json.dumps({"lanes": lanes}), encoding="utf-8")
    router = HarnessRouter(home=tmp_path, which=_BINS.get, env={})
    router.record_dispatch("codex", "implement")
    route = StepRoute("implement", router=router, restore=LaneBinding("codex", "", "codex"))
    with pytest.raises(service.RoutingError) as error:
        await route.pick()
    assert error.value.code == "daily_cap"
    assert router.ledger.snapshot()["codex"].count_since(0) == 1
    assert "claude" not in router.ledger.snapshot()


@pytest.mark.asyncio
async def test_a_restored_configured_agent_fallback_does_not_cross_to_a_recovered_lane(
    router: Any,
) -> None:
    route = StepRoute(
        "implement", router=router, restore=LaneBinding(CONFIGURED_AGENT_LANE, "", "")
    )
    assert await route.pick() is None
    assert route.binding == (CONFIGURED_AGENT_LANE, "")
    assert router.ledger.snapshot() == {}  # Both lanes were free to take it.
    assert await route.failed(RuntimeError(_USAGE_LIMIT), tool_ran=False) is False


@pytest.mark.asyncio
async def test_a_fallback_is_saved_as_the_configured_agent(tmp_path: Path) -> None:
    router = _router(tmp_path, harnesses=("codex",))
    router.record_failure("codex", exc=RuntimeError(_USAGE_LIMIT))
    route = StepRoute("implement", router=router)
    assert route.binding == ("", "")  # Not yet chosen.
    assert await route.pick() is None
    assert route.binding == (CONFIGURED_AGENT_LANE, "")


@pytest.mark.asyncio
async def test_the_first_limit_on_a_restored_lane_is_never_a_free_move(router: Any) -> None:
    route = StepRoute("implement", router=router, restore=LaneBinding("codex", "", "codex"))
    await route.pick()
    # The earlier process may have changed the workspace already.
    assert await route.failed(RuntimeError(_USAGE_LIMIT), tool_ran=False) is False
    assert route.binding == ("", "")  # Released: the next pick resolves, not restores.
    moved = await route.pick()
    assert moved.harness == "claude"
    assert route.binding == ("claude", "")
    # The restore is spent: an ordinary failure budget applies from here.
    assert await route.failed(RuntimeError(_USAGE_LIMIT), tool_ran=False) is True


def test_a_route_for_a_task_restores_only_a_bound_task() -> None:
    bound = Task(index=1, title="t", description="d", harness="codex", lane_id="codex")
    assert StepRoute.for_task(bound)._restore == LaneBinding("codex", "", "codex")
    assert StepRoute.for_task(Task(index=2, title="t", description="d"))._restore is None


def _task_persist(task: Task, log: list[tuple[str, str, int]], sessions: MagicMock) -> Any:
    async def persist() -> None:
        log.append((task.lane_id, task.lane_model, len(sessions.opened)))

    return persist


async def _execute_with(run: Project, task: Task, sessions: MagicMock, persist: Any = None) -> bool:
    return await task_executor.execute_task(
        run,
        task,
        sessions,
        None,
        "",
        None,
        False,
        None,
        "",
        AsyncMock(),
        f"{SESSION_PREFIX}:{run.task_id}:task{task.index}",
        persist=persist,
    )


@pytest.mark.asyncio
async def test_a_paused_step_resumes_on_the_lane_and_model_it_was_dispatched_on(
    router: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from junction.taskrunner import TaskRunner

    _quiet_executor(monkeypatch)
    _edit_routing(router, lambda doc: doc["lanes"][0].update(model="gpt-x"))
    task = Task(index=1, title="build it", description="d", kind="implement")
    run = _run(task, route_steps=True)
    run.status = "running"
    sessions = _sessions([_Client(asyncio.CancelledError(), tool=True)])
    saved: list[tuple[str, str, int]] = []

    # The step does work, then the run is paused (its asyncio task cancelled).
    with pytest.raises(asyncio.CancelledError):
        await _execute_with(run, task, sessions, _task_persist(task, saved, sessions))
    # The lane was durable before the provider opened, not only afterwards.
    assert saved == [("codex", "gpt-x", 0)]

    # Gateway restart: the registry comes back from disk.
    runner = TaskRunner(sessions=MagicMock(), auto_test=False, work_dir=tmp_path)
    runner._runs[run.task_id] = run
    runner._persist_runs()
    reloaded = TaskRunner(sessions=MagicMock(), auto_test=False, work_dir=tmp_path)
    reloaded._load_runs()
    resumed_run = reloaded._runs[run.task_id]
    resumed = resumed_run.tasks[0]
    assert (resumed_run.status, resumed.status.value) == ("paused", "pending")

    # The step's own dispatch used up codex's headroom; scored fresh it moves.
    _crowd(router, "codex")
    assert (await StepRoute("implement", router=router).pick()).harness == "claude"

    sessions2 = _sessions([_Client(reply="finished")])
    assert await _execute_with(resumed_run, resumed, sessions2) is True
    assert [(o["acp_backend_override"], o["model"]) for o in sessions2.opened] == [
        ("codex", "gpt-x")
    ]
    assert resumed.harness == "codex"
    assert router.ledger.snapshot()["claude"].count_since(0) == 1  # only the premise check


@pytest.mark.asyncio
async def test_a_resumed_lane_limit_costs_an_attempt_even_before_any_tool(
    router: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _quiet_executor(monkeypatch)
    task = Task(index=1, title="build it", description="d", kind="implement")
    task.harness, task.lane_id = "codex", "codex"
    run = _run(task, route_steps=True)
    sessions = _sessions([_Client(RuntimeError(_USAGE_LIMIT)), _Client()])
    saved: list[tuple[str, str, int]] = []
    assert await _execute_with(run, task, sessions, _task_persist(task, saved, sessions)) is True
    assert [o["acp_backend_override"] for o in sessions.opened] == ["codex", "claude"]
    assert task.attempts == 2  # Not a free hop: the step may have run before the pause.
    # Released when the limit hit, rebound once the next lane was chosen.
    assert saved == [("", "", 1), ("claude", "", 1)]
    assert (task.lane_id, task.harness) == ("claude", "claude")


@pytest.mark.asyncio
async def test_a_resume_that_cannot_return_to_its_lane_waits_instead_of_crossing(
    router: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _quiet_executor(monkeypatch)
    task = Task(index=1, title="build it", description="d", kind="implement")
    task.harness, task.lane_id = "codex", "codex"
    run = _run(task, route_steps=True)
    _rest_codex(router)
    sessions = _sessions([_Client()])
    assert await _execute_with(run, task, sessions) is False
    assert "codex" in task.error and "resting" in task.error
    assert sessions.opened == []
    assert task.lane_id == "codex"  # Still bound: the lane is expected back.
    assert "claude" not in router.ledger.snapshot()
    sessions.reset.assert_not_awaited()  # Refusal is not a provider failure.

    # Once the lane recovers the same step goes back to it.
    router.ledger.clear_cooldown()
    assert await _execute_with(run, task, sessions) is True
    assert [o["acp_backend_override"] for o in sessions.opened] == ["codex"]


@pytest.mark.asyncio
async def test_a_configured_agent_fallback_stays_on_the_configured_agent_when_resumed(
    router: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _quiet_executor(monkeypatch)
    monkeypatch.setattr(
        "junction.model_router.routing.apply_role_model", AsyncMock(return_value="auto")
    )
    for lane in ("codex", "claude"):
        router.record_failure(lane, exc=RuntimeError(_USAGE_LIMIT))
    task = Task(index=1, title="build it", description="d", kind="implement")
    run = _run(task, route_steps=True)
    sessions = _sessions([_Client(asyncio.CancelledError(), tool=True)])
    saved: list[tuple[str, str, int]] = []
    with pytest.raises(asyncio.CancelledError):
        await _execute_with(run, task, sessions, _task_persist(task, saved, sessions))
    assert saved == [(CONFIGURED_AGENT_LANE, "", 0)]

    router.ledger.clear_cooldown()  # Both lanes are back, but the step is in flight.
    resumed = _sessions([_Client()])
    assert await _execute_with(run, task, resumed) is True
    assert resumed.opened == [{"agent": None, "cwd": None}]
    assert task.harness == ""
    assert router.ledger.snapshot().get("claude") is None or not any(
        u.count_since(0) for u in router.ledger.snapshot().values()
    )


async def _single(
    run: Project, task: Task, sessions: MagicMock, tmp_path: Path, persist: Any = None
) -> bool:
    return await task_executor.execute_single_task(
        run,
        task,
        "history",
        sessions,
        None,
        "",
        AsyncMock(),
        None,
        None,
        False,
        None,
        tmp_path,
        MagicMock(),
        AsyncMock(),
        persist=persist,
    )


@pytest.mark.asyncio
async def test_a_passed_step_lets_go_of_its_lane_and_a_failed_one_keeps_it(
    router: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _quiet_executor(monkeypatch)
    monkeypatch.setattr(task_executor, "self_review", AsyncMock(return_value=True))
    passing = Task(index=1, title="build it", description="d", kind="implement")
    run = _run(passing, route_steps=True)
    assert await _single(run, passing, _sessions([_Client()]), tmp_path) is True
    assert (passing.lane_id, passing.lane_model) == ("", "")
    assert passing.harness == "codex"  # What ran it is still shown.

    failing = Task(index=2, title="build more", description="d", kind="implement")
    run.tasks.append(failing)
    broken = _sessions([_Client(ValueError(f"boom {n}")) for n in range(3)])
    assert await _single(run, failing, broken, tmp_path) is False
    # A later resume of the unfinished step still goes back to its lane.
    assert failing.lane_id == "codex"
