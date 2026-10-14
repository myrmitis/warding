"""A connection-only probe must not become a model-aware chat readiness gate."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from warding.harness_router.connect import STATUS_CONNECTED, probe_harness


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("pin", "served", "advertised"),
    [
        ("gpt-6.1-sol", "gpt-6-sol[ultra]", ["gpt-6-sol[ultra]"]),
        ("gpt-6-sol[ultra]", "gpt-6.1-sol", ["gpt-6-sol[ultra]"]),
        ("", "gpt-6.1-sol", ["gpt-6-sol[ultra]"]),
    ],
)
async def test_connection_probe_keeps_model_diagnostics_out_of_shared_chat_readiness(
    pin: str, served: str, advertised: list[str]
) -> None:
    provider = SimpleNamespace(
        start=AsyncMock(),
        shutdown=AsyncMock(),
        stream=AsyncMock(),
        served_model=served,
        _client=SimpleNamespace(available_models=lambda: [{"modelId": m} for m in advertised]),
    )
    made: list[tuple[str, str]] = []

    def maker(h: str, m: str) -> SimpleNamespace:
        made.append((h, m))
        return provider

    result = await probe_harness("codex", installed=True, model=pin, make_provider=maker)
    # Startup/auth evidence is not model-specific readiness evidence: shared
    # records are keyed only by harness and may have come from a routed lane.
    assert result.status == STATUS_CONNECTED
    assert [entry.id for entry in result.advertised] == advertised
    assert made == [("codex", pin)]
    provider.start.assert_awaited_once()
    provider.shutdown.assert_awaited_once()
    provider.stream.assert_not_called()
    assert result.detail == ""
