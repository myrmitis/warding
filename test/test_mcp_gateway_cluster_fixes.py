"""Regression tests for #926, #927, #928 (mcp-gateway cluster)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from warding.mcp_gateway.rewriter import _WRAPPER_MARKER
from warding.mcp_gateway.session_servers import (
    injection_server_names,
    pooled_session_servers,
)

# ── Enabling gateway at runtime rebuilds the provider factory ─────────


class TestEnableRebuildsFactory:
    """After toggling mcp_gateway.enabled, the provider factory must be
    rebuilt so new sessions resolve the overlay path from current config."""

    @pytest.mark.asyncio
    async def test_enable_calls_refresh_defaults(self) -> None:
        """_apply_mcp_gateway_enabled must call refresh_defaults() on the
        session manager so the captured overlay path is re-resolved."""
        from warding.slack.gateway import GatewayOrchestrator

        orch = GatewayOrchestrator.__new__(GatewayOrchestrator)
        orch._mcp_gateway_manager = None
        orch.dashboard_state = SimpleNamespace()
        orch.sessions = MagicMock()
        orch.sessions.refresh_defaults = AsyncMock()

        with patch.object(type(orch), "_init_mcp_gateway", new_callable=AsyncMock) as mock_init:
            mock_init.return_value = None
            with patch("warding.slack.gateway.WardingConfig") as mock_cfg:
                mock_cfg.load.return_value = MagicMock(mcp_gateway=MagicMock(enabled=True))
                orch._cfg = mock_cfg.load.return_value
                result = await orch._apply_mcp_gateway_enabled(True)  # noqa: F841

        orch.sessions.refresh_defaults.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disable_also_calls_refresh_defaults(self) -> None:
        """Disabling must also rebuild the factory so new sessions stop
        injecting stubs pointing at a dead socket."""
        from warding.slack.gateway import GatewayOrchestrator

        orch = GatewayOrchestrator.__new__(GatewayOrchestrator)
        orch._mcp_gateway_manager = MagicMock(is_running=False)
        orch._mcp_gateway_manager.ping = AsyncMock(return_value=False)
        orch.dashboard_state = SimpleNamespace()
        orch.sessions = MagicMock()
        orch.sessions.refresh_defaults = AsyncMock()

        with patch.object(type(orch), "_stop_mcp_broker", new_callable=AsyncMock):
            with patch("warding.slack.gateway.WardingConfig") as mock_cfg:
                mock_cfg.load.return_value = MagicMock(mcp_gateway=MagicMock(enabled=False))
                orch._cfg = mock_cfg.load.return_value
                await orch._apply_mcp_gateway_enabled(False)

        orch.sessions.refresh_defaults.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_crash_when_sessions_is_none(self) -> None:
        """Early boot: sessions may not be initialised yet."""
        from warding.slack.gateway import GatewayOrchestrator

        orch = GatewayOrchestrator.__new__(GatewayOrchestrator)
        orch._mcp_gateway_manager = None
        orch.dashboard_state = None
        orch.sessions = None

        with patch.object(type(orch), "_init_mcp_gateway", new_callable=AsyncMock):
            with patch("warding.slack.gateway.WardingConfig") as mock_cfg:
                mock_cfg.load.return_value = MagicMock(mcp_gateway=MagicMock(enabled=True))
                orch._cfg = mock_cfg.load.return_value
                # Must not raise
                await orch._apply_mcp_gateway_enabled(True)


# ── Injection precedence is robustly tested ───────────────────────────


class TestInjectionPrecedenceRobust:
    """Non-skippable structural tests that verify the injection contract
    without requiring kiro-cli on PATH."""

    def test_injection_server_names_matches_pooled_output(self, tmp_path: Path) -> None:
        """injection_server_names returns the exact set that
        pooled_session_servers would inject, ensuring the duplicate-detection
        guard covers the full injection set."""
        overlay = tmp_path / "agents"
        overlay.mkdir()
        servers = {
            "pooled-a": {_WRAPPER_MARKER: True, "command": "/usr/bin/a", "args": [], "env": {}},
            "pooled-b": {_WRAPPER_MARKER: True, "command": "/usr/bin/b", "args": [], "env": {}},
            "unpooled": {"command": "npx", "args": ["-y", "foo"], "env": {}},
        }
        (overlay / "agent.json").write_text(
            json.dumps({"name": "agent", "mcpServers": servers}), encoding="utf-8"
        )
        names = injection_server_names(overlay, "agent")
        injected = pooled_session_servers(overlay, "agent")
        assert names == {"pooled-a", "pooled-b"}
        assert {e["name"] for e in injected} == names

    def test_injection_names_empty_when_disabled(self) -> None:
        assert injection_server_names(None, "agent") == frozenset()

    def test_injected_names_shadow_by_identity(self, tmp_path: Path) -> None:
        """Each injected entry's name MUST equal the server it shadows in
        the agent spec. This is the structural guarantee that makes override
        semantics sufficient: kiro-cli matches by name."""
        overlay = tmp_path / "agents"
        overlay.mkdir()
        servers = {
            "corp-mcp": {_WRAPPER_MARKER: True, "command": "/bin/stub", "args": [], "env": {}},
        }
        (overlay / "agent.json").write_text(
            json.dumps({"name": "agent", "mcpServers": servers}), encoding="utf-8"
        )
        (entry,) = pooled_session_servers(overlay, "agent")
        # The name in the injection output is what kiro-cli uses to decide
        # whether to suppress the spec's own copy. If this ever diverges,
        # pooling silently doubles every server.
        assert entry["name"] == "corp-mcp"


# ── Naming ────────────────────────────────────────────────────────────


class TestNaming:
    """The gateway's marker and env identifiers are WARDING_*-prefixed."""

    def test_marker_value_is_warding_prefixed(self) -> None:
        assert "warding" in _WRAPPER_MARKER.lower()

    def test_stub_reads_warding_mcp_socket_env(self) -> None:
        from warding.mcp_gateway.stub import _parse_args

        with patch.dict(os.environ, {"WARDING_MCP_SOCKET": "/tmp/new.sock"}, clear=False):
            args = _parse_args([
                "--server", "test", "--agent", "a",
                "--target-command", "/bin/x", "--work-dir", "/tmp",
            ])
        assert args.socket == "/tmp/new.sock"

    def test_rewriter_emits_warding_env_key_prefix(self, tmp_path: Path) -> None:
        """rewrite_agents must populate target_env with WARDING_MCP_TARGET_ keys."""
        from warding.mcp_gateway.rewriter import rewrite_agents

        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "test.json").write_text(json.dumps({
            "name": "test",
            "mcpServers": {
                "pooled": {"command": sys.executable, "args": ["--stdio"]},
            },
        }), encoding="utf-8")
        overlay_dir = tmp_path / "overlay"
        overlay_dir.mkdir()
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        _, target_env = rewrite_agents(
            source_dir=agents_dir,
            overlay_dir=overlay_dir,
            socket_path=Path("/tmp/gw.sock"),
            work_dir=work_dir,
            stub_servers=frozenset({"pooled"}),
        )
        assert any(k.startswith("WARDING_MCP_TARGET_") for k in target_env), (
            f"Expected WARDING_MCP_TARGET_ prefix in target_env keys: {list(target_env.keys())}"
        )

    def test_idempotent_rewrite_keeps_marker(self, tmp_path: Path) -> None:
        """Re-running the rewriter on an already-wrapped entry keeps the marker."""
        from warding.mcp_gateway.rewriter import _rewrite_single_spec

        spec = {
            "name": "agent",
            "mcpServers": {
                "already": {
                    _WRAPPER_MARKER: True,
                    "command": "/bin/stub",
                    "args": [],
                    "env": {},
                },
            },
        }
        new_spec, wrapped = _rewrite_single_spec(
            spec=spec,
            stubs_dir=tmp_path,
            socket_path=Path("/tmp/gw.sock"),
            work_dir=tmp_path,
            sandbox_mode="standard",
            approval_mode="interactive",
            stub_servers=frozenset({"myserver"}),
        )
        entry = new_spec["mcpServers"]["already"]
        assert entry.get(_WRAPPER_MARKER) is True
        assert wrapped == 1
