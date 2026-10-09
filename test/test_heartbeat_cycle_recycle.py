"""Tests for the heartbeat cycle-end recycle path.

Per code review:
- A per-task ``reset(HEARTBEAT_KEY)`` in ``_heartbeat_task.finally`` deterministically
  tears down the session under concurrent ``asyncio.gather``'d sibling tasks
  sharing the same key — the next sibling streams against a torn-down provider.
- Per-cycle reset (always-recycle) cold-starts the entire MCP toolbelt every
  minute even on healthy idle sessions. This cost is now accepted deliberately:
  it is unobserved (nothing waits on a tick) and strictly cheaper than re-sending
  an accumulated transcript as input tokens every tick.

Resolution: per-task ``finally`` only releases the per-key semaphore; cycle-end
recycle is handled once by ``SessionManager.recycle_heartbeat`` (called from
``HeartbeatService._process_heartbeat_file`` after ``asyncio.gather`` completes).
Multi-task cycles share one warm session; between cycles the session is always
torn down, so each cycle starts fresh — matching the "fresh context each cycle"
contract in ``config/prompt.md``.  Nobody waits on a heartbeat tick, so the
per-cycle cold-start is unobserved, whereas a retained transcript would be
re-sent as input tokens on every tick.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from warding.heartbeat import HeartbeatService, heartbeat_path
from warding.session import HEARTBEAT_KEY


def _make_cfg():
    """Minimal WardingConfig stub for SessionManager unit tests."""
    cfg = MagicMock()
    cfg.session.pool_size = 0
    cfg.session.pool_agent = ""
    cfg.session.pool_ttl_secs = 0
    cfg.session.pool_cwd = ""
    cfg.agent.default_agent = ""
    return cfg


@pytest.fixture()
def heartbeat_file(tmp_path, monkeypatch):
    """Redirect heartbeat_path() to a tmp file."""
    monkeypatch.setattr("warding.heartbeat.workspace_dir", lambda: tmp_path)
    return heartbeat_path()


class TestOnCycleEndCallback:
    @pytest.mark.asyncio
    async def test_callback_invoked_after_gather_completes(self, heartbeat_file):
        """on_cycle_end fires exactly once per cycle, AFTER all tasks finish."""
        order: list[str] = []

        async def _on_task(text, deliver):
            order.append(f"task:{text}")
            return None

        async def _on_cycle_end():
            order.append("cycle_end")

        heartbeat_file.write_text(
            "# Heartbeat Tasks\n\n"
            "- [ ] task A\n"
            "- [ ] task B\n"
            "- [ ] task C\n",
            encoding="utf-8",
        )

        svc = HeartbeatService(
            memory=MagicMock(),
            on_task=_on_task,
            on_cycle_end=_on_cycle_end,
        )
        await svc._process_heartbeat_file()

        # All tasks ran exactly once, then on_cycle_end fired once at the end.
        task_runs = [s for s in order if s.startswith("task:")]
        assert len(task_runs) == 3
        assert order[-1] == "cycle_end", "on_cycle_end must fire LAST"
        assert order.count("cycle_end") == 1, "on_cycle_end must fire exactly once"

    @pytest.mark.asyncio
    async def test_callback_invoked_even_when_tasks_raise(self, heartbeat_file):
        """on_cycle_end runs even if individual tasks fail."""
        cycle_end_called = []

        async def _on_task(text, deliver):
            raise RuntimeError("task boom")

        async def _on_cycle_end():
            cycle_end_called.append(True)

        heartbeat_file.write_text(
            "# Heartbeat Tasks\n\n- [ ] some task\n",
            encoding="utf-8",
        )

        svc = HeartbeatService(
            memory=MagicMock(),
            on_task=_on_task,
            on_cycle_end=_on_cycle_end,
        )
        await svc._process_heartbeat_file()

        assert cycle_end_called == [True]

    @pytest.mark.asyncio
    async def test_callback_failure_does_not_crash_loop(self, heartbeat_file):
        """A raising on_cycle_end must NOT propagate — the cycle is over,
        and the periodic loop must keep ticking."""
        async def _on_task(text, deliver):
            return None

        async def _on_cycle_end():
            raise RuntimeError("recycle failed")

        heartbeat_file.write_text(
            "# Heartbeat Tasks\n\n- [ ] some task\n",
            encoding="utf-8",
        )

        svc = HeartbeatService(
            memory=MagicMock(),
            on_task=_on_task,
            on_cycle_end=_on_cycle_end,
        )
        # Should NOT raise — the warning is logged and the loop continues.
        await svc._process_heartbeat_file()

    @pytest.mark.asyncio
    async def test_no_callback_when_no_tasks(self, heartbeat_file):
        """Cycles with zero tasks skip on_cycle_end entirely (no churn)."""
        cycle_end_called = []

        async def _on_task(text, deliver):
            return None

        async def _on_cycle_end():
            cycle_end_called.append(True)

        # File exists but has only the header — zero tasks.
        heartbeat_file.write_text(
            "# Heartbeat Tasks\n\n",
            encoding="utf-8",
        )

        svc = HeartbeatService(
            memory=MagicMock(),
            on_task=_on_task,
            on_cycle_end=_on_cycle_end,
        )
        await svc._process_heartbeat_file()

        assert cycle_end_called == [], "on_cycle_end must not fire when no tasks ran"


class TestRecycleHeartbeat:
    """``SessionManager.recycle_heartbeat`` tears the session down at the end
    of EVERY cycle, regardless of context% or prompt count — heartbeat
    promises "fresh context each cycle" and nobody waits on a tick, so the
    per-cycle cold-start is unobserved while a retained transcript costs input
    tokens on every tick."""

    @pytest.mark.asyncio
    async def test_no_op_when_session_absent(self):
        """Cycles where no heartbeat task ever ran (no session created)
        must be cheap — no work, no errors."""
        from warding.session import SessionManager

        mgr = SessionManager(cfg=_make_cfg(), provider_factory=MagicMock())
        # Should not raise even with no provider, no session, no factory call.
        await mgr.recycle_heartbeat()

    @pytest.mark.asyncio
    async def test_recycles_healthy_session(self):
        """A nearly-empty session is STILL recycled. This is the behavioural
        change: previously a session under 70% context and under 40 prompts
        was preserved, which is what let the heartbeat transcript accumulate
        across cycles while the docs promised fresh context."""
        from warding.session import FirstTurnState, SessionManager, _Session

        mgr = SessionManager(cfg=_make_cfg(), provider_factory=MagicMock())
        provider = MagicMock()
        provider.context_usage_pct = MagicMock(return_value=15.0)
        provider.shutdown = AsyncMock()
        sess = _Session(provider=provider, first_turn=FirstTurnState.NOTHING_ARMED)
        sess.prompt_count = 5
        mgr._sessions[HEARTBEAT_KEY] = sess

        await mgr.recycle_heartbeat()

        assert HEARTBEAT_KEY not in mgr._sessions
        provider.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_recycles_at_pct_threshold(self):
        """A full session is recycled too — the next ``get_or_create``
        creates a fresh one on demand."""
        from warding.session import FirstTurnState, SessionManager, _Session

        mgr = SessionManager(cfg=_make_cfg(), provider_factory=MagicMock())
        provider = MagicMock()
        provider.context_usage_pct = MagicMock(return_value=72.0)
        provider.shutdown = AsyncMock()
        sess = _Session(provider=provider, first_turn=FirstTurnState.NOTHING_ARMED)
        sess.prompt_count = 10
        mgr._sessions[HEARTBEAT_KEY] = sess

        await mgr.recycle_heartbeat()

        # Old session torn down and removed; no eager replacement (unlike
        # background, which calls _ensure_background — heartbeat is
        # on-demand only).
        assert HEARTBEAT_KEY not in mgr._sessions
        provider.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_recycles_when_context_pct_unavailable(self):
        """A provider that can't report context% is recycled all the same —
        there is no threshold left to fall back on."""
        from warding.session import FirstTurnState, SessionManager, _Session

        mgr = SessionManager(cfg=_make_cfg(), provider_factory=MagicMock())
        provider = MagicMock()
        provider.context_usage_pct = MagicMock(return_value=0.0)
        provider.shutdown = AsyncMock()
        sess = _Session(provider=provider, first_turn=FirstTurnState.NOTHING_ARMED)
        sess.prompt_count = 1
        mgr._sessions[HEARTBEAT_KEY] = sess

        await mgr.recycle_heartbeat()

        assert HEARTBEAT_KEY not in mgr._sessions
        provider.shutdown.assert_awaited_once()


class TestHeartbeatAgentInstall:
    """``_install_heartbeat_agent`` writes the warding-heartbeat agent
    config with a minimal MCP surface (per code review)."""

    def test_installs_with_minimal_mcp_servers(self, tmp_path, monkeypatch):
        """Heartbeat agent gets warding-core only on public installs — NOT
        warding-cron / governance / etc.  This is the
        narrow-toolbelt fix for cold-start cost. (Any extra internal
        wiring is omitted on public installs, matching
        ``_install_research_agent`` / ``_install_knowledge_agent``.)"""
        import json

        from warding import agent as agent_mod

        kiro_dir = tmp_path / "agents"
        kiro_dir.mkdir()
        # Seed a main warding.json with multiple mcp servers — the heartbeat
        # installer should pick out only the one it needs (warding-core).
        main_config = {
            "name": "warding",
            "mcpServers": {
                "corp-mcp": {"command": "/bin/corp-mcp", "args": ["x"]},
                "warding-core": {"command": "/bin/mc", "args": ["mcp-core"]},
                "warding-cron": {"command": "/bin/mc", "args": ["mcp-cron"]},
                "playwright-mcp": {"command": "/bin/playwright-mcp", "args": []},
            },
        }
        (kiro_dir / "warding.json").write_text(json.dumps(main_config))

        monkeypatch.setattr(agent_mod, "KIRO_AGENTS_DIR", kiro_dir)

        agent_mod._install_heartbeat_agent()

        path = kiro_dir / "warding-heartbeat.json"
        assert path.exists()
        config = json.loads(path.read_text(encoding="utf-8"))

        assert config["name"] == "warding-heartbeat"
        # Minimal MCP surface — only warding-core (other servers, such as
        # corp-mcp, are omitted).
        assert set(config["mcpServers"].keys()) == {"warding-core"}
        # Tools tags reflect that server (so kiro-cli loads it).
        assert "@warding-core" in config["tools"]
        assert "@corp-mcp" not in config["tools"]
        # Description references the SEL audit gateway-side responsibility.
        assert "HEARTBEAT_SAFE_TOOLS" in config["description"]

    def test_strips_include_tools_filters_from_main_config(self, tmp_path, monkeypatch):
        """The main warding config may narrow a server via ``--include-tools``
        / ``--include-tool-tags`` / ``--exclude-tools``; those filters are
        fragile (a typo silently surfaces zero tools to the agent) and the
        heartbeat allowlist is enforced gateway-side anyway. Strip them so
        the heartbeat agent always sees the full catalog and
        ``HEARTBEAT_SAFE_TOOLS`` is the sole gate. (Asserted on warding-core —
        the only server the public installer pulls.)
        """
        import json

        from warding import agent as agent_mod

        kiro_dir = tmp_path / "agents"
        kiro_dir.mkdir()
        main_config = {
            "name": "warding",
            "mcpServers": {
                "warding-core": {
                    "command": "/bin/mc",
                    "args": [
                        "mcp-core",
                        "--include-tools=recall,learn_list",
                        "--include-tool-tags",
                        "read,default",
                        "--exclude-tools",
                        "send_message",
                        "--skill-paths",
                        "/skills/path",
                    ],
                },
            },
        }
        (kiro_dir / "warding.json").write_text(json.dumps(main_config))
        monkeypatch.setattr(agent_mod, "KIRO_AGENTS_DIR", kiro_dir)

        agent_mod._install_heartbeat_agent()

        config = json.loads((kiro_dir / "warding-heartbeat.json").read_text(encoding="utf-8"))
        core_args = config["mcpServers"]["warding-core"]["args"]
        # Filter flags + their values must be stripped (both --flag=value and
        # --flag <value> shapes).
        joined = " ".join(core_args)
        assert "--include-tools" not in joined
        assert "--include-tool-tags" not in joined
        assert "--exclude-tools" not in joined
        assert "recall,learn_list" not in joined  # value of --include-tools=
        assert "read,default" not in joined  # value of --include-tool-tags
        assert "send_message" not in joined  # value of --exclude-tools
        # Skill paths + positional args must be preserved (unrelated args).
        assert "--skill-paths" in core_args
        assert "/skills/path" in core_args
        assert "mcp-core" in core_args

    def test_install_resilient_when_main_config_missing(self, tmp_path, monkeypatch):
        """First-run scenario: warding.json may not exist yet when the
        heartbeat installer is called.  Should still write a valid (empty
        mcpServers) heartbeat config — install ordering is not load-bearing."""
        import json

        from warding import agent as agent_mod

        kiro_dir = tmp_path / "agents"
        kiro_dir.mkdir()
        monkeypatch.setattr(agent_mod, "KIRO_AGENTS_DIR", kiro_dir)

        agent_mod._install_heartbeat_agent()

        path = kiro_dir / "warding-heartbeat.json"
        assert path.exists()
        config = json.loads(path.read_text(encoding="utf-8"))
        assert config["name"] == "warding-heartbeat"
        # No main config → empty mcpServers (subsequent rebuild_agent_config
        # call will re-seed when warding.json appears).
        assert config["mcpServers"] == {}
        # tools must be derived from mcpServers — never reference a
        # namespace without a matching mcpServers entry, otherwise kiro-cli
        # fails to load the agent. (review-bot finding on rev 6.)
        assert config["tools"] == []

    def test_tools_derived_from_resolved_mcp_servers(self, tmp_path, monkeypatch):
        """``tools`` must be built from the mcpServers actually resolved.

        The installer only pulls ``warding-core``; ``corp-mcp`` is never
        carried over.  So a main config that has
        corp-mcp but NOT warding-core resolves to an empty toolbelt — and
        the tools list must NEVER reference a namespace without a matching
        mcpServers entry, otherwise kiro-cli fails to load the agent.
        (review-bot finding on rev 6.)
        """
        import json

        from warding import agent as agent_mod

        kiro_dir = tmp_path / "agents"
        kiro_dir.mkdir()
        # Main config has corp-mcp but NOT warding-core.
        main_config = {
            "name": "warding",
            "mcpServers": {
                "corp-mcp": {"command": "/bin/corp-mcp", "args": []},
            },
        }
        (kiro_dir / "warding.json").write_text(json.dumps(main_config))
        monkeypatch.setattr(agent_mod, "KIRO_AGENTS_DIR", kiro_dir)

        agent_mod._install_heartbeat_agent()

        config = json.loads((kiro_dir / "warding-heartbeat.json").read_text(encoding="utf-8"))
        # corp-mcp is omitted; warding-core absent here.
        assert config["mcpServers"] == {}
        # tools list mirrors mcpServers — never references @corp-mcp.
        assert config["tools"] == []
