"""Model catalog probe: loopback only, no live providers, no secrets."""

from __future__ import annotations

import argparse
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from junction.model_router.probe import (
    CODE_INVALID_PORT,
    CODE_OK,
    CODE_UNREACHABLE,
    probe_status,
    resolve_router_port,
)


class _HealthServer:
    def __init__(self, body: bytes) -> None:
        class _ProbeHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                route = self.path.split("?", 1)[0]
                if route in ("/health", "/health/liveliness"):
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, fmt: str, *args: Any) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _ProbeHandler)
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def health_server() -> Iterator[_HealthServer]:
    server = _HealthServer(b'{"ok":true,"api_key":"sk-live-secret","version":"1"}')
    try:
        yield server
    finally:
        server.close()


def test_probe_up_drops_secret_fields(health_server: _HealthServer) -> None:
    status = probe_status(router_port=health_server.port, gateway_port=health_server.port)
    assert status.reachable is True
    assert status.degraded is False
    assert status.to_dict()["status"] == "healthy"
    assert status.router.code == CODE_OK
    assert status.router.health.get("ok") is True
    assert status.router.health.get("version") == "1"
    dumped = json.dumps(status.to_dict())
    assert "sk-live-secret" not in dumped
    assert "api_key" not in dumped


def test_probe_down_is_degraded_not_an_exception() -> None:
    closer = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = int(closer.server_address[1])
    closer.server_close()
    status = probe_status(router_port=port, gateway_port=port)
    assert status.reachable is False
    assert status.degraded is True
    assert status.router.code == CODE_UNREACHABLE
    assert status.to_dict()["status"] == "unreachable"
    assert "127.0.0.1" in status.router.url


def test_invalid_port_is_coded() -> None:
    status = probe_status(router_port=0)
    assert status.reachable is False
    assert status.router.code == CODE_INVALID_PORT


def test_env_port_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_ROUTER_PORT", "4242")
    assert resolve_router_port() == 4242
    monkeypatch.setenv("MODEL_ROUTER_PORT", "not-a-port")
    assert resolve_router_port() == 4202


def test_cli_status_prints_json_without_secrets(
    health_server: _HealthServer, capsys: pytest.CaptureFixture[str]
) -> None:
    from junction.model_router.cli import run_router_command

    args = argparse.Namespace(router_action="status", router_port=health_server.port)
    run_router_command(args)
    out = capsys.readouterr().out
    assert "sk-live-secret" not in out
    assert "injects them" not in out
    assert "never paste provider keys into chat." in out
    assert out.splitlines()[0].startswith("model plane:")
    last = out.strip().splitlines()[-1]
    payload = json.loads(last)
    assert payload["reachable"] is True
    assert payload["router"]["code"] == CODE_OK
    assert "api_key" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_api_status_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    from aiohttp.test_utils import make_mocked_request

    from junction.model_router import api
    from junction.model_router.probe import EndpointStatus, RouterStatus

    fake = RouterStatus(
        reachable=False,
        degraded=True,
        router=EndpointStatus(url="http://127.0.0.1:9/health", ok=False, code=CODE_UNREACHABLE),
        gateway=EndpointStatus(
            url="http://127.0.0.1:9/health/liveliness",
            ok=False,
            code=CODE_UNREACHABLE,
        ),
    )
    monkeypatch.setattr(api, "probe_status", lambda: fake)
    request = make_mocked_request("GET", "/api/model-router/status")
    resp = await api.api_status(request)
    assert resp.status == 200
    body = json.loads(resp.body)
    assert body["degraded"] is True
    assert body["router"]["code"] == CODE_UNREACHABLE


def test_router_is_a_listed_cli_command() -> None:
    from junction import cli_help

    assert "router" in cli_help.SUMMARIES
    assert "planes" in cli_help.SUMMARIES


def test_model_id_pattern_allows_namespaced_slugs_not_paths() -> None:
    import re

    from junction.model_router.catalog import MODEL_ID_MAX_LEN, MODEL_ID_PATTERN

    assert MODEL_ID_MAX_LEN == 64
    assert re.fullmatch(MODEL_ID_PATTERN, "")
    assert re.fullmatch(MODEL_ID_PATTERN, "auto")
    assert re.fullmatch(MODEL_ID_PATTERN, "kimi-oauth/k3")
    assert re.fullmatch(MODEL_ID_PATTERN, "openrouter/tencent/hy4-preview")
    assert re.fullmatch(MODEL_ID_PATTERN, "../../etc/passwd") is None
    assert re.fullmatch(MODEL_ID_PATTERN, "/etc/passwd") is None
    assert re.fullmatch(MODEL_ID_PATTERN, "foo/./bar") is None
    assert re.fullmatch(MODEL_ID_PATTERN, "foo//bar") is None
    assert re.fullmatch(MODEL_ID_PATTERN, "foo/") is None
    assert re.fullmatch(MODEL_ID_PATTERN, "id with space") is None


def test_catalog_includes_codex_router_model_choices() -> None:
    from junction.model_router.catalog import load_catalog

    catalog = load_catalog()
    slugs = {row.slug for row in catalog.models}
    provider_ids = {row.id for row in catalog.providers}
    assert catalog.version == 1
    assert len(catalog.models) >= 198
    assert "kimi-oauth/k3" in slugs
    assert "kimi-oauth/kimi-for-coding-highspeed" in slugs
    assert "deepseek/deepseek-v4-pro" in slugs
    assert "deepseek/deepseek-v4-flash" in slugs
    assert "grok-oauth/grok-4.5" in slugs
    assert "anthropic-api/claude-opus-4.8" in slugs
    assert "github-copilot" in provider_ids
    assert "openrouter" in provider_ids
    dumped = json.dumps(catalog.to_dict())
    assert "sk-" not in dumped
    # ``auth_kind: api_key`` names how the sidecar authenticates, not a secret.
    from junction.model_router.routing import annotated_catalog

    annotated = annotated_catalog()
    by_slug = {row["slug"]: row["cost_class"] for row in annotated["models"]}
    assert by_slug["deepseek/deepseek-v4-flash"] == "economy"
    assert by_slug["kimi-oauth/k3"] == "capable"
    assert by_slug["deepseek/deepseek-v4-pro"] == "capable"


def test_cost_class_and_plan_never_hardcodes_a_default_id() -> None:
    from junction.model_router.routing import (
        COST_CAPABLE,
        COST_ECONOMY,
        COST_STANDARD,
        ROLE_DAG_EDGES,
        ROLE_EXECUTION,
        ROLE_ORCHESTRATION,
        ROLE_PLANNING,
        build_plan,
        classify_cost,
        resolve_wire_id,
    )

    assert classify_cost("deepseek/deepseek-v4-flash") == COST_ECONOMY
    assert classify_cost("kimi-oauth/k3") == COST_CAPABLE
    assert classify_cost("minimax-m3") == COST_STANDARD
    assert classify_cost("glm-5-turbo") == COST_CAPABLE
    assert classify_cost("gpt-5.4") == COST_CAPABLE
    assert classify_cost("llama-3-turbo") == COST_ECONOMY
    assert (ROLE_ORCHESTRATION, ROLE_PLANNING) in ROLE_DAG_EDGES
    assert (ROLE_PLANNING, ROLE_EXECUTION) in ROLE_DAG_EDGES

    empty = build_plan()
    assert all(row.wire_id == "auto" for row in empty.roles)
    assert empty.assignment(ROLE_PLANNING) and empty.assignment(ROLE_PLANNING).suggestion

    advertised = ["deepseek-v4-flash", "kimi-k3", "minimax-m3"]
    plan = build_plan(advertised=advertised)
    assert plan.assignment(ROLE_ORCHESTRATION).wire_id == "deepseek-v4-flash"
    assert plan.assignment(ROLE_PLANNING).wire_id == "kimi-k3"
    assert plan.assignment(ROLE_EXECUTION).wire_id == "minimax-m3"

    pinned = build_plan(pins={"planning": "kimi-oauth/k3"}, advertised=advertised)
    assert pinned.assignment(ROLE_PLANNING).wire_id == "kimi-oauth/k3"
    assert resolve_wire_id("background", advertised=["haiku-4.5", "opus-4.8"]) == "haiku-4.5"
    fallback = build_plan(advertised=["claude-opus-4.8", "claude-sonnet-4"])
    assert fallback.assignment(ROLE_ORCHESTRATION).wire_id == "claude-sonnet-4"
    assert "fallback" in fallback.assignment(ROLE_ORCHESTRATION).reason


def test_cli_catalog_and_plan_print_json_without_secrets(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from junction.model_router.cli import run_router_command

    run_router_command(argparse.Namespace(router_action="catalog", provider="", cost_class=""))
    catalog_out = capsys.readouterr().out
    last = catalog_out.strip().splitlines()[-1]
    payload = json.loads(last)
    assert payload["model_count"] >= 198
    assert "sk-" not in catalog_out
    assert "holds credentials" not in catalog_out
    assert "no credentials in this snapshot" in catalog_out

    run_router_command(argparse.Namespace(router_action="plan", advertised="haiku-4.5,opus"))
    plan_out = capsys.readouterr().out
    assert "injects them" not in plan_out
    assert "never paste provider keys into chat." in plan_out
    plan_payload = json.loads(plan_out.strip().splitlines()[-1])
    assert plan_payload["code"] == "ok"
    roles = {row["role"]: row for row in plan_payload["roles"]}
    assert roles["orchestration"]["wire_id"] == "haiku-4.5"
    assert roles["planning"]["wire_id"] == "opus"


@pytest.mark.asyncio
async def test_api_catalog_and_plan() -> None:
    from aiohttp.test_utils import make_mocked_request

    from junction.model_router import api

    catalog_resp = await api.api_catalog(make_mocked_request("GET", "/api/model-router/catalog"))
    assert catalog_resp.status == 200
    body = json.loads(catalog_resp.body)
    assert body["model_count"] >= 198
    assert "sk-" not in json.dumps(body)

    plan_resp = await api.api_plan(
        make_mocked_request("GET", "/api/model-router/plan?advertised=flash-1,opus-1")
    )
    assert plan_resp.status == 200
    plan_body = json.loads(plan_resp.body)
    roles = {row["role"]: row for row in plan_body["roles"]}
    assert roles["orchestration"]["cost_class"] == "economy"
    assert roles["planning"]["cost_class"] == "capable"
    assert body["models"][0]["cost_class"] in {"economy", "standard", "capable"}


def test_orchestrator_turn_role_picks_dag_stage() -> None:
    from junction.model_router.routing import (
        ROLE_EXECUTION,
        ROLE_ORCHESTRATION,
        ROLE_PLANNING,
        orchestrator_turn_role,
    )

    assert orchestrator_turn_role(in_stage=True, synthetic=False) == ROLE_EXECUTION
    assert orchestrator_turn_role(in_stage=True, synthetic=True) == ROLE_EXECUTION
    assert orchestrator_turn_role(in_stage=False, synthetic=True) == ROLE_ORCHESTRATION
    assert orchestrator_turn_role(in_stage=False, synthetic=False) == ROLE_PLANNING


@pytest.mark.asyncio
async def test_apply_role_model_sets_pin_and_skips_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    from junction.config.loader import AgentConfig, JunctionConfig
    from junction.model_router.routing import ROLE_PLANNING, apply_role_model

    class _Client:
        def __init__(self) -> None:
            self.seen: list[str] = []

        async def set_model(self, model_id: str) -> None:
            self.seen.append(model_id)

    monkeypatch.setattr(
        "junction.config.loader.JunctionConfig.load",
        classmethod(
            lambda cls: JunctionConfig(agent=AgentConfig(role_models={"planning": "kimi-k3"}))
        ),
    )
    client = _Client()
    assert await apply_role_model(client, ROLE_PLANNING) == "kimi-k3"
    assert client.seen == ["kimi-k3"]
    client.seen.clear()
    assert await apply_role_model(client, "background") == "auto"
    assert client.seen == []


@pytest.mark.asyncio
async def test_apply_role_model_skips_namespaced_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    from junction.config.loader import AgentConfig, JunctionConfig
    from junction.model_router.routing import ROLE_PLANNING, apply_role_model

    class _Client:
        def __init__(self) -> None:
            self.seen: list[str] = []

        async def set_model(self, model_id: str) -> None:
            self.seen.append(model_id)

    monkeypatch.setattr(
        "junction.config.loader.JunctionConfig.load",
        classmethod(
            lambda cls: JunctionConfig(agent=AgentConfig(role_models={"planning": "kimi-oauth/k3"}))
        ),
    )
    client = _Client()
    assert await apply_role_model(client, ROLE_PLANNING) == "kimi-oauth/k3"
    assert client.seen == []


@pytest.mark.asyncio
async def test_apply_role_model_calls_available_models_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from junction.config.loader import AgentConfig, JunctionConfig
    from junction.model_router.routing import ROLE_ORCHESTRATION, apply_role_model

    class _Client:
        def __init__(self) -> None:
            self.seen: list[str] = []

        def available_models(self) -> list[dict[str, str]]:
            return [
                {"modelId": "claude-haiku-4.5"},
                {"modelId": "claude-opus-4.8"},
            ]

        async def set_model(self, model_id: str) -> None:
            self.seen.append(model_id)

    monkeypatch.setattr(
        "junction.config.loader.JunctionConfig.load",
        classmethod(lambda cls: JunctionConfig(agent=AgentConfig(role_models={}))),
    )
    client = _Client()
    assert await apply_role_model(client, ROLE_ORCHESTRATION) == "claude-haiku-4.5"
    assert client.seen == ["claude-haiku-4.5"]


def test_embedded_router_serves_catalog_and_refuses_forwarding() -> None:
    import urllib.error
    import urllib.request

    from junction.model_router.embedded import (
        CODE_NO_FORWARD,
        ensure_embedded_router,
        stop_embedded_router,
    )

    bind = ensure_embedded_router(port=0)
    try:
        assert bind.owned is True
        assert bind.host == "127.0.0.1"
        assert bind.port > 0
        status = probe_status(router_port=bind.port, gateway_port=9)
        assert status.router.ok is True
        assert status.router.health.get("service") == "junction"
        assert status.to_dict()["status"] == "degraded"
        again = ensure_embedded_router(port=0)
        assert again.port == bind.port
        from junction.loopback_http import loopback_urlopen

        req = urllib.request.Request(
            f"http://127.0.0.1:{bind.port}/v1/chat/completions",
            data=b"{}",
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as raised:
            loopback_urlopen(req, timeout=2)
        assert raised.value.code == 501
        body = json.loads(raised.value.read())
        assert body["code"] == CODE_NO_FORWARD
        with loopback_urlopen(f"http://127.0.0.1:{bind.port}/catalog", timeout=2) as resp:
            catalog = json.loads(resp.read())
        assert catalog["model_count"] >= 1
        dumped = json.dumps(catalog)
        assert "sk-" not in dumped
        assert "BEGIN PRIVATE" not in dumped
    finally:
        stop_embedded_router()


def test_embedded_router_leaves_a_busy_port_alone() -> None:
    from junction.model_router.embedded import ensure_embedded_router, stop_embedded_router

    holder = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = int(holder.server_address[1])
    thread = threading.Thread(target=holder.serve_forever, daemon=True)
    thread.start()
    try:
        bind = ensure_embedded_router(port=port)
        assert bind.owned is False
        assert bind.port == port
    finally:
        holder.shutdown()
        holder.server_close()
        stop_embedded_router()


def test_builtin_catalog_line_when_health_names_junction() -> None:
    from junction.planes import format_human_planes

    text = format_human_planes(
        {
            "harness": {"default": "auto", "selected": "", "runtimes": []},
            "model": {
                "status": "degraded",
                "router": {"health": {"service": "junction", "ok": True}},
            },
            "roles": {"roles": []},
        },
        heading="Planes",
    )
    assert "built-in catalog" in text
    assert "provider translation is not bundled" in text
