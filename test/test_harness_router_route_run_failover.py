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

from junction.config.paths import data_home
from junction.harness_router import cli
from junction.harness_router.limits import FAILURE_RATE_LIMIT, FAILURE_USAGE_LIMIT
from junction.harness_router.service import HarnessRouter
from junction.providers.base import EVENT_COMPLETE, EVENT_PERMISSION_REQUEST, EVENT_TEXT_CHUNK

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
    import junction.sandbox as sandbox

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
    import junction.cli_chat as cli_chat

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
