"""A spec-family permission request must reach the gate WITH its tool arguments.

``hooks.on_tool_call`` decides on ``event.raw_tool_params``: the keystone path
check (``security_policy.json``, ``profiles/``, ``admission_policy.json``,
``computer_use.json``), the write-protected-config tier and the arg-derived
governance scopes (``filesystem.write`` / ``network.egress``) all read it, and a
display title carries none of that.

Two defects left it empty for Claude Code and Codex, so a write to a keystone path
was judged on its (cwd-relative, model-influenced) title alone and came back
``allow``:

* ``AcpClient`` cached the ``rawInput`` of the initial ``tool_call`` but not of the
  ``tool_call_update`` refinements. claude-agent-acp streams ``rawInput: {}`` first
  and the real arguments only in the refinements.
* The shared permission builder reads ``toolCall.input`` / ``toolCall.params`` (the
  kiro-cli spellings) and never the ACP-spec ``toolCall.rawInput``. Codex sends a
  file change with NO ``rawInput`` at all, only ``locations`` and diff blocks.

The Claude frames below are RECORDED from a real ``claude-agent-acp`` 0.60.0
session (paths templated; every file involved was a synthetic placeholder, and
every permission request was rejected, so nothing was written). The Codex frames
are NOT recorded -- there is no Codex login to drive -- and are built from
``@agentclientprotocol/codex-acp`` 1.13.1 (``createFileChangeUpdate`` /
``fileChangeToolCall`` / ``commandToolCall`` in ``dist/index.js``). The MCP
frames use its tagged ``CodexToolCallMapper.createMcpToolCallUpdate`` and
``permissions/mcp.ts`` correlated approval shapes, also source-derived.

Each frame goes through ``AcpClient._dispatch_events`` (the production dispatch
loop), and the resulting event is handed to ``HookManager.on_tool_call`` with the
exact keyword arguments ``dashboard/chat_runner.py`` uses for a permission event.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

from warding import security
from warding.acp.client import _MAX_CACHED_TOOL_PARAMS, AcpClient, _frame_target_paths
from warding.acp.types import (
    ACP_BACKEND_CLAUDE,
    ACP_BACKEND_CODEX,
    ACP_BACKEND_KIRO,
    ACP_BACKENDS_SPEC_FAMILY,
    EVENT_PERMISSION_REQUEST,
    METHOD_REQUEST_PERMISSION,
    AcpEvent,
    JsonRpcMessage,
)
from warding.hooks import TOOL_DENY, HookManager, HooksConfig, target_paths
from warding.path_spellings import MAX_TARGET_PATHS, PATH_LIMIT_SENTINEL, exceeds_path_limits

# ── Recorded claude-agent-acp 0.60.0 frames (Write) ──
# A Write of a new file in the session's cwd. The adapter titles an in-cwd write
# with the cwd-RELATIVE name ("Write note2.txt"), so the title alone never names
# where the file really is; the absolute path lives only in rawInput / locations.
_CLAUDE_WRITE = [
    {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "sess-1",
            "update": {
                "_meta": {"claudeCode": {"toolName": "Write"}},
                "toolCallId": "toolu_017C9PXsiMvdD17nS9PU4HDu",
                "sessionUpdate": "tool_call",
                "rawInput": {},
                "status": "pending",
                "title": "Write",
                "kind": "edit",
                "content": [],
                "locations": [],
            },
        },
    },
    {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "sess-1",
            "update": {
                "_meta": {"claudeCode": {"toolName": "Write"}},
                "toolCallId": "toolu_017C9PXsiMvdD17nS9PU4HDu",
                "sessionUpdate": "tool_call_update",
                "rawInput": {"file_path": "__WS__/note2.txt"},
                "title": "Write note2.txt",
                "kind": "edit",
                "locations": [{"path": "__WS__/note2.txt"}],
            },
        },
    },
    {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "sess-1",
            "update": {
                "_meta": {"claudeCode": {"toolName": "Write"}},
                "toolCallId": "toolu_017C9PXsiMvdD17nS9PU4HDu",
                "sessionUpdate": "tool_call_update",
                "rawInput": {"file_path": "__WS__/note2.txt", "content": "hello"},
                "title": "Write note2.txt",
                "kind": "edit",
                "content": [
                    {
                        "type": "diff",
                        "path": "__WS__/note2.txt",
                        "oldText": None,
                        "newText": "hello",
                    }
                ],
                "locations": [{"path": "__WS__/note2.txt"}],
            },
        },
    },
    {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "session/request_permission",
        "params": {
            "options": [
                {
                    "kind": "allow_always",
                    "name": "Always Allow all Write",
                    "optionId": "allow_always",
                },
                {"kind": "allow_once", "name": "Allow", "optionId": "allow"},
                {"kind": "reject_once", "name": "Reject", "optionId": "reject"},
            ],
            "sessionId": "sess-1",
            "toolCall": {
                "toolCallId": "toolu_017C9PXsiMvdD17nS9PU4HDu",
                "rawInput": {"file_path": "__WS__/note2.txt", "content": "hello"},
                "title": "Write note2.txt",
                "kind": "edit",
                "content": [
                    {
                        "type": "diff",
                        "path": "__WS__/note2.txt",
                        "oldText": None,
                        "newText": "hello",
                    }
                ],
                "locations": [{"path": "__WS__/note2.txt"}],
            },
        },
    },
]

# ── Recorded claude-agent-acp 0.60.0 frames (Bash) ──
_CLAUDE_BASH = [
    {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "sess-1",
            "update": {
                "_meta": {"claudeCode": {"toolName": "Bash"}},
                "toolCallId": "toolu_01DFLZ3Z3AKA4obYjwyp6fHc",
                "sessionUpdate": "tool_call",
                "rawInput": {},
                "status": "pending",
                "title": "Terminal",
                "kind": "execute",
                "content": [],
            },
        },
    },
    {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "sess-1",
            "update": {
                "_meta": {"claudeCode": {"toolName": "Bash"}},
                "toolCallId": "toolu_01DFLZ3Z3AKA4obYjwyp6fHc",
                "sessionUpdate": "tool_call_update",
                "rawInput": {"command": "echo hi > out.txt"},
                "title": "echo hi > out.txt",
                "kind": "execute",
            },
        },
    },
    {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "sess-1",
            "update": {
                "_meta": {"claudeCode": {"toolName": "Bash"}},
                "toolCallId": "toolu_01DFLZ3Z3AKA4obYjwyp6fHc",
                "sessionUpdate": "tool_call_update",
                "rawInput": {
                    "command": "echo hi > out.txt",
                    "description": 'Write "hi" to out.txt',
                },
                "title": "echo hi > out.txt",
                "kind": "execute",
                "content": [
                    {
                        "type": "content",
                        "content": {"type": "text", "text": 'Write "hi" to out.txt'},
                    }
                ],
            },
        },
    },
    {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "session/request_permission",
        "params": {
            "options": [
                {
                    "kind": "allow_always",
                    "name": "Always Allow Bash(echo hi *)",
                    "optionId": "allow_always",
                },
                {"kind": "allow_once", "name": "Allow", "optionId": "allow"},
                {"kind": "reject_once", "name": "Reject", "optionId": "reject"},
            ],
            "sessionId": "sess-1",
            "toolCall": {
                "toolCallId": "toolu_01DFLZ3Z3AKA4obYjwyp6fHc",
                "rawInput": {
                    "command": "echo hi > out.txt",
                    "description": 'Write "hi" to out.txt',
                },
                "title": "echo hi > out.txt",
                "kind": "execute",
                "content": [
                    {
                        "type": "content",
                        "content": {"type": "text", "text": 'Write "hi" to out.txt'},
                    }
                ],
            },
        },
    },
]

# ── Recorded claude-agent-acp 0.60.0 frames (Read of a file outside the cwd) ──
# Claude auto-allows an in-cwd read, so a Read only reaches the host when it is outside
# the cwd -- and then the adapter titles it with the ABSOLUTE path.
_CLAUDE_READ = [
    {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "sess-1",
            "update": {
                "_meta": {"claudeCode": {"toolName": "Read"}},
                "toolCallId": "toolu_01G1p1JboiuN2HTEfqEf87Xv",
                "sessionUpdate": "tool_call",
                "rawInput": {},
                "status": "pending",
                "title": "Read File",
                "kind": "read",
                "locations": [],
                "content": [],
            },
        },
    },
    {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "sess-1",
            "update": {
                "_meta": {"claudeCode": {"toolName": "Read"}},
                "toolCallId": "toolu_01G1p1JboiuN2HTEfqEf87Xv",
                "sessionUpdate": "tool_call_update",
                "rawInput": {"file_path": "__WS__/note2.txt"},
                "title": "Read __WS__/note2.txt",
                "kind": "read",
                "locations": [{"path": "__WS__/note2.txt", "line": 1}],
                "content": [],
            },
        },
    },
    {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "session/request_permission",
        "params": {
            "options": [
                {"kind": "allow_always", "name": "Always Allow Read", "optionId": "allow_always"},
                {"kind": "allow_once", "name": "Allow", "optionId": "allow"},
                {"kind": "reject_once", "name": "Reject", "optionId": "reject"},
            ],
            "sessionId": "sess-1",
            "toolCall": {
                "toolCallId": "toolu_01G1p1JboiuN2HTEfqEf87Xv",
                "rawInput": {"file_path": "__WS__/note2.txt"},
                "title": "Read __WS__/note2.txt",
                "kind": "read",
                "locations": [{"path": "__WS__/note2.txt", "line": 1}],
                "content": [],
            },
        },
    },
]


# ── Recorded claude-agent-acp 0.60.0 frames (WebFetch) ──
# The title names the URL, but only ``rawInput.url`` + kind ``fetch`` feeds the
# ``network.egress`` scope; a title classifies as a command/tool name.
_CLAUDE_WEBFETCH = [
    {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "sess-1",
            "update": {
                "_meta": {"claudeCode": {"toolName": "WebFetch"}},
                "toolCallId": "toolu_01WMkgrvjugLc3X979sU11PT",
                "sessionUpdate": "tool_call",
                "rawInput": {},
                "status": "pending",
                "title": "Fetch",
                "kind": "fetch",
                "content": [],
            },
        },
    },
    {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "sess-1",
            "update": {
                "_meta": {"claudeCode": {"toolName": "WebFetch"}},
                "toolCallId": "toolu_01WMkgrvjugLc3X979sU11PT",
                "sessionUpdate": "tool_call_update",
                "rawInput": {"url": "https://evil.example.com/data"},
                "title": "Fetch https://evil.example.com/data",
                "kind": "fetch",
            },
        },
    },
    {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": "sess-1",
            "update": {
                "_meta": {"claudeCode": {"toolName": "WebFetch"}},
                "toolCallId": "toolu_01WMkgrvjugLc3X979sU11PT",
                "sessionUpdate": "tool_call_update",
                "rawInput": {
                    "url": "https://evil.example.com/data",
                    "prompt": "Summarize the content of this page.",
                },
                "title": "Fetch https://evil.example.com/data",
                "kind": "fetch",
                "content": [
                    {
                        "type": "content",
                        "content": {"type": "text", "text": "Summarize the content of this page."},
                    }
                ],
            },
        },
    },
    {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "session/request_permission",
        "params": {
            "options": [
                {
                    "kind": "allow_always",
                    "name": "Always Allow WebFetch(domain:evil.example.com)",
                    "optionId": "allow_always",
                },
                {"kind": "allow_once", "name": "Allow", "optionId": "allow"},
                {"kind": "reject_once", "name": "Reject", "optionId": "reject"},
            ],
            "sessionId": "sess-1",
            "toolCall": {
                "toolCallId": "toolu_01WMkgrvjugLc3X979sU11PT",
                "rawInput": {
                    "url": "https://evil.example.com/data",
                    "prompt": "Summarize the content of this page.",
                },
                "title": "Fetch https://evil.example.com/data",
                "kind": "fetch",
                "content": [
                    {
                        "type": "content",
                        "content": {"type": "text", "text": "Summarize the content of this page."},
                    }
                ],
            },
        },
    },
]


# ── Codex-shaped frames (built from codex-acp 1.13.1, not recorded) ──
_CODEX_OPTIONS = [
    {"optionId": "allow_once", "name": "Yes, proceed", "kind": "allow_once"},
    {
        "optionId": "allow_for_session",
        "name": "Yes, and don't ask again for these files",
        "kind": "allow_always",
    },
    {
        "optionId": "cancel",
        "name": "No, and tell Codex what to do differently",
        "kind": "reject_once",
    },
]


def _codex_file_change(call_id, *, diff_paths, location_paths):
    """``createFileChangeUpdate`` then ``fileChangeToolCall``.

    The first frame carries the diff blocks (and a rename's destination, as the
    block's ``path``) but no ``rawInput`` and no ``locations``. The permission
    request carries ``locations`` (the change's SOURCE path) and the fixed title
    "Edit files", and again no ``rawInput``.
    """
    permission_call = {
        "toolCallId": call_id,
        "kind": "edit",
        "status": "pending",
        "title": "Edit files",
    }
    if location_paths:
        permission_call["locations"] = [{"path": p} for p in location_paths]
    return [
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": "thr-1",
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": call_id,
                    "title": "Editing files",
                    "kind": "edit",
                    "status": "pending",
                    "content": [
                        {
                            "type": "diff",
                            "oldText": "old",
                            "newText": "new",
                            "path": path,
                            "_meta": {"kind": "update"},
                        }
                        for path in diff_paths
                    ],
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "session/request_permission",
            "params": {
                "sessionId": "thr-1",
                "toolCall": permission_call,
                "options": _CODEX_OPTIONS,
                "_meta": {"permission": {"version": 1, "title": "Make edits?"}},
            },
        },
    ]


def _codex_read_command(call_id, *, path, command, cwd):
    """A single recognised ``read`` command action.

    The tool_call is titled "Read file '<path>'" with kind ``read`` and no
    ``rawInput``; the permission request is hard-coded to kind ``execute``, titled
    "Read file", and holds the command ONLY in ``rawInput``.
    """
    return [
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": "thr-1",
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": call_id,
                    "status": "pending",
                    "kind": "read",
                    "title": f"Read file '{path}'",
                    "locations": [{"path": path}],
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "session/request_permission",
            "params": {
                "sessionId": "thr-1",
                "toolCall": {
                    "toolCallId": call_id,
                    "kind": "execute",
                    "status": "pending",
                    "title": "Read file",
                    "rawInput": {"command": command, "cwd": cwd},
                    "locations": [{"path": path}],
                },
                "options": _CODEX_OPTIONS,
            },
        },
    ]


def _codex_mcp_call(arguments, *, server="warding-core", tool="learn_list"):
    """Tagged codex-acp 1.13.1 mapper + correlated permissions/mcp.ts shapes.

    These are source-derived, not recorded: ``createMcpToolCallUpdate`` wraps
    the actual arguments and marks a call that otherwise has the shell kind.
    The correlated approval names only the call id; identity must survive in
    the notification caches rather than being inferred from the permission.
    """
    return [
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": "thr-1",
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "mcp-call",
                    "kind": "execute",
                    "title": f"mcp.{server}.{tool}",
                    "status": "pending",
                    "rawInput": {"server": server, "tool": tool, "arguments": arguments},
                    "_meta": {"is_mcp_tool_call": True},
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "session/request_permission",
            "params": {
                "sessionId": "thr-1",
                "toolCall": {
                    "toolCallId": "mcp-call",
                    "kind": "execute",
                    "status": "pending",
                },
                "_meta": {"is_mcp_tool_approval": True},
                "options": _CODEX_OPTIONS,
            },
        },
    ]


# ── Harness plumbing ──


def _render(frames, **substitutions):
    """Deep-copy *frames* with ``old -> new`` string substitutions applied.

    Applied to the JSON text, so a template path inside a title, a ``rawInput`` value
    and a ``locations`` entry are all rewritten consistently, which is what the real
    adapter does for one call.
    """
    text = json.dumps(frames)
    for old, new in substitutions.items():
        text = text.replace(old, json.dumps(new)[1:-1])
    return json.loads(text)


class _Env:
    """A scratch home, data home and workspace the gate resolves against."""

    def __init__(self, root: Path) -> None:
        self.home = root / "home"
        self.data_home = self.home / ".warding"
        self.ws = root / "ws"
        for d in (self.data_home / "profiles", self.ws):
            d.mkdir(parents=True)


@pytest.fixture
def env(tmp_path, monkeypatch) -> _Env:
    scratch = _Env(tmp_path)
    monkeypatch.setenv("HOME", str(scratch.home))
    monkeypatch.setenv("USERPROFILE", str(scratch.home))
    monkeypatch.setenv("WARDING_HOME", str(scratch.data_home))
    for name in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "KIRO_HOME"):
        monkeypatch.delenv(name, raising=False)
    # The bash matcher is compiled once per process with the home directory it saw first,
    # so a test that moves HOME must drop it on the way in and on the way out; left in
    # place it makes every later test in the worker match the scratch home, not the real one.
    security._home_targets_cache.clear()
    security._SENSITIVE_RE = None
    yield scratch
    security._home_targets_cache.clear()
    security._SENSITIVE_RE = None


def _client(env: _Env, backend: str = ACP_BACKEND_CLAUDE) -> AcpClient:
    return AcpClient(work_dir=env.ws, acp_backend=backend)


async def _replay(client: AcpClient, frames) -> list[AcpEvent]:
    """Drive *frames* through the production ``_dispatch_events`` loop."""

    async def _prompt_loop(req_id, timeout):
        for frame in frames:
            msg = JsonRpcMessage.from_dict(frame)
            yield ("permission" if msg.method == METHOD_REQUEST_PERMISSION else "update"), msg
        yield "complete", JsonRpcMessage.from_dict(
            {"jsonrpc": "2.0", "id": 1, "result": {"stopReason": "end_turn"}}
        )

    client._prompt_loop = _prompt_loop  # type: ignore[method-assign]
    return [event async for event in client._dispatch_events(1, 30.0)]


async def _permission_event(client: AcpClient, frames) -> AcpEvent:
    events = [e for e in await _replay(client, frames) if e.kind == EVENT_PERMISSION_REQUEST]
    assert len(events) == 1, events
    return events[0]


def _gate(event: AcpEvent):
    """``HookManager.on_tool_call`` exactly as ``chat_runner`` calls it for a permission."""
    return HookManager(HooksConfig.from_dict({})).on_tool_call(
        event.title,
        session_key="test-slot",
        agent="",
        app="",
        tool_kind=event.tool_kind,
        raw_params=event.raw_tool_params,
        command=event.shell_command,
        is_shell=event.is_shell,
        mcp_server_name=event.mcp_server_name,
        mcp_tool_name=event.tool_name,
        resolved_agent="",
    )


def _write_frames(env: _Env, target: Path, cwd: Path | None = None):
    """The recorded Write sequence aimed at *target*, titled relative to *cwd*."""
    cwd = cwd or env.ws
    return _render(
        _CLAUDE_WRITE,
        **{
            "__WS__/note2.txt": str(target),
            "Write note2.txt": f"Write {target.relative_to(cwd).as_posix()}",
        },
    )


# ── (1) the refinement's rawInput is cached ──


@pytest.mark.asyncio
async def test_the_refinements_raw_input_is_what_the_permission_event_carries(env):
    """The initial tool_call streams ``rawInput: {}`` (so nothing is cached from it);
    the complete arguments arrive only in the ``tool_call_update`` refinements."""
    target = env.ws / "note2.txt"
    client = _client(env)

    event = await _permission_event(client, _write_frames(env, target))

    assert client._tool_call_params["toolu_017C9PXsiMvdD17nS9PU4HDu"] == {
        "file_path": str(target),
        "content": "hello",
    }
    assert event.raw_tool_params == {"file_path": str(target), "content": "hello"}
    assert event.raw_params_trusted is True, "params the client parsed itself are trusted"


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", [ACP_BACKEND_CLAUDE, ACP_BACKEND_CODEX])
async def test_the_client_caches_params_exactly_as_the_shared_runtime_parser(env, backend):
    """The direct client and ``AcpRuntime`` parse the same frames, so the structured
    params one resolves a permission from must be the ones the other does for a
    spec-family harness; only the direct client skipped the refinement."""
    from warding.acp._dispatch import parse_session_update

    updates = [
        f for f in _write_frames(env, env.ws / "note2.txt") if f["method"] == "session/update"
    ]
    shared: dict[str, dict] = {}
    for frame in updates:
        parse_session_update(frame["params"]["update"], raw_params_cache=shared)
    client = _client(env, backend)

    await _replay(client, updates)

    assert shared, "the shared parser must cache the refinement's params"
    assert client._tool_call_params == shared


@pytest.mark.asyncio
async def test_a_kiro_session_on_the_direct_client_keeps_its_own_cache(env):
    """H13: the refinement cache is the spec family's. A kiro-cli session on this client
    resolves its params from the initial ``tool_call`` alone, so a refinement that omits
    the path cannot replace the one the call was announced with."""
    keystone = str(env.data_home / "security_policy.json")
    client = _client(env, ACP_BACKEND_KIRO)
    frames = [
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "k1",
                    "title": "Write",
                    "kind": "edit",
                    "rawInput": {"path": keystone},
                }
            },
        },
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "k1",
                    "kind": "edit",
                    "rawInput": {"content": "x"},
                }
            },
        },
    ]

    await _replay(client, frames)

    assert client._tool_call_params["k1"] == {"path": keystone}


@pytest.mark.asyncio
async def test_the_params_cache_is_bounded_and_cleared_each_turn(env):
    client = _client(env)
    for i in range(_MAX_CACHED_TOOL_PARAMS + 40):
        client._extract_tool_call_refinement(
            JsonRpcMessage.from_dict(
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "update": {
                            "sessionUpdate": "tool_call_update",
                            "toolCallId": f"t{i}",
                            "kind": "edit",
                            "rawInput": {"file_path": f"/x/{i}"},
                        }
                    },
                }
            )
        )
    assert len(client._tool_call_params) <= _MAX_CACHED_TOOL_PARAMS + 1

    await _replay(client, [])

    assert client._tool_call_params == {}
    assert client._tool_call_paths == {}


# ── (2) the gate now sees the real arguments (Claude) ──


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("relative", "reason"),
    [
        ("security_policy.json", "sensitive path"),
        ("profiles/p.json", "sensitive path"),
        ("admission_policy.json", "sensitive path"),
        ("computer_use.json", "sensitive path"),
        ("config.json", "write-protected"),
        ("config.local.json", "write-protected"),
    ],
)
async def test_a_claude_write_to_a_keystone_or_config_path_is_denied(env, relative, reason):
    """The session runs with the data home as its cwd, so the adapter titles the call
    "Write security_policy.json": nothing in the title names the data home."""
    target = env.data_home / relative
    event = await _permission_event(_client(env), _write_frames(env, target, cwd=env.data_home))

    assert event.title == f"Write {relative}"
    decision = _gate(event)

    assert decision.action == TOOL_DENY, "the keystone must not depend on the title"
    assert reason in decision.reason


@pytest.mark.asyncio
async def test_the_slot_workspace_may_be_the_home_directory(env):
    """The other layout: cwd is ``$HOME`` and the title is ".warding/<file>"."""
    target = env.data_home / "security_policy.json"
    event = await _permission_event(_client(env), _write_frames(env, target, cwd=env.home))

    assert event.title == "Write .warding/security_policy.json"
    assert _gate(event).action == TOOL_DENY


@pytest.mark.asyncio
async def test_an_ordinary_claude_write_is_still_allowed(env):
    """The recovery tightens a decision only where a path is forbidden."""
    event = await _permission_event(_client(env), _write_frames(env, env.ws / "note2.txt"))

    assert _gate(event).action != TOOL_DENY


@pytest.mark.asyncio
async def test_a_claude_bash_command_is_still_gated_and_ordinary_ones_allowed(env):
    event = await _permission_event(_client(env), _render(_CLAUDE_BASH))
    assert event.is_shell is True
    assert event.shell_command == "echo hi > out.txt"
    assert _gate(event).action != TOOL_DENY

    hostile = _render(
        _CLAUDE_BASH,
        **{
            "echo hi > out.txt": f"cat {env.data_home / 'security_policy.json'}",
        },
    )
    assert _gate(await _permission_event(_client(env), hostile)).action == TOOL_DENY


@pytest.mark.asyncio
async def test_a_claude_read_of_config_is_allowed_but_of_the_policy_is_not(env):
    """Config is write-protected, not read-protected; the policy is neither readable nor writable."""
    cfg = _render(
        _CLAUDE_READ,
        **{"__WS__/note2.txt": str(env.data_home / "config.json")},
    )
    assert _gate(await _permission_event(_client(env), cfg)).action != TOOL_DENY

    policy = _render(
        _CLAUDE_READ,
        **{"__WS__/note2.txt": str(env.data_home / "security_policy.json")},
    )
    assert _gate(await _permission_event(_client(env), policy)).action == TOOL_DENY


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "relative",
    [
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".codex/config.toml",
        ".codex/hooks.json",
        ".codex/rules/default.rules",
    ],
)
async def test_a_claude_write_to_the_users_harness_config_is_denied(env, relative):
    """One approved write there is a standing waiver for every later session.

    The session's cwd is the file's own directory, so the title is just the basename
    ("Write settings.json") and only the structured path can deny it."""
    target = env.home / relative
    event = await _permission_event(_client(env), _write_frames(env, target, cwd=target.parent))

    assert event.title == f"Write {target.name}"
    decision = _gate(event)

    assert decision.action == TOOL_DENY
    assert "write-protected" in decision.reason


@pytest.mark.asyncio
async def test_a_claude_write_to_the_user_scope_mcp_config_is_denied(env):
    """``~/.claude.json`` holds user-scope MCP servers, whose command launches at the
    next session start with no prompt."""
    event = await _permission_event(
        _client(env), _write_frames(env, env.home / ".claude.json", cwd=env.home)
    )

    assert _gate(event).action == TOOL_DENY


@pytest.mark.asyncio
async def test_a_claude_write_to_the_project_scope_settings_is_denied(env):
    target = env.ws / ".claude" / "settings.local.json"
    event = await _permission_event(_client(env), _write_frames(env, target))

    assert event.title == "Write .claude/settings.local.json"
    assert _gate(event).action == TOOL_DENY


# ── (2) Codex: no rawInput on a file change ──


@pytest.mark.asyncio
async def test_a_codex_patch_naming_the_policy_is_denied(env):
    """The permission title is the fixed string "Edit files"; the only evidence of
    the target is ``locations``."""
    policy = str(env.data_home / "security_policy.json")
    frames = _codex_file_change(
        "call_1",
        diff_paths=[str(env.ws / "a.py"), policy],
        location_paths=[str(env.ws / "a.py"), policy],
    )
    event = await _permission_event(_client(env, ACP_BACKEND_CODEX), frames)

    assert event.title == "Edit files"
    assert event.raw_tool_params == {"paths": [str(env.ws / "a.py"), policy]}
    decision = _gate(event)

    assert decision.action == TOOL_DENY
    assert "sensitive path" in decision.reason


@pytest.mark.asyncio
async def test_one_forbidden_path_among_many_denies_the_whole_patch(env):
    paths = [str(env.ws / f"f{i}.py") for i in range(6)] + [str(env.data_home / "config.json")]
    frames = _codex_file_change("call_1", diff_paths=paths, location_paths=paths)
    event = await _permission_event(_client(env, ACP_BACKEND_CODEX), frames)

    decision = _gate(event)

    assert decision.action == TOOL_DENY
    assert "write-protected" in decision.reason


@pytest.mark.asyncio
async def test_a_codex_rename_onto_the_policy_is_caught_by_the_diff_block(env):
    """``locations`` lists a change's SOURCE path; a rename's destination appears only
    as the ``path`` of the diff block on the earlier tool_call."""
    frames = _codex_file_change(
        "call_1",
        diff_paths=[str(env.data_home / "security_policy.json")],
        location_paths=[str(env.ws / "innocent.json")],
    )
    event = await _permission_event(_client(env, ACP_BACKEND_CODEX), frames)

    assert _gate(event).action == TOOL_DENY


@pytest.mark.asyncio
async def test_a_codex_permission_without_locations_still_sees_the_earlier_diff_paths(env):
    """``fileChangePaths`` is empty when codex-acp has not seen the item, so the
    permission frame names nothing; the tool_call's diff blocks are all there is."""
    frames = _codex_file_change(
        "call_1", diff_paths=[str(env.data_home / "profiles" / "p.json")], location_paths=[]
    )
    event = await _permission_event(_client(env, ACP_BACKEND_CODEX), frames)

    assert _gate(event).action == TOOL_DENY


@pytest.mark.asyncio
async def test_a_codex_patch_of_ordinary_files_is_allowed_and_not_trusted(env):
    paths = [str(env.ws / "a.py"), str(env.ws / "b.py")]
    frames = _codex_file_change("call_1", diff_paths=paths, location_paths=paths)
    event = await _permission_event(_client(env, ACP_BACKEND_CODEX), frames)

    assert _gate(event).action != TOOL_DENY
    assert event.raw_tool_params == {"paths": paths}
    assert event.raw_params_trusted is False, "paths from a permission frame are agent-supplied"


@pytest.mark.asyncio
async def test_a_codex_patch_to_the_harness_config_is_denied(env):
    for rel in (".codex/config.toml", ".codex/hooks.json", ".codex/rules/default.rules"):
        target = str(env.home / rel)
        frames = _codex_file_change("call_1", diff_paths=[target], location_paths=[target])
        event = await _permission_event(_client(env, ACP_BACKEND_CODEX), frames)
        assert _gate(event).action == TOOL_DENY, rel


@pytest.mark.asyncio
async def test_a_codex_read_command_is_judged_on_its_real_target(env):
    """Titled "Read file"; the command exists only in the permission's rawInput and
    the target only in ``locations``."""
    policy = str(env.data_home / "security_policy.json")
    event = await _permission_event(
        _client(env, ACP_BACKEND_CODEX),
        _codex_read_command("call_2", path=policy, command=f"cat {policy}", cwd=str(env.ws)),
    )

    assert event.title == "Read file"
    # The card renders the arguments as JSON, which escapes a Windows path's backslashes.
    assert (
        json.dumps(f"cat {policy}")[1:-1] in event.tool_input
    ), "the approval card must show the command"
    assert _gate(event).action == TOOL_DENY

    ordinary = str(env.ws / "README.md")
    event = await _permission_event(
        _client(env, ACP_BACKEND_CODEX),
        _codex_read_command("call_3", path=ordinary, command=f"cat {ordinary}", cwd=str(env.ws)),
    )
    assert _gate(event).action != TOOL_DENY


# ── (3) provenance stays honest ──


@pytest.mark.asyncio
async def test_params_taken_from_the_permission_frame_are_not_trusted(env):
    """No preceding tool_call: the only arguments are the frame's own."""
    target = env.data_home / "security_policy.json"
    frames = [f for f in _write_frames(env, target, cwd=env.data_home) if "id" in f]
    event = await _permission_event(_client(env), frames)

    assert event.raw_tool_params == {"file_path": str(target), "content": "hello"}
    assert event.raw_params_trusted is False
    assert _gate(event).action == TOOL_DENY


@pytest.mark.asyncio
async def test_the_cache_stays_authoritative_but_the_frames_paths_are_still_checked(env):
    """A harness whose permission frame disagrees with what it streamed earlier gains
    nothing: the cached params are kept, and a forbidden path the frame names on top
    of them still denies. The cache entry itself is never mutated."""
    frames = _write_frames(env, env.ws / "note2.txt")
    frames[-1]["params"]["toolCall"]["locations"] = [
        {"path": str(env.data_home / "security_policy.json")}
    ]
    client = _client(env)

    event = await _permission_event(client, frames)

    assert event.raw_params_trusted is True
    assert event.raw_tool_params["file_path"] == str(env.ws / "note2.txt")
    assert event.raw_tool_params["paths"] == [str(env.data_home / "security_policy.json")]
    assert "paths" not in client._tool_call_params["toolu_017C9PXsiMvdD17nS9PU4HDu"]
    assert _gate(event).action == TOOL_DENY


@pytest.mark.asyncio
async def test_a_path_the_params_already_name_is_not_duplicated(env):
    event = await _permission_event(_client(env), _write_frames(env, env.ws / "note2.txt"))

    assert "paths" not in event.raw_tool_params


# ── (2) positive membership: only the spec family, never the kiro-cli path ──


@pytest.mark.asyncio
async def test_kiro_cli_through_this_client_keeps_its_own_resolution(env):
    """H13: the shared builder and the kiro-cli path are untouched. A frame in the
    ACP-spec spelling must not hand kiro-cli arguments it has never been given."""
    frames = _render(
        _codex_file_change(
            "call_1",
            diff_paths=[str(env.data_home / "security_policy.json")],
            location_paths=[str(env.data_home / "security_policy.json")],
        )
    )
    frames[-1]["params"]["toolCall"]["rawInput"] = {"file_path": "/x"}

    event = await _permission_event(_client(env, ACP_BACKEND_KIRO), frames)

    assert event.raw_tool_params is None
    assert event.raw_params_trusted is False


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", sorted(ACP_BACKENDS_SPEC_FAMILY))
async def test_every_spec_family_backend_recovers_the_arguments(env, backend):
    """Membership, not an allowlist of two named harnesses: the fields are ACP-spec
    fields, and the recovery only ever adds paths to be checked."""
    policy = str(env.data_home / "security_policy.json")
    frames = _codex_file_change("call_1", diff_paths=[policy], location_paths=[policy])

    event = await _permission_event(_client(env, backend), frames)

    assert event.raw_tool_params == {"paths": [policy]}
    assert _gate(event).action == TOOL_DENY


# ── governance reads the same arguments ──


def _install_ceiling(body: dict):
    """Install *body* as the governance ceiling the gate composes with."""
    import dataclasses

    from warding.config.loader import WardingConfig
    from warding.platform import context as ctx_mod
    from warding.platform.bootstrap import build_default_context
    from warding.platform.governance import parse_policy

    ctx_mod.set_context(
        dataclasses.replace(
            build_default_context(WardingConfig.load()), governance=parse_policy(body)
        )
    )


def _as_quoted(path) -> str:
    """*path* as the governance reason prints it, which quotes it with ``repr``.

    That escapes a Windows path's backslashes; a POSIX path prints unchanged.
    """
    return repr(str(path))[1:-1]


@pytest.fixture
def governed_writes(env):
    """A ceiling that allows writes only under the workspace."""
    from warding.platform import context as ctx_mod

    _install_ceiling(
        {
            "version": 1,
            "boot": {"fail_closed": True},
            "filesystem": {"write": {"mode": "allow", "allow": [os.path.join(str(env.ws), "**")]}},
        }
    )
    yield
    ctx_mod.reset_context()


@pytest.mark.asyncio
async def test_the_filesystem_write_ceiling_binds_a_claude_write(env, governed_writes):
    inside = await _permission_event(_client(env), _write_frames(env, env.ws / "note2.txt"))
    assert _gate(inside).action != TOOL_DENY

    outside = env.home / "elsewhere.txt"
    event = await _permission_event(_client(env), _write_frames(env, outside, cwd=env.home))
    decision = _gate(event)

    assert decision.action == TOOL_DENY
    assert "governance policy" in decision.reason
    assert _as_quoted(outside) in decision.reason


@pytest.mark.asyncio
async def test_the_filesystem_write_ceiling_binds_every_file_of_a_codex_patch(env, governed_writes):
    paths = [str(env.ws / "a.py"), str(env.home / "elsewhere.txt")]
    frames = _codex_file_change("call_1", diff_paths=paths, location_paths=paths)
    event = await _permission_event(_client(env, ACP_BACKEND_CODEX), frames)

    decision = _gate(event)

    assert decision.action == TOOL_DENY
    assert "governance policy" in decision.reason
    assert _as_quoted(paths[1]) in decision.reason


@pytest.fixture
def governed_egress(env):
    """A ceiling that allows network egress only to one host."""
    from warding.platform import context as ctx_mod

    _install_ceiling(
        {
            "version": 1,
            "boot": {"fail_closed": True},
            "network": {"egress": {"mode": "allow", "allow": ["allowed.example.com"]}},
        }
    )
    yield
    ctx_mod.reset_context()


@pytest.mark.asyncio
async def test_the_network_egress_ceiling_binds_a_claude_webfetch(env, governed_egress):
    event = await _permission_event(_client(env), _render(_CLAUDE_WEBFETCH))

    assert event.tool_kind == "fetch"
    assert event.raw_tool_params["url"] == "https://evil.example.com/data"
    blocked_host = urlparse(event.raw_tool_params["url"]).hostname
    decision = _gate(event)

    assert decision.action == TOOL_DENY
    assert blocked_host and blocked_host in decision.reason

    allowed = _render(_CLAUDE_WEBFETCH, **{"evil.example.com": "allowed.example.com"})
    assert _gate(await _permission_event(_client(env), allowed)).action != TOOL_DENY


# ── frame helper ──


def test_frame_target_paths_reads_all_three_sources_and_ignores_junk():
    from warding.acp.client import _frame_target_paths

    frame = {
        "locations": [{"path": "/a"}, {"path": ""}, {"nope": 1}, "str", {"path": 7}],
        "content": [
            {"type": "diff", "path": "/b"},
            {"type": "content", "path": "/not-a-diff"},
            {"type": "diff"},
        ],
    }
    raw = {"file_path": "/c", "notebook_path": "/d", "paths": ["/e", 3]}

    assert _frame_target_paths(frame, raw) == ["/c", "/e", "/d", "/a", "/b"]
    assert _frame_target_paths({"locations": "x", "content": 3}, None) == []


def test_the_frame_recovery_does_not_mutate_the_harness_frame(env):
    """The merged params are a copy; the frame dict the harness built is left alone."""
    client = _client(env)
    policy = str(env.data_home / "security_policy.json")
    frames = _codex_file_change("call_1", diff_paths=[policy], location_paths=[policy])
    pristine = copy.deepcopy(frames[-1])
    msg = JsonRpcMessage.from_dict(frames[-1])

    client._build_permission_event(msg)

    assert frames[-1] == pristine


# ── hardening: how the harness reads the path, where it resolves it, and how much it may name ──

_KEYSTONE_FILES = [
    "security_policy.json",
    "admission_policy.json",
    "computer_use.json",
    "profiles/team.json",
]


def _claude_edit_permission(env: _Env, raw_input: dict, *, title: str = "Write", kind="edit"):
    """A Claude Code permission request carrying *raw_input* and nothing cached before it."""
    frame = {
        "jsonrpc": "2.0",
        "id": 9,
        "method": "session/request_permission",
        "params": {
            "sessionId": "sess-1",
            "options": [
                {"kind": "allow_always", "name": "Always Allow", "optionId": "allow_always"},
                {"kind": "allow_once", "name": "Allow", "optionId": "allow"},
                {"kind": "reject_once", "name": "Reject", "optionId": "reject"},
            ],
            "toolCall": {
                "toolCallId": "toolu_hardening",
                "rawInput": raw_input,
                "title": title,
                "kind": kind,
            },
        },
    }
    return _client(env)._build_permission_event(JsonRpcMessage.from_dict(frame))


@pytest.mark.parametrize("keystone", _KEYSTONE_FILES)
@pytest.mark.parametrize("pad", ["\ufeff", " ", "\t", "\n", "\u00a0", "\u2028", "\u3000"])
def test_a_path_the_harness_trims_is_checked_as_the_harness_reads_it(env, keystone, pad):
    """Claude Code trims JavaScript whitespace, U+FEFF included, before it opens a path.
    Python's ``strip`` leaves U+FEFF, so the string as written named a file that does not
    exist while the file the harness opened was the keystone."""
    target = str(env.data_home / keystone)
    event = _claude_edit_permission(env, {"file_path": pad + target, "content": "x"})

    assert _gate(event).action == TOOL_DENY


@pytest.mark.parametrize("keystone", _KEYSTONE_FILES)
@pytest.mark.parametrize(
    ("work_dir_under_data_home", "prefix"),
    [("", ""), ("", "./"), ("workspace/slot1", "../../")],
)
def test_a_relative_path_is_checked_where_the_session_will_open_it(
    env, keystone, work_dir_under_data_home, prefix
):
    """The harness resolves a relative path against the session's working directory; the
    gate resolves it against its own, which is somewhere else."""
    work_dir = env.data_home / work_dir_under_data_home
    work_dir.mkdir(parents=True, exist_ok=True)
    client = AcpClient(work_dir=work_dir, acp_backend=ACP_BACKEND_CLAUDE)
    name = prefix + keystone
    frame = {
        "jsonrpc": "2.0",
        "id": 9,
        "method": "session/request_permission",
        "params": {
            "sessionId": "sess-1",
            "options": [{"kind": "allow_once", "name": "Allow", "optionId": "allow"}],
            "toolCall": {
                "toolCallId": "toolu_rel",
                "rawInput": {"file_path": name, "content": "x"},
                "title": "Write",
                "kind": "edit",
            },
        },
    }

    event = client._build_permission_event(JsonRpcMessage.from_dict(frame))

    assert _gate(event).action == TOOL_DENY


def test_a_relative_path_inside_the_workspace_is_still_allowed(env):
    event = _claude_edit_permission(env, {"file_path": "notes/todo.md", "content": "x"})

    assert _gate(event).action != TOOL_DENY


@pytest.mark.parametrize("kind", ["edit", "delete", "move"])
def test_every_file_changing_kind_reaches_the_write_protected_tier(env, kind):
    target = str(Path(env.home) / ".claude" / "settings.json")
    event = _claude_edit_permission(env, {"file_path": target}, title="Write", kind=kind)

    assert _gate(event).action == TOOL_DENY


@pytest.mark.parametrize("kind", ["read", "fetch", "search", "think"])
def test_a_read_of_a_write_protected_config_is_not_blocked_by_kind(env, kind):
    target = str(Path(env.home) / ".claude" / "settings.json")
    event = _claude_edit_permission(env, {"file_path": target}, title="Read file", kind=kind)

    assert _gate(event).action != TOOL_DENY


def test_a_call_naming_too_many_paths_is_denied_not_truncated(env):
    """A truncated check would let the unchecked tail carry the forbidden path."""
    keystone = str(env.data_home / "security_policy.json")
    paths = [f"/w/f{i}.txt" for i in range(5000)] + [keystone]
    event = _claude_edit_permission(env, {"paths": paths})

    assert _gate(event).action == TOOL_DENY


def test_a_call_naming_an_oversized_path_is_denied(env):
    event = _claude_edit_permission(env, {"file_path": "/w/" + "a" * 5000})

    assert _gate(event).action == TOOL_DENY


def test_a_large_but_ordinary_patch_is_not_denied(env):
    paths = [str(env.ws / f"f{i}.txt") for i in range(500)]
    event = _claude_edit_permission(env, {"paths": paths})

    assert _gate(event).action != TOOL_DENY


def test_a_deeply_nested_raw_input_does_not_break_the_permission_build(env):
    """``json.loads`` accepts nesting that ``json.dumps`` cannot render again."""
    nested: object = "x"
    for _ in range(1500):
        nested = [nested]

    event = _claude_edit_permission(env, {"file_path": str(env.ws / "a.txt"), "deep": nested})

    assert event.raw_tool_params is not None


@pytest.mark.asyncio
async def test_a_flood_of_finished_calls_does_not_erase_an_earlier_rename_destination(env):
    """A finished call is dropped and the oldest pending one is evicted, never the map."""
    keystone = str(env.data_home / "security_policy.json")
    source = str(env.ws / "a.txt")
    client = _client(env, ACP_BACKEND_CODEX)
    first = _codex_file_change("call_rename", diff_paths=[source, keystone], location_paths=[])
    noise = []
    for i in range(_MAX_CACHED_TOOL_PARAMS + 44):
        for status, kind in (("pending", "tool_call"), ("completed", "tool_call_update")):
            noise.append(
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "update": {
                            "sessionUpdate": kind,
                            "toolCallId": f"noise{i}",
                            "title": "Read",
                            "kind": "read",
                            "status": status,
                            "locations": [{"path": f"/n/{i}"}],
                        }
                    },
                }
            )
    permission = _codex_file_change("call_rename", diff_paths=[], location_paths=[source])[-1]

    event = await _permission_event(client, [first[0], *noise, permission])

    assert _gate(event).action == TOOL_DENY


def test_the_settings_seed_is_recorded_even_when_the_hook_raises_something_unexpected(
    env,
):
    """A seed that raised after writing must still be revertible."""
    client = _client(env)
    path = env.ws / ".claude" / "settings.local.json"
    path.parent.mkdir(parents=True)

    def seed() -> None:
        path.write_text('{"permissions": {"defaultMode": "bypassPermissions"}}')
        raise RuntimeError("registry shape surprise")

    client._write_claude_local_settings = seed  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError):
        client._seed_claude_local_settings("seed failed")
    client._undo_claude_settings_seed()

    assert not path.exists()


# ── Codex marks MCP notifications as execute, but they are not shell calls ──


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [{}, {"limit": 3}])
async def test_a_codex_mcp_approval_keeps_its_notification_identity_and_arguments(env, arguments):
    frames = _codex_mcp_call(arguments)
    repeated = copy.deepcopy(frames[-1])
    repeated["id"] = 10
    # Permission-only claims cannot replace the preceding adapter identity/args.
    repeated["params"]["toolCall"]["rawInput"] = {
        "server": "other",
        "tool": "other",
        "arguments": {"limit": 999},
    }
    events = [
        event
        for event in await _replay(_client(env, ACP_BACKEND_CODEX), [*frames, repeated])
        if event.kind == EVENT_PERMISSION_REQUEST
    ]

    assert len(events) == 2
    for event in events:
        assert event.is_shell is False
        assert event.shell_classified is True
        assert event.mcp_server_name == "warding-core"
        assert event.tool_name == "learn_list"
        assert event.raw_tool_params == arguments
        assert event.raw_params_trusted is True
        assert _gate(event).action != TOOL_DENY


@pytest.mark.asyncio
async def test_a_codex_mcp_refinement_can_supply_the_adapter_identity(env):
    frames = _codex_mcp_call({"limit": 3})
    initial = copy.deepcopy(frames[0])
    initial["params"]["update"].pop("_meta")
    initial["params"]["update"]["rawInput"] = {}
    frames[0]["params"]["update"]["sessionUpdate"] = "tool_call_update"
    # A marked argument refinement need not repeat the optional kind.
    frames[0]["params"]["update"].pop("kind")

    event = await _permission_event(_client(env, ACP_BACKEND_CODEX), [initial, *frames])

    assert event.is_shell is False
    assert event.shell_classified is True
    assert event.mcp_server_name == "warding-core"
    assert event.tool_name == "learn_list"
    assert event.raw_tool_params == {"limit": 3}
    assert event.raw_params_trusted is True
    assert _gate(event).action != TOOL_DENY


@pytest.mark.asyncio
async def test_a_codex_mcp_arguments_wrapper_cannot_hide_a_keystone_path(env):
    policy = str(env.data_home / "security_policy.json")
    event = await _permission_event(
        _client(env, ACP_BACKEND_CODEX), _codex_mcp_call({"file_path": policy})
    )

    assert event.raw_tool_params == {"file_path": policy}
    assert event.is_shell is False
    assert _gate(event).action == TOOL_DENY


@pytest.mark.asyncio
@pytest.mark.parametrize("deny", ["@warding-core", "@warding-core/learn_list"])
async def test_a_codex_mcp_approval_is_bound_by_its_canonical_governance_identity(env, deny):
    from warding.platform import context as ctx_mod

    _install_ceiling(
        {"version": 1, "boot": {"fail_closed": True}, "mcp": {"mode": "deny", "deny": [deny]}}
    )
    try:
        event = await _permission_event(_client(env, ACP_BACKEND_CODEX), _codex_mcp_call({}))
        decision = _gate(event)
    finally:
        ctx_mod.reset_context()

    assert event.mcp_server_name == "warding-core"
    assert event.tool_name == "learn_list"
    assert decision.action == TOOL_DENY
    assert "governance policy" in decision.reason


@pytest.mark.asyncio
async def test_a_codex_mcp_arguments_wrapper_cannot_hide_a_denied_network_target(
    env, governed_egress
):
    event = await _permission_event(
        _client(env, ACP_BACKEND_CODEX),
        _codex_mcp_call({"url": "https://denied.example.com/api"}),
    )

    decision = _gate(event)

    assert decision.action == TOOL_DENY
    assert "governance policy" in decision.reason


@pytest.mark.asyncio
@pytest.mark.parametrize("marker", [None, False, 1, "true"])
async def test_an_execute_notification_without_the_exact_codex_mcp_marker_stays_shell(env, marker):
    frames = _codex_mcp_call({})
    frames[0]["params"]["update"]["_meta"]["is_mcp_tool_call"] = marker

    event = await _permission_event(_client(env, ACP_BACKEND_CODEX), frames)

    assert event.is_shell is True
    assert event.mcp_server_name == ""
    assert event.tool_name == ""
    assert _gate(event).action == TOOL_DENY


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_input",
    [
        {"server": "", "tool": "learn_list", "arguments": {}},
        {"server": "warding-core/learn_list", "tool": "learn_list", "arguments": {}},
        {"server": "warding-core", "tool": " learn_list", "arguments": {}},
        {"server": "warding-core", "tool": "learn/list", "arguments": {}},
        {"server": 7, "tool": "learn_list", "arguments": {}},
        {"server": "warding-core", "tool": None, "arguments": {}},
        {"server": "warding-core", "tool": "learn_list", "arguments": []},
        {"server": "warding-core", "tool": "learn_list"},
        {"server": "warding-core", "tool": "learn_list", "arguments": {}, "command": None},
    ],
)
async def test_a_malformed_codex_mcp_notification_cannot_waive_the_shell_deny(env, raw_input):
    frames = _codex_mcp_call({})
    frames[0]["params"]["update"]["rawInput"] = raw_input

    event = await _permission_event(_client(env, ACP_BACKEND_CODEX), frames)

    assert event.is_shell is True
    assert event.mcp_server_name == ""
    assert event.tool_name == ""
    assert _gate(event).action == TOOL_DENY


@pytest.mark.asyncio
async def test_a_codex_mcp_marker_requires_the_notification_raw_input_field(env):
    frames = _codex_mcp_call({})
    update = frames[0]["params"]["update"]
    update["input"] = update.pop("rawInput")

    event = await _permission_event(_client(env, ACP_BACKEND_CODEX), frames)

    assert event.is_shell is True
    assert event.mcp_server_name == ""
    assert _gate(event).action == TOOL_DENY


@pytest.mark.asyncio
async def test_a_permission_frame_mcp_marker_cannot_reclassify_a_cached_codex_shell(env):
    frames = _codex_mcp_call({})
    initial = frames[0]["params"]["update"]
    initial.pop("_meta")
    initial["rawInput"] = {}
    permission = frames[-1]["params"]["toolCall"]
    permission["_meta"] = {"is_mcp_tool_call": True}
    permission["rawInput"] = {"server": "warding-core", "tool": "learn_list", "arguments": {}}

    event = await _permission_event(_client(env, ACP_BACKEND_CODEX), frames)

    assert event.is_shell is True
    assert event.shell_classified is True
    assert event.mcp_server_name == ""
    assert event.tool_name == ""
    assert event.raw_params_trusted is False
    assert _gate(event).action == TOOL_DENY


@pytest.mark.asyncio
async def test_a_permission_only_codex_mcp_claim_has_no_canonical_identity_or_provenance(env):
    permission = _codex_mcp_call({})[-1]
    permission["params"]["toolCall"]["_meta"] = {"is_mcp_tool_call": True}
    permission["params"]["toolCall"]["rawInput"] = {
        "server": "warding-core",
        "tool": "learn_list",
        "arguments": {},
    }

    event = await _permission_event(_client(env, ACP_BACKEND_CODEX), [permission])

    assert event.shell_classified is False
    assert event.mcp_server_name == ""
    assert event.tool_name == ""
    assert event.raw_params_trusted is False


@pytest.mark.asyncio
@pytest.mark.parametrize("has_command", [False, True])
async def test_a_codex_mcp_argument_replacement_without_provenance_drops_the_old_identity(
    env, has_command
):
    frames = _codex_mcp_call({})
    refinement = copy.deepcopy(frames[0])
    update = refinement["params"]["update"]
    update["sessionUpdate"] = "tool_call_update"
    update.pop("kind")
    update["_meta"]["is_mcp_tool_call"] = False
    if has_command:
        update["rawInput"] = {"command": f"cat {env.data_home / 'security_policy.json'}"}

    event = await _permission_event(
        _client(env, ACP_BACKEND_CODEX), [frames[0], refinement, frames[-1]]
    )

    assert event.is_shell is True
    assert event.mcp_server_name == ""
    assert event.tool_name == ""
    if has_command:
        assert event.shell_command == update["rawInput"]["command"]
    else:
        assert event.shell_command is None
    assert _gate(event).action == TOOL_DENY


@pytest.mark.asyncio
async def test_a_codex_mcp_marker_has_no_effect_on_kiros_existing_execute_path(env):
    event = await _permission_event(_client(env, ACP_BACKEND_KIRO), _codex_mcp_call({}))

    assert event.is_shell is True
    assert event.mcp_server_name == ""
    assert event.tool_name == ""
    assert "arguments" in event.raw_tool_params
    assert _gate(event).action == TOOL_DENY


class _TailObservedList(list):
    """Fail deterministically if a bounded reader iterates through the tail."""

    def __init__(self, values):
        super().__init__(values)
        self.iterations: list[int] = []
        self.slices: list[slice] = []

    def __iter__(self):
        iteration = len(self.iterations)
        self.iterations.append(0)
        for value in super().__iter__():
            self.iterations[iteration] += 1
            assert self.iterations[iteration] <= MAX_TARGET_PATHS + 2, "unbounded tail iteration"
            yield value

    def __getitem__(self, key):
        if isinstance(key, slice):
            self.slices.append(key)
        return super().__getitem__(key)


@pytest.mark.parametrize("source", ["locations", "content"])
def test_frame_path_collection_stops_once_it_has_the_denial_sentinel(env, source):
    paths = [str(env.ws / f"f{i}.txt") for i in range(MAX_TARGET_PATHS + 50)]
    values = _TailObservedList(
        {"path": path, **({"type": "diff"} if source == "content" else {})} for path in paths
    )

    found = _frame_target_paths({source: values}, None)

    assert found == [PATH_LIMIT_SENTINEL]
    assert values.iterations == []


def test_permission_path_merge_copies_only_the_bounded_prefix_and_still_denies(env):
    paths = _TailObservedList(str(env.ws / f"f{i}.txt") for i in range(MAX_TARGET_PATHS + 50))
    event = AcpEvent(
        kind=EVENT_PERMISSION_REQUEST,
        title="Write files",
        tool_kind="edit",
        tool_input="already rendered",
        raw_tool_params={"paths": paths},
    )
    msg = JsonRpcMessage.from_dict(
        {
            "method": METHOD_REQUEST_PERMISSION,
            "id": 9,
            "params": {"toolCall": {"locations": [{"path": str(env.ws / "another.txt")}]}},
        }
    )

    _client(env)._recover_permission_arguments(event, msg)

    assert paths.slices == [slice(None, MAX_TARGET_PATHS + 1)]
    assert paths.iterations == []
    assert len(paths) == MAX_TARGET_PATHS + 50
    assert _gate(event).action == TOOL_DENY


def test_a_bounded_permission_merge_keeps_a_distinct_forbidden_path_after_many_duplicates(env):
    ordinary = str(env.ws / "ordinary.txt")
    policy = str(env.data_home / "security_policy.json")
    paths = _TailObservedList([ordinary] * (MAX_TARGET_PATHS + 50) + [policy])
    event = AcpEvent(
        kind=EVENT_PERMISSION_REQUEST,
        title="Write files",
        tool_kind="edit",
        tool_input="already rendered",
        raw_tool_params={"paths": paths},
    )
    msg = JsonRpcMessage.from_dict(
        {
            "method": METHOD_REQUEST_PERMISSION,
            "id": 9,
            "params": {"toolCall": {"locations": [{"path": str(env.ws / "another.txt")}]}},
        }
    )

    _client(env)._recover_permission_arguments(event, msg)

    # The count alone denies before the unseen forbidden tail; the sentinel must
    # survive the merge rather than becoming an allowing truncated prefix.
    assert PATH_LIMIT_SENTINEL in target_paths(event.raw_tool_params)
    assert paths.iterations == []
    assert _gate(event).action == TOOL_DENY


@pytest.mark.parametrize("value", ["ordinary.txt", None])
def test_raw_path_entry_bounds_deny_repetitions_and_non_paths_before_iteration(env, value):
    from warding.platform.governance import _tool_arg_paths

    paths = _TailObservedList([value] * (MAX_TARGET_PATHS + 50))

    assert target_paths({"paths": paths}) == [PATH_LIMIT_SENTINEL]
    assert _tool_arg_paths({"paths": paths}) == (PATH_LIMIT_SENTINEL,)
    assert paths.iterations == []
    event = AcpEvent(
        kind=EVENT_PERMISSION_REQUEST,
        title="Write files",
        tool_kind="edit",
        raw_tool_params={"paths": paths},
    )
    assert _gate(event).action == TOOL_DENY
    assert paths.iterations == []


@pytest.mark.parametrize("source", ["locations", "content"])
@pytest.mark.parametrize("has_path", [False, True])
def test_frame_entry_bounds_deny_repetitions_and_non_paths_before_iteration(env, source, has_path):
    value = {"path": str(env.ws / "ordinary.txt")} if has_path else {}
    if source == "content":
        value["type"] = "diff"
    values = _TailObservedList([value] * (MAX_TARGET_PATHS + 50))

    found = _frame_target_paths({source: values}, None)

    assert found == [PATH_LIMIT_SENTINEL]
    assert values.iterations == []
    event = AcpEvent(
        kind=EVENT_PERMISSION_REQUEST,
        title="Write files",
        tool_kind="edit",
        raw_tool_params={"paths": found},
    )
    assert _gate(event).action == TOOL_DENY


@pytest.mark.parametrize("source", ["locations", "content"])
def test_frame_collection_also_stops_when_trimmed_spellings_exceed_the_distinct_bound(env, source):
    values = _TailObservedList(
        {
            "path": "\ufeff" + str(env.ws / f"f{i}.txt"),
            **({"type": "diff"} if source == "content" else {}),
        }
        for i in range(MAX_TARGET_PATHS)
    )

    found = _frame_target_paths({source: values}, None)

    assert exceeds_path_limits(found)
    assert values.iterations[0] < len(values)
