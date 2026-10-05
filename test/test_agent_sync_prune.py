"""Tests for agent sync prune logic in dashboard/handlers/agents.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from junction.agent_discovery import AgentInfo
from junction.config.loader import JunctionAgentConfig, JunctionConfig


def _make_package_agent(name: str) -> AgentInfo:
    return AgentInfo(
        name=name,
        filename=f"local-AcmeAgents-{name}.json",
        description=f"{name} agent",
        model="auto",
        source="package",
        package="AcmeAgents",
    )


def _make_config(agents: dict[str, JunctionAgentConfig]) -> JunctionConfig:
    """Create a MagicMock standing in for JunctionConfig with the given agents dict."""
    cfg = MagicMock(spec=JunctionConfig)
    cfg.agents = agents
    cfg.default_agent = "junction"
    cfg.save = MagicMock()
    return cfg


async def _run_sync(cfg: JunctionConfig, agents_list: list[AgentInfo]) -> dict:
    """Invoke the production _do_agents_sync with mocked dependencies and return parsed body."""
    from junction.dashboard.handlers.agents import _do_agents_sync

    request = MagicMock()
    request.get.return_value = "dashboard"

    sel_mock = MagicMock()

    with (
        patch("junction.dashboard.handlers.agents.JunctionConfig.load", return_value=cfg),
        patch("junction.dashboard.handlers.agents.list_agents", return_value=agents_list),
        patch("junction.dashboard.handlers.agents._sel", return_value=sel_mock),
    ):
        response = await _do_agents_sync(request)

    assert response.body is not None
    return json.loads(response.body)


class TestAgentSyncPrune:
    """Tests for the prune step in _do_agents_sync (real production code path)."""

    @pytest.mark.asyncio
    async def test_prune_removes_stale_package_agents(self):
        """Agents with source='package' not in scan results get pruned."""
        agents = {
            "review-agent": JunctionAgentConfig(kiro_agent="review-agent", source="package"),
            "cloud-agent": JunctionAgentConfig(kiro_agent="cloud-agent", source="package"),
            "dev-agent": JunctionAgentConfig(kiro_agent="dev-agent", source="package"),
        }
        cfg = _make_config(agents)
        pkg_list = [_make_package_agent("cloud-agent"), _make_package_agent("dev-agent")]

        body = await _run_sync(cfg, pkg_list)

        assert body["pruned"] == ["review-agent"]
        assert "review-agent" not in cfg.agents
        assert "cloud-agent" in cfg.agents
        assert "dev-agent" in cfg.agents
        cfg.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_prune_skips_junction_owned_agents(self):
        """Agents with source='junction' are never pruned."""
        agents = {
            "junction": JunctionAgentConfig(kiro_agent="junction", source="junction"),
            "stale-pkg": JunctionAgentConfig(kiro_agent="stale-pkg", source="package"),
        }
        cfg = _make_config(agents)
        pkg_list = [_make_package_agent("dev-agent")]

        body = await _run_sync(cfg, pkg_list)

        assert "stale-pkg" in body["pruned"]
        assert "junction" not in body["pruned"]
        assert "junction" in cfg.agents

    @pytest.mark.asyncio
    async def test_prune_skips_user_created_agents(self):
        """Agents with source='builtin' (user-created) are never pruned."""
        agents = {
            "my-custom": JunctionAgentConfig(kiro_agent="my-custom", source="builtin"),
            "stale-pkg": JunctionAgentConfig(kiro_agent="stale-pkg", source="package"),
        }
        cfg = _make_config(agents)
        pkg_list = [_make_package_agent("dev-agent")]

        body = await _run_sync(cfg, pkg_list)

        assert "stale-pkg" in body["pruned"]
        assert "my-custom" not in body["pruned"]
        assert "my-custom" in cfg.agents

    @pytest.mark.asyncio
    async def test_no_prune_when_scan_returns_empty(self):
        """Empty scan result (likely transient failure) should not prune anything."""
        agents = {
            "cloud-agent": JunctionAgentConfig(kiro_agent="cloud-agent", source="package"),
            "dev-agent": JunctionAgentConfig(kiro_agent="dev-agent", source="package"),
        }
        cfg = _make_config(agents)
        pkg_list: list[AgentInfo] = []

        body = await _run_sync(cfg, pkg_list)

        assert body["pruned"] == []
        assert body["synced"] == []
        assert "cloud-agent" in cfg.agents
        assert "dev-agent" in cfg.agents
        cfg.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_and_prune_in_same_sync(self):
        """A single sync both adds new agents and prunes stale ones."""
        agents = {
            "old-agent": JunctionAgentConfig(kiro_agent="old-agent", source="package"),
        }
        cfg = _make_config(agents)
        pkg_list = [_make_package_agent("new-agent")]

        body = await _run_sync(cfg, pkg_list)

        assert body["synced"] == ["new-agent"]
        assert body["pruned"] == ["old-agent"]
        assert "new-agent" in cfg.agents
        assert "old-agent" not in cfg.agents
        cfg.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_noop_when_nothing_changed(self):
        """No adds or prunes when config matches scan exactly."""
        agents = {
            "cloud-agent": JunctionAgentConfig(kiro_agent="cloud-agent", source="package"),
        }
        cfg = _make_config(agents)
        pkg_list = [_make_package_agent("cloud-agent")]

        body = await _run_sync(cfg, pkg_list)

        assert body["synced"] == []
        assert body["pruned"] == []
        cfg.save.assert_not_called()


class TestAgentSyncFsCheckIsOffloaded:
    """The per-agent on-disk existence check (a stat + a namespaced glob) runs in
    a loop over discovered agents; on a populated agents directory it must be
    offloaded or the gateway loop and heartbeat stall."""

    def test_the_on_disk_check_is_awaited_off_loop(self) -> None:
        import inspect

        from junction.dashboard.handlers import agents

        src = inspect.getsource(agents._do_agents_sync)
        assert "await asyncio.to_thread(" in src
        assert "_namespaced_agent_file_exists(_dn)" in src, "the FS check must run off-loop"
