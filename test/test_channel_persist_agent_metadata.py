"""Every channel transport's ``_persist_turn`` must record the resolved agent.

``ConversationLog.append`` records the agent in the session file's metadata
header only when the file-creating write supplies it — omit it and the
dashboard lists the session as the "default" agent forever, and Discord's
``_persisted_agent`` resume path reads back "" (falling back to the channel
agent even when the session was created under an override).

Pre-fix, every channel transport omitted ``agent=`` on its persist writes.
The Slack path has its own end-to-end lock in
``test_slack_transport_dispatch.py``; this file locks the shared
``_persist_turn`` shape used by the other six channels, calling the unbound
method with a minimal stand-in so no channel client needs to be constructed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from junction.history import ConversationLog

_CHANNELS = [
    ("telegram", "junction.telegram.transport_dispatch"),
    ("teams", "junction.teams.transport_dispatch"),
    ("webex", "junction.webex.transport_dispatch"),
    ("wecom", "junction.wecom.transport_dispatch"),
    ("weixin", "junction.weixin.transport_dispatch"),
    ("discord", "junction.discord.transport_dispatch"),
]


def _dispatcher_class(module):
    """The class in *module* that defines ``_persist_turn``."""
    for obj in vars(module).values():
        if isinstance(obj, type) and "_persist_turn" in vars(obj):
            return obj
    raise AssertionError(f"no _persist_turn owner in {module.__name__}")


@pytest.mark.parametrize("channel,mod_name", _CHANNELS)
def test_persist_turn_records_agent_in_session_metadata(channel, mod_name, tmp_path):
    module = __import__(mod_name, fromlist=["_"])
    cls = _dispatcher_class(module)
    log = ConversationLog(base_dir=tmp_path)
    host = SimpleNamespace(conv_log=log)

    key = f"{channel}:agent-metadata-test"
    cls._persist_turn(host, key, "hello", "world", True, agent="sales-agent")

    listed = log.list_sessions()
    assert listed, f"{channel}: _persist_turn should persist a session file"
    assert (
        listed[0].get("agent") == "sales-agent"
    ), f"{channel}: session metadata must carry the agent the turn ran under"


@pytest.mark.parametrize("channel,mod_name", _CHANNELS)
def test_persist_turn_without_agent_still_writes(channel, mod_name, tmp_path):
    """The kwarg is optional — legacy/edge call paths keep working."""
    module = __import__(mod_name, fromlist=["_"])
    cls = _dispatcher_class(module)
    log = ConversationLog(base_dir=tmp_path)
    host = SimpleNamespace(conv_log=log)

    cls._persist_turn(host, f"{channel}:no-agent", "hello", "world", False)
    assert log.list_sessions(), f"{channel}: turn must still persist without agent"
