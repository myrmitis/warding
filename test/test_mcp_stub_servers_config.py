"""How ``mcp_gateway.stub_servers`` is read from config.

The stub is a per-server opt-in: a fresh machine gets none, and the list the
operator wrote is the list that is stubbed. ``stub_servers: []`` and a missing
key both mean "stub nothing", and the sharing switch (``enabled``) has no say in
what is stubbed -- the two layers are independent by design.
"""

import json
import unittest.mock
from pathlib import Path

from warding.config.loader import WardingConfig, _resolve_stub_servers


def _load_from_dict(data: object, tmp_path: Path) -> WardingConfig:
    """Write *data* into the test's own tmp_path and load via WardingConfig.load().

    The file stays under ``tmp_path`` rather than the shared system temp dir, so
    concurrent workers cannot see each other's config.
    """
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(data), encoding="utf-8")
    with unittest.mock.patch(
        "warding.config.loader.config_path",
        return_value=cfg,
    ):
        return WardingConfig.load()


class TestResolver:
    """The pure decision, isolated from config loading."""

    def test_the_listed_servers_are_stubbed(self) -> None:
        assert _resolve_stub_servers({"stub_servers": ["alpha-mcp"]}) == ["alpha-mcp"]

    def test_an_explicitly_empty_list_stubs_nothing(self) -> None:
        assert _resolve_stub_servers({"stub_servers": []}) == []

    def test_the_sharing_switch_has_no_say_in_what_is_stubbed(self) -> None:
        assert _resolve_stub_servers({"enabled": False, "stub_servers": ["alpha-mcp"]}) == [
            "alpha-mcp"
        ]
        assert _resolve_stub_servers({"enabled": True, "stub_servers": ["alpha-mcp"]}) == [
            "alpha-mcp"
        ]

    def test_a_fresh_install_stubs_nothing(self) -> None:
        assert _resolve_stub_servers({}) == []

    def test_junk_entries_are_dropped_rather_than_carried(self) -> None:
        assert _resolve_stub_servers(
            {"stub_servers": ["ok-mcp", "", None, 7, {"a": 1}, "also-ok"]}
        ) == ["ok-mcp", "also-ok"]

    def test_a_non_list_value_is_not_trusted(self) -> None:
        assert _resolve_stub_servers({"stub_servers": "alpha-mcp"}) == []


class TestThroughTheLoader:
    """The resolver wired into ``WardingConfig.load``, which is what ships."""

    def test_the_configured_list_arrives_as_stub_servers(self, tmp_path) -> None:
        cfg = _load_from_dict(
            {"mcp_gateway": {"enabled": True, "stub_servers": ["alpha-mcp"]}},
            tmp_path,
        )
        assert cfg.mcp_gateway.stub_servers == ["alpha-mcp"]

    def test_a_cleared_list_survives_the_load(self, tmp_path) -> None:
        cfg = _load_from_dict({"mcp_gateway": {"enabled": True, "stub_servers": []}}, tmp_path)
        assert cfg.mcp_gateway.stub_servers == []

    def test_the_shipped_default_is_empty(self, tmp_path) -> None:
        """No mcp_gateway section at all — the state of a fresh install."""
        cfg = _load_from_dict({}, tmp_path)
        assert cfg.mcp_gateway.stub_servers == []
