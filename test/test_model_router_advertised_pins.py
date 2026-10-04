"""Explicit namespaced pins use only the active harness's advertised models.

The client records set_model calls; no provider, network, or real config is used.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from junction.model_router import routing


class _Client:
    def __init__(self, models: list[dict[str, str]]) -> None:
        self.models = models
        self.seen: list[str] = []

    def available_models(self) -> list[dict[str, str]]:
        return self.models

    async def set_model(self, model_id: str) -> None:
        self.seen.append(model_id)


@pytest.fixture(autouse=True)
def no_real_pins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routing, "_load_pins", lambda: {})


def _pin(monkeypatch: pytest.MonkeyPatch, model_id: str) -> None:
    monkeypatch.setattr(routing, "_load_pins", lambda: {"planning": model_id})


@pytest.mark.asyncio
@pytest.mark.parametrize("model_id", ["vendor-a/model-a", "aggregator/vendor-b/model-b"])
@pytest.mark.parametrize("field", ["modelId", "value"])
async def test_explicit_namespaced_pin_reaches_advertising_harness(
    monkeypatch: pytest.MonkeyPatch, model_id: str, field: str
) -> None:
    _pin(monkeypatch, model_id)
    client = _Client([{field: model_id}])
    assert await routing.apply_role_model(client, routing.ROLE_PLANNING) == model_id
    assert client.seen == [model_id]


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", ["list", "handle"])
async def test_namespaced_pin_uses_existing_advertised_lookup_shapes(
    monkeypatch: pytest.MonkeyPatch, shape: str
) -> None:
    model_id = "vendor-a/model-a"
    _pin(monkeypatch, model_id)
    client: Any = _Client([])
    models = [{"modelId": model_id}]
    if shape == "list":
        client.available_models = models
    else:
        client._handle = SimpleNamespace(available_models=lambda: models)
    assert await routing.apply_role_model(client, routing.ROLE_PLANNING) == model_id
    assert client.seen == [model_id]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "models",
    [[], [{"modelId": "vendor-b/model-a"}], [{"label": "vendor-a/model-a"}]],
)
async def test_catalog_pin_without_matching_active_advertisement_stays_unapplied(
    monkeypatch: pytest.MonkeyPatch, models: list[dict[str, str]]
) -> None:
    model_id = "vendor-a/model-a"
    _pin(monkeypatch, model_id)
    client = _Client(models)
    assert await routing.apply_role_model(client, routing.ROLE_PLANNING) == model_id
    assert client.seen == []


@pytest.mark.asyncio
async def test_unknown_advertisement_from_failed_lookup_does_not_activate_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pin(monkeypatch, "vendor-a/model-a")
    client = _Client([])

    def unavailable() -> list[dict[str, str]]:
        raise RuntimeError("probe unavailable")

    monkeypatch.setattr(client, "available_models", unavailable)
    assert await routing.apply_role_model(client, routing.ROLE_PLANNING) == "vendor-a/model-a"
    assert client.seen == []


@pytest.mark.asyncio
@pytest.mark.parametrize("pin", ["", "auto"])
async def test_unpinned_namespaced_candidate_is_not_newly_activated(
    monkeypatch: pytest.MonkeyPatch, pin: str
) -> None:
    _pin(monkeypatch, pin)
    client = _Client([{"modelId": "vendor-a/model-pro"}])
    expected = "auto" if pin == "auto" else "vendor-a/model-pro"
    assert await routing.apply_role_model(client, routing.ROLE_PLANNING) == expected
    assert client.seen == []


@pytest.mark.asyncio
async def test_advertisement_is_scoped_to_each_client(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin(monkeypatch, "vendor-a/model-a")
    first = _Client([{"modelId": "vendor-a/model-a"}])
    second = _Client([{"modelId": "vendor-b/model-a"}])
    await routing.apply_role_model(first, routing.ROLE_PLANNING)
    await routing.apply_role_model(second, routing.ROLE_PLANNING)
    assert first.seen == ["vendor-a/model-a"]
    assert second.seen == []


@pytest.mark.asyncio
async def test_explicit_pin_keeps_spelling_and_uses_shared_entitlement_predicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pin(monkeypatch, "  vendor-a/Model-A  ")
    client = _Client([{"modelId": "vendor-a/Model-A"}])
    import junction.acp.client as acp_client

    calls: list[tuple[str, list[str]]] = []
    original = acp_client.model_is_unusable

    def observed(model_id: str, advertised: list[str]) -> bool:
        calls.append((model_id, advertised))
        return original(model_id, advertised)

    monkeypatch.setattr(acp_client, "model_is_unusable", observed)
    assert await routing.apply_role_model(client, routing.ROLE_PLANNING) == "vendor-a/Model-A"
    assert calls == [("vendor-a/Model-A", ["vendor-a/Model-A"])]
    assert client.seen == ["vendor-a/Model-A"]


@pytest.mark.asyncio
async def test_setter_failure_preserves_best_effort_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pin(monkeypatch, "vendor-a/model-a")
    client = _Client([{"modelId": "vendor-a/model-a"}])

    async def failed(model_id: str) -> None:
        client.seen.append(model_id)
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(client, "set_model", failed)
    assert await routing.apply_role_model(client, routing.ROLE_PLANNING) == "auto"
    assert client.seen == ["vendor-a/model-a"]


@pytest.mark.asyncio
async def test_setter_failure_of_explicit_pin_is_logged_without_error_text(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _pin(monkeypatch, "vendor-a/model-a")
    client = _Client([{"modelId": "vendor-a/model-a"}])

    async def failed(model_id: str) -> None:
        raise RuntimeError("secret-token-in-provider-error")

    monkeypatch.setattr(client, "set_model", failed)
    with caplog.at_level("INFO", logger=routing.logger.name):
        assert await routing.apply_role_model(client, routing.ROLE_PLANNING) == "auto"
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert [r.getMessage() for r in warnings] == [
        "model-router role planning apply skipped (RuntimeError)"
    ]
    assert "secret-token-in-provider-error" not in caplog.text


class _Wrapper:
    """Shape of ``AcpProvider``: advertises models but re-exports no ``set_model``."""

    def __init__(self, inner: _Client, attr: str) -> None:
        self.available_models = inner.available_models
        setattr(self, attr, inner)


@pytest.mark.asyncio
@pytest.mark.parametrize("attr", ["client", "_client"])
async def test_explicit_namespaced_pin_reaches_setter_behind_wrapper(
    monkeypatch: pytest.MonkeyPatch, attr: str
) -> None:
    _pin(monkeypatch, "vendor-a/model-a")
    inner = _Client([{"modelId": "vendor-a/model-a"}])
    wrapper = _Wrapper(inner, attr)
    assert not hasattr(wrapper, "set_model")
    assert await routing.apply_role_model(wrapper, routing.ROLE_PLANNING) == "vendor-a/model-a"
    assert inner.seen == ["vendor-a/model-a"]


@pytest.mark.asyncio
async def test_wrapper_guards_still_apply_before_setter_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = _Client([{"modelId": "vendor-a/model-a"}])
    wrapper = _Wrapper(inner, "client")
    # An unpinned namespaced suggestion is not activated through a wrapper.
    assert await routing.apply_role_model(wrapper, routing.ROLE_PLANNING) == "auto"
    # A pin the active harness does not advertise stays unapplied too.
    _pin(monkeypatch, "vendor-b/model-b")
    assert await routing.apply_role_model(wrapper, routing.ROLE_PLANNING) == "vendor-b/model-b"
    assert inner.seen == []


@pytest.mark.asyncio
async def test_missing_setter_preserves_best_effort_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pin(monkeypatch, "vendor-a/model-a")
    client = SimpleNamespace(available_models=[{"modelId": "vendor-a/model-a"}])
    assert await routing.apply_role_model(client, routing.ROLE_PLANNING) == "auto"


@pytest.mark.asyncio
async def test_native_pin_and_auto_behavior_are_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin(monkeypatch, "native-model")
    client = _Client([])
    assert await routing.apply_role_model(client, routing.ROLE_PLANNING) == "native-model"
    assert client.seen == ["native-model"]
    client.seen.clear()
    assert await routing.apply_role_model(client, routing.ROLE_BACKGROUND) == "auto"
    assert await routing.apply_role_model(client, "unknown-role") == "auto"
    assert client.seen == []
