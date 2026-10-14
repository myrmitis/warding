"""``warding route run`` moves a turn to another lane only before it did work.

Harness-router invariant 4: only lane failures move work, and only before
activity. A turn that streamed text or answered a permission request (so a tool
may have run) and then hits a lane-level error mid-stream stays on its lane;
re-running the prompt elsewhere would repeat that work. A reply that is nothing
but a usage-limit notice still moves.

Providers are fakes on the per-test data home with a stubbed ``which``: nothing
starts a harness process or touches the network.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from warding.config.paths import data_home
from warding.harness_router import cli
from warding.harness_router.limits import FAILURE_RATE_LIMIT, FAILURE_USAGE_LIMIT
from warding.harness_router.service import HarnessRouter
from warding.providers.base import EVENT_COMPLETE, EVENT_PERMISSION_REQUEST, EVENT_TEXT_CHUNK

_CODEX_429 = "exceeded retry limit, last status: 429 Too Many Requests"
_CODEX_400 = (
    '{"type":"error","status":400,"error":{"type":"invalid_request_error",'
    '"message":"The \'gpt-6.1-sol\' model is not supported when using Codex with a ChatGPT account."}}'
)

_BINS = {"codex": "/b/codex", "claude": "/b/claude", "npx": "/b/npx", "grok": "/b/grok"}

_THREE_LANES = {
    "lanes": [
        {"id": "pro", "harness": "codex"},
        {"id": "max", "harness": "claude"},
        {"id": "sg", "harness": "grok"},
    ]
}


@pytest.fixture(autouse=True)
def _pin_os_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Detect harnesses against a pinned OS home, never the developer's (see
    ``test_harness_router._pin_os_home``: DSH detection reads ``Path.home()``)."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))


@pytest.fixture(autouse=True)
def warm_calls(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """Stub the blocking sandbox probe ``route run`` / ``route check`` warm up."""
    import warding.sandbox as sandbox

    calls: list[bool] = []
    monkeypatch.setattr(sandbox, "warm_backend", lambda: calls.append(True))
    return calls


def _router(
    monkeypatch: pytest.MonkeyPatch,
    bins: dict[str, str] | None = None,
    doc: dict[str, Any] | None = None,
) -> HarnessRouter:
    """A router on the per-test data home, installed as the one the CLI builds."""
    home = data_home()
    if doc is not None:
        (home / "routing.json").write_text(json.dumps(doc), encoding="utf-8")
    router = HarnessRouter(home=home, which=(_BINS if bins is None else bins).get, env={})
    monkeypatch.setattr(cli, "HarnessRouter", lambda: router)
    return router


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="warding route")
    cli.add_arguments(parser)
    return parser.parse_args(list(argv))


def _event(kind: str, text: str = "") -> SimpleNamespace:
    return SimpleNamespace(kind=kind, text=text)


def _reply(*chunks: str) -> list[SimpleNamespace]:
    return [_event(EVENT_TEXT_CHUNK, c) for c in chunks] + [_event(EVENT_COMPLETE)]


class _FakeProvider:
    """Streams a scripted turn; can fail at start, mid-stream, or at shutdown."""

    def __init__(
        self,
        events: list[SimpleNamespace] | None = None,
        *,
        start_error: BaseException | None = None,
        stream_error: BaseException | None = None,
        shutdown_error: BaseException | None = None,
    ) -> None:
        self._events = events or []
        self._start_error = start_error
        self._stream_error = stream_error
        self._shutdown_error = shutdown_error
        self.prompts: list[str] = []
        self.shut = False

    async def start(self) -> None:
        if self._start_error is not None:
            raise self._start_error

    async def stream(self, prompt: str) -> AsyncIterator[SimpleNamespace]:
        self.prompts.append(prompt)
        for event in self._events:
            yield event
        if self._stream_error is not None:
            raise self._stream_error

    async def shutdown(self) -> None:
        self.shut = True
        if self._shutdown_error is not None:
            raise self._shutdown_error


def _providers(monkeypatch: pytest.MonkeyPatch, *providers: _FakeProvider) -> list[tuple[str, str]]:
    """Hand out *providers* in order; returns the (lane id, cwd) of each one made."""
    queue = list(providers)
    made: list[tuple[str, str]] = []

    def make(lane: Any, cwd: str) -> _FakeProvider:
        made.append((lane.id, cwd))
        return queue.pop(0)

    monkeypatch.setattr(cli, "_make_provider", make)
    return made


def _run_exit_code(args: argparse.Namespace) -> int:
    try:
        cli.run_route_command(args)
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def test_route_run_fails_over_when_the_reply_is_a_usage_limit_notice(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    router = _router(monkeypatch, doc=_THREE_LANES)
    limited = _FakeProvider(_reply("You've hit your usage limit."))
    rescuer = _FakeProvider(_reply("done"))
    made = _providers(monkeypatch, limited, rescuer)

    assert _run_exit_code(_parse("run", "build it", "--no-prompt")) == 0

    err = capsys.readouterr().err
    assert [lane for lane, _ in made] == ["pro", "max"]
    assert "[route] pro unavailable (usage_limit); moving to max" in err
    # Only the first hop carries the routing reason.
    assert "[route] max (Claude Code) · implement\n" in err
    assert limited.shut and rescuer.shut
    usage = router.ledger.snapshot()
    assert usage["pro"].cooldown_reason == FAILURE_USAGE_LIMIT
    assert usage["max"].ok == 1


def test_route_run_success_keeps_a_limit_recorded_while_its_harness_shut_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``route run`` records its success after the harness exits, which can take
    seconds; a limit a gateway run hits on the same lane meanwhile must stay."""
    router = _router(monkeypatch, doc=_THREE_LANES)
    gateway = HarnessRouter(home=router.home, which=_BINS.get, env={})

    class _SlowExit(_FakeProvider):
        async def shutdown(self) -> None:
            await super().shutdown()
            gateway.record_dispatch("pro", "implement")
            gateway.record_failure(
                "pro", text="You've hit your usage limit. Try again in 3 hours.", harness="codex"
            )

    made = _providers(monkeypatch, _SlowExit(_reply("done")))
    assert _run_exit_code(_parse("run", "build it", "--no-prompt", "--harness", "pro")) == 0
    assert [lane for lane, _ in made] == ["pro"]
    usage = router.ledger.snapshot()["pro"]
    assert usage.cooldown_reason == FAILURE_USAGE_LIMIT
    assert (usage.ok, usage.failed, usage.harness) == (1, 1, "codex")


def test_route_run_does_not_move_once_the_turn_produced_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A lane that fails MID-stream has already done work; re-running the prompt
    on another lane would repeat it, tool calls included."""
    router = _router(monkeypatch, doc=_THREE_LANES)
    partial = _FakeProvider(
        [_event(EVENT_TEXT_CHUNK, "half done")], stream_error=RuntimeError("429 rate limit")
    )
    made = _providers(monkeypatch, partial, _FakeProvider(_reply("redone")))

    code = _run_exit_code(_parse("run", "x", "--no-prompt"))

    captured = capsys.readouterr()
    assert captured.out.startswith("half done")
    assert router.ledger.snapshot()["pro"].cooldown_reason == FAILURE_RATE_LIMIT
    # The work already ran on pro: moving would run the prompt a second time.
    assert [lane for lane, _ in made] == ["pro"]
    assert code == 1 and "[route] pro failed (rate_limit)" in captured.err


def _answer_with(monkeypatch: pytest.MonkeyPatch, approved: bool) -> None:
    """Answer every permission request with *approved*, without the real gate."""
    import warding.cli_chat as cli_chat

    async def answer(prov: Any, event: Any, *, interactive: bool, gate: Any = None) -> bool:
        return approved

    monkeypatch.setattr(cli_chat, "_build_tool_gate", lambda agent="": object())
    monkeypatch.setattr(cli_chat, "_answer_permission", answer)


def test_route_run_does_not_move_once_a_tool_was_approved(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An approved permission request means the tool may already have run, even
    with no text streamed, so a mid-stream failure stays on the lane."""
    _router(monkeypatch, doc=_THREE_LANES)
    asked = _FakeProvider(
        [_event(EVENT_PERMISSION_REQUEST)], stream_error=RuntimeError("429 rate limit")
    )
    made = _providers(monkeypatch, asked, _FakeProvider(_reply("redone")))
    _answer_with(monkeypatch, approved=True)

    assert _run_exit_code(_parse("run", "x")) == 1
    assert [lane for lane, _ in made] == ["pro"]
    assert "[route] pro failed (rate_limit)" in capsys.readouterr().err


def test_route_run_still_moves_when_the_only_tool_call_was_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A refused call (``--no-prompt``, the gate, or the user) never ran, so a
    lane failure after it is as safe to move as one before any activity."""
    _router(monkeypatch, doc=_THREE_LANES)
    asked = _FakeProvider(
        [_event(EVENT_PERMISSION_REQUEST)], stream_error=RuntimeError("429 rate limit")
    )
    made = _providers(monkeypatch, asked, _FakeProvider(_reply("done")))
    _answer_with(monkeypatch, approved=False)

    assert _run_exit_code(_parse("run", "x", "--no-prompt")) == 0
    assert [lane for lane, _ in made] == ["pro", "max"]
    assert "[route] pro unavailable (rate_limit); moving to max" in capsys.readouterr().err


@pytest.mark.parametrize(
    "reply",
    [
        _CODEX_429,
        '{"type":"error","status":429,"error":{"type":"rate_limit_error",'
        '"message":"Too many requests"}}',
    ],
)
def test_route_run_backs_off_codex_provider_429_and_routes_to_next_lane(
    monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    router = _router(monkeypatch, doc=_THREE_LANES)
    made = _providers(monkeypatch, _FakeProvider(_reply(reply)), _FakeProvider(_reply("pong")))
    assert _run_exit_code(_parse("run", "Reply pong", "--no-prompt")) == 0
    assert [lane for lane, _ in made] == ["pro", "max"]
    usage = router.ledger.snapshot()
    assert (usage["pro"].ok, usage["pro"].failed, usage["pro"].limited) == (0, 1, 1)
    assert usage["pro"].cooldown_reason == FAILURE_RATE_LIMIT
    assert usage["max"].ok == 1
    assert router.resolve("route", kind="implement").lane.id == "max"


@pytest.mark.parametrize("reply", [_CODEX_400, _CODEX_429])
def test_pinned_codex_provider_errors_exit_nonzero_and_are_not_successes(
    monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    router = _router(monkeypatch, doc=_THREE_LANES)
    made = _providers(monkeypatch, _FakeProvider(_reply(reply)))
    assert _run_exit_code(_parse("run", "x", "--harness", "pro", "--no-prompt")) == 1
    assert [lane for lane, _ in made] == ["pro"]
    usage = router.ledger.snapshot()["pro"]
    assert (usage.ok, usage.failed) == (0, 1)
    assert usage.cooldown_reason == (FAILURE_RATE_LIMIT if reply == _CODEX_429 else "")
    assert usage.limited == (1 if reply == _CODEX_429 else 0)


def test_unsupported_inherited_codex_model_error_is_not_a_transient_lane_failure(
    monkeypatch,
) -> None:
    router = _router(monkeypatch, doc=_THREE_LANES)
    assert router.settings().lanes_for_harness("codex")[0].model == ""
    made = _providers(monkeypatch, _FakeProvider(_reply(_CODEX_400)))
    assert _run_exit_code(_parse("run", "x", "--no-prompt")) == 1
    assert [lane for lane, _ in made] == ["pro"]
    assert router.ledger.snapshot()["pro"].cooldown_until == 0


@pytest.mark.parametrize("approved", [False, True])
def test_codex_notice_after_permission_never_replays_approved_tools(
    monkeypatch: pytest.MonkeyPatch, approved: bool
) -> None:
    _router(monkeypatch, doc=_THREE_LANES)
    _answer_with(monkeypatch, approved=approved)
    events = [_event(EVENT_PERMISSION_REQUEST), *_reply(_CODEX_429)]
    made = _providers(monkeypatch, _FakeProvider(events), _FakeProvider(_reply("pong")))
    assert _run_exit_code(_parse("run", "x", "--no-prompt")) == 0
    assert [lane for lane, _ in made] == (["pro"] if approved else ["pro", "max"])


@pytest.mark.parametrize("event_kind", ["tool_call", "subagent_activity"])
def test_codex_notice_after_native_tool_activity_is_not_replayed(monkeypatch, event_kind) -> None:
    _router(monkeypatch, doc=_THREE_LANES)
    tool_event = SimpleNamespace(kind=event_kind, tool_call_id="child-edit", text="")
    made = _providers(
        monkeypatch, _FakeProvider([tool_event, *_reply(_CODEX_429)]), _FakeProvider(_reply("pong"))
    )
    assert _run_exit_code(_parse("run", "x", "--no-prompt")) == 0
    assert [lane for lane, _ in made] == ["pro"]


@pytest.mark.parametrize("reply", ["HTTP 429 Too Many Requests", "Fixed HTTP 400 model errors"])
def test_route_run_error_discussion_remains_a_success(monkeypatch, reply) -> None:
    router = _router(monkeypatch, doc=_THREE_LANES)
    made = _providers(monkeypatch, _FakeProvider(_reply(reply)))
    assert _run_exit_code(_parse("run", "x", "--no-prompt")) == 0
    assert [lane for lane, _ in made] == ["pro"]
    assert router.ledger.snapshot()["pro"].ok == 1


@pytest.mark.parametrize("permission_first", [False, True])
@pytest.mark.parametrize("raises", [False, True])
def test_denied_pending_tool_does_not_hide_a_codex_provider_failure(
    monkeypatch, permission_first: bool, raises: bool
) -> None:
    router = _router(monkeypatch, doc=_THREE_LANES)
    _answer_with(monkeypatch, approved=False)
    pending = SimpleNamespace(kind="tool_call", tool_call_id="pending", sub_session_id="")
    permission = SimpleNamespace(
        kind=EVENT_PERMISSION_REQUEST, tool_call_id="pending", sub_session_id=""
    )
    events = [permission, pending] if permission_first else [pending, permission]
    failed = _FakeProvider(
        events if raises else [*events, *_reply(_CODEX_429)],
        stream_error=RuntimeError("HTTP 429 Too Many Requests") if raises else None,
    )
    made = _providers(monkeypatch, failed, _FakeProvider(_reply("pong")))
    assert _run_exit_code(_parse("run", "x", "--no-prompt")) == 0
    assert [lane for lane, _ in made] == ["pro", "max"]
    assert router.ledger.snapshot()["pro"].cooldown_reason == FAILURE_RATE_LIMIT
    assert router.ledger.snapshot()["pro"].ok == 0


@pytest.mark.parametrize("activity", ["text", "approved", "child", "idless"])
def test_denial_cannot_erase_independent_turn_activity(monkeypatch, activity: str) -> None:
    _router(monkeypatch, doc=_THREE_LANES)
    import warding.cli_chat as cli_chat

    monkeypatch.setattr(cli_chat, "_build_tool_gate", lambda agent="": object())

    async def answer(_provider, event, **kwargs):
        return event.tool_call_id == "approved"

    monkeypatch.setattr(cli_chat, "_answer_permission", answer)
    first = {
        "text": _event(EVENT_TEXT_CHUNK, "partial answer"),
        "approved": SimpleNamespace(
            kind=EVENT_PERMISSION_REQUEST, tool_call_id="approved", sub_session_id=""
        ),
        "child": SimpleNamespace(
            kind="subagent_activity", tool_call_id="pending", sub_session_id="child"
        ),
        "idless": SimpleNamespace(kind="tool_call", tool_call_id="", sub_session_id=""),
    }[activity]
    pending = SimpleNamespace(kind="tool_call", tool_call_id="pending", sub_session_id="")
    permission = SimpleNamespace(
        kind=EVENT_PERMISSION_REQUEST, tool_call_id="pending", sub_session_id=""
    )
    made = _providers(
        monkeypatch,
        _FakeProvider([first, pending, permission], stream_error=RuntimeError("HTTP 429")),
        _FakeProvider(_reply("pong")),
    )
    assert _run_exit_code(_parse("run", "x", "--no-prompt")) == 1
    assert [lane for lane, _ in made] == ["pro"]
