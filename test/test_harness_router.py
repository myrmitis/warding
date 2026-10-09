"""Harness router: lanes, limit detection, ledger, scoring, and dispatch seams."""

from __future__ import annotations

import contextlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from warding.harness_router import limits
from warding.harness_router.kinds import TASK_KINDS, normalize_kind
from warding.harness_router.lanes import (
    Lane,
    RoutingSettings,
    auto_lanes,
    load_settings,
    parse_settings,
    template_document,
)
from warding.harness_router.ledger import RETENTION_SECS, UsageLedger
from warding.harness_router.router import (
    DECISION_DISABLED,
    DECISION_NO_LANE,
    DECISION_OK,
    EXCLUDED_COOLDOWN,
    EXCLUDED_DAILY_CAP,
    EXCLUDED_NOT_INSTALLED,
    decide,
)
from warding.harness_router.service import HarnessRouter, RoutingError

NOW = 1_800_000_000.0

_ALL_BINS = {
    "claude": "/b/claude",
    "codex": "/b/codex",
    "npx": "/b/npx",
    "cursor-agent": "/b/cursor-agent",
    "grok": "/b/grok",
    "opencode": "/b/opencode",
}


def _which(installed: dict[str, str]):
    return installed.get


def _lane(lane_id: str, harness: str, **kw: Any) -> Lane:
    raw = {"id": lane_id, "harness": harness, **kw}
    lane = parse_settings({"lanes": [raw]}).lanes[0]
    return lane


def _settings(*lanes: Lane, **kw: Any) -> RoutingSettings:
    return RoutingSettings(lanes=tuple(lanes), **kw)


@pytest.fixture(autouse=True)
def _pin_os_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Detect harnesses against a pinned OS home, never the developer's.

    ``load_settings(home=...)`` and ``HarnessRouter(home=...)`` take the Warding
    DATA home, which is a different root from the OS home. Pinning the OS home
    keeps these assertions hermetic on a developer machine.
    """
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))


# ── kinds ──


def test_normalize_kind_falls_back_to_role_then_implement() -> None:
    assert normalize_kind("REVIEW") == "review"
    assert normalize_kind("", role="planning") == "plan"
    assert normalize_kind("nonsense", role="background") == "quick"
    assert normalize_kind(None) == "implement"


# ── limits ──


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Claude AI usage limit reached|1800003600", limits.FAILURE_USAGE_LIMIT),
        ("5-hour limit reached ∙ resets 3pm", limits.FAILURE_USAGE_LIMIT),
        (
            "You've hit your usage limit. Upgrade to Pro or try again in 2 hours 5 minutes.",
            limits.FAILURE_USAGE_LIMIT,
        ),
        ("Insufficient credits. Add more at openrouter.ai", limits.FAILURE_USAGE_LIMIT),
        ("stream error: last status: 429 Too Many Requests", limits.FAILURE_RATE_LIMIT),
        ("Rate limit exceeded, please retry", limits.FAILURE_RATE_LIMIT),
        ("JSON-RPC error: {'code': -32000, 'message': 'Authentication required'}", "auth"),
        ("Invalid API key · Please run /login", limits.FAILURE_AUTH),
        ("ACP runtime 'grok' is not installed. Install Grok CLI", limits.FAILURE_UNAVAILABLE),
        # Task failures that merely mention limits must not rest a lane.
        ("context window limit reached while reading the repo", limits.FAILURE_OTHER),
        ("turn_limit:100", limits.FAILURE_OTHER),
        ("AssertionError at line 429 of test_api.py", limits.FAILURE_OTHER),
        ("", limits.FAILURE_OTHER),
    ],
)
def test_classify_failure(text: str, expected: str) -> None:
    assert limits.classify_failure(text) == expected


def test_classify_exception_by_type() -> None:
    class AcpAuthRequired(Exception):
        pass

    assert limits.classify_exception(AcpAuthRequired("x")) == limits.FAILURE_AUTH
    assert limits.classify_exception(FileNotFoundError("grok")) == limits.FAILURE_UNAVAILABLE
    failure = limits.HarnessLaneFailure(limits.FAILURE_USAGE_LIMIT, "limit")
    assert limits.classify_exception(failure) == limits.FAILURE_USAGE_LIMIT


def test_parse_reset_relative_clock_and_epoch() -> None:
    assert limits.parse_reset_seconds("try again in 2 hours 5 minutes", now=NOW) == 7500
    assert limits.parse_reset_seconds("retry after 30 seconds", now=NOW) == 30
    assert limits.parse_reset_seconds("usage limit reached|1800003600", now=NOW) == 3600
    clock = limits.parse_reset_seconds("limit reached, resets 3pm", now=NOW)
    assert clock is not None and 0 < clock <= 86400
    assert limits.parse_reset_seconds("resets 3", now=NOW) is None
    assert limits.parse_reset_seconds("no hint here", now=NOW) is None


def test_cooldown_bounds_and_ordinary_failures() -> None:
    assert limits.cooldown_seconds(limits.FAILURE_OTHER, "boom") == 0.0
    usage = limits.cooldown_seconds(limits.FAILURE_USAGE_LIMIT, "usage limit", now=NOW)
    assert usage == limits.DEFAULT_COOLDOWN_SECS[limits.FAILURE_USAGE_LIMIT]
    tiny = limits.cooldown_seconds(limits.FAILURE_RATE_LIMIT, "retry after 1 seconds", now=NOW)
    assert tiny == limits.MIN_COOLDOWN_SECS
    huge = limits.cooldown_seconds(limits.FAILURE_USAGE_LIMIT, "try again in 30 days", now=NOW)
    assert huge == limits.MAX_COOLDOWN_SECS


def test_limit_notice_only_for_short_usage_or_auth_replies() -> None:
    assert limits.limit_notice_failure("You've hit your usage limit.") == "usage_limit"
    assert limits.limit_notice_failure("Please run /login first") == "auth"
    # An answer ABOUT rate limiting is not a throttle.
    assert limits.limit_notice_failure("I added a rate limiter to the API.") == ""
    long_answer = "Here is the usage limit design. " + "x" * limits.LIMIT_NOTICE_MAX_CHARS
    assert limits.limit_notice_failure(long_answer) == ""


# ── lanes ──


def test_parse_settings_applies_profile_defaults_and_overrides() -> None:
    settings = parse_settings(
        {
            "max_failover": 1,
            "lanes": [
                {"id": "max", "harness": "claude", "weight": 3, "window_limit": 200},
                {
                    "id": "or-cheap",
                    "harness": "opencode",
                    "model": "openrouter/deepseek/deepseek-v4",
                    "affinity": {"bulk": 1.0},
                    "daily_limit": 50,
                },
            ],
        }
    )
    assert settings.source == "config" and settings.max_failover == 1
    claude, cheap = settings.lanes
    assert claude.billing == "subscription" and claude.weight == 3 and claude.window_limit == 200
    assert claude.affinity_for("plan") == 1.0
    assert cheap.billing == "metered" and cheap.affinity_for("bulk") == 1.0
    assert cheap.model == "openrouter/deepseek/deepseek-v4"


def test_parse_settings_skips_bad_lanes_with_warnings() -> None:
    settings = parse_settings(
        {
            "lanes": [
                {"harness": "nope"},
                {"id": "Bad Id", "harness": "codex"},
                {"id": "a", "harness": "codex", "billing": "weird", "affinity": {"zzz": 1}},
                {"id": "a", "harness": "grok"},
                {"id": "k", "harness": "auto"},
                "not-an-object",
            ]
        }
    )
    assert [lane.id for lane in settings.lanes] == ["a"]
    assert settings.lanes[0].billing == "subscription"
    assert len(settings.warnings) >= 5


def test_kiro_lane_maps_to_empty_backend() -> None:
    lane = _lane("kiro", "kiro")
    assert lane.backend == ""


def test_load_settings_without_file_detects_installed(tmp_path: Path) -> None:
    settings = load_settings(home=tmp_path, which=_which({"grok": "/b/grok"}), env={})
    assert settings.source == "auto"
    assert [lane.harness for lane in settings.lanes] == ["grok"]


def test_load_settings_with_broken_file_degrades_to_detection(tmp_path: Path) -> None:
    (tmp_path / "routing.json").write_text("{not json", encoding="utf-8")
    settings = load_settings(home=tmp_path, which=_which({"grok": "/b/grok"}), env={})
    assert settings.source == "auto"
    assert settings.warnings and "ignored" in settings.warnings[0]


def test_template_round_trips_through_the_parser() -> None:
    doc = template_document(["claude", "codex", "opencode"])
    settings = parse_settings(json.loads(json.dumps(doc)))
    assert [lane.id for lane in settings.lanes] == ["claude", "codex", "opencode"]
    assert not settings.warnings


# ── ledger ──


def test_ledger_records_dispatches_and_limits(tmp_path: Path) -> None:
    ledger = UsageLedger(tmp_path)
    ledger.record_dispatch("codex", "implement", now=NOW)
    ledger.record_dispatch("codex", "implement", now=NOW + 1)
    until = ledger.record_outcome(
        "codex",
        ok=False,
        failure=limits.FAILURE_USAGE_LIMIT,
        text="You've hit your usage limit, try again in 10 minutes. key=AKIAABCDEFGHIJKLMNOP",
        now=NOW + 2,
    )
    usage = ledger.snapshot()["codex"]
    assert usage.count_since(NOW) == 2
    assert usage.kinds == {"implement": 2}
    assert until == pytest.approx(NOW + 2 + 600)
    assert usage.cooling(NOW + 3) and usage.cooldown_reason == "usage_limit"
    assert "AKIAABCDEFGHIJKLMNOP" not in usage.last_error
    ledger.record_outcome("codex", ok=True, now=NOW + 4)
    assert not ledger.snapshot()["codex"].cooling(NOW + 5)


def test_ledger_task_failure_does_not_rest_the_lane(tmp_path: Path) -> None:
    ledger = UsageLedger(tmp_path)
    ledger.record_outcome("codex", ok=False, failure=limits.FAILURE_OTHER, text="boom", now=NOW)
    usage = ledger.snapshot()["codex"]
    assert usage.failed == 1 and usage.limited == 0 and not usage.cooling(NOW)


def test_ledger_prunes_old_dispatches_and_survives_corruption(tmp_path: Path) -> None:
    ledger = UsageLedger(tmp_path)
    ledger.record_dispatch("grok", now=NOW - RETENTION_SECS - 10)
    ledger.record_dispatch("grok", now=NOW)
    assert ledger.snapshot()["grok"].dispatches == [NOW]
    ledger.path.write_text("garbage", encoding="utf-8")
    assert ledger.snapshot() == {}
    ledger.record_dispatch("grok", now=NOW)
    assert ledger.snapshot()["grok"].count_since(0) == 1


def test_clear_cooldown(tmp_path: Path) -> None:
    ledger = UsageLedger(tmp_path)
    ledger.set_cooldown("a", 600, "usage_limit")
    ledger.set_cooldown("b", 600, "auth")
    assert ledger.clear_cooldown("a") == ["a"]
    assert sorted(ledger.clear_cooldown()) == ["b"]


# ── scoring ──


def _full_house() -> RoutingSettings:
    return _settings(*auto_lanes(["cursor", "claude", "codex", "grok", "opencode"]))


_INSTALLED = ("cursor", "claude", "codex", "grok", "opencode")


@pytest.mark.parametrize(
    ("kind", "lane"),
    [
        ("plan", "claude"),
        ("review", "claude"),
        ("implement", "codex"),
        ("debug", "codex"),
        ("research", "grok"),
        ("quick", "cursor"),
    ],
)
def test_fresh_install_routes_by_affinity(kind: str, lane: str) -> None:
    decision = decide(_full_house(), {}, _INSTALLED, kind=kind, now=NOW)
    assert decision.code == DECISION_OK and decision.lane is not None
    assert decision.lane.id == lane


def test_metered_lane_is_overflow_not_first_choice() -> None:
    decision = decide(_full_house(), {}, _INSTALLED, kind="bulk", now=NOW)
    assert decision.lane is not None and decision.lane.billing != "metered"
    only_metered = decide(_full_house(), {}, ("opencode",), kind="bulk", now=NOW)
    assert only_metered.lane is not None and only_metered.lane.id == "opencode"


def test_load_spreads_across_subscriptions(tmp_path: Path) -> None:
    ledger = UsageLedger(tmp_path)
    settings = _settings(*auto_lanes(["claude", "codex"]))
    picks = []
    for step in range(40):
        decision = decide(
            settings, ledger.snapshot(), ("claude", "codex"), kind="implement", now=NOW
        )
        assert decision.lane is not None
        picks.append(decision.lane.id)
        ledger.record_dispatch(decision.lane.id, now=NOW - 1 - step)
    assert picks[0] == "codex"
    # Both plans take a real share; neither is drained while the other idles.
    assert 12 <= picks.count("claude") <= 28


def test_cooldown_and_install_state_exclude_lanes(tmp_path: Path) -> None:
    ledger = UsageLedger(tmp_path)
    ledger.record_outcome("codex", ok=False, failure="usage_limit", text="usage limit", now=NOW)
    decision = decide(
        _full_house(), ledger.snapshot(), ("claude", "codex", "grok"), kind="implement", now=NOW + 5
    )
    assert decision.lane is not None and decision.lane.id == "claude"
    by_id = {c.lane.id: c for c in decision.candidates}
    assert by_id["codex"].excluded == EXCLUDED_COOLDOWN
    assert by_id["cursor"].excluded == EXCLUDED_NOT_INSTALLED
    assert "cursor" not in [lane.id for lane in decision.fallbacks]


def test_window_limit_and_daily_cap(tmp_path: Path) -> None:
    ledger = UsageLedger(tmp_path)
    for i in range(3):
        ledger.record_dispatch("codex", now=NOW - i)
        ledger.record_dispatch("or", now=NOW - i)
    settings = _settings(
        _lane("codex", "codex", window_limit=3),
        _lane("claude", "claude"),
        _lane("or", "opencode", daily_limit=3),
    )
    decision = decide(
        settings, ledger.snapshot(), ("codex", "claude", "opencode"), kind="implement", now=NOW
    )
    assert decision.lane is not None and decision.lane.id == "claude"
    by_id = {c.lane.id: c for c in decision.candidates}
    assert by_id["or"].excluded == EXCLUDED_DAILY_CAP
    assert by_id["codex"].eligible and by_id["codex"].note == "window limit reached"


def test_exclude_prefer_disabled_and_empty() -> None:
    settings = _full_house()
    excluded = decide(settings, {}, _INSTALLED, kind="implement", exclude=["codex"], now=NOW)
    assert excluded.lane is not None and excluded.lane.id != "codex"
    preferred = decide(settings, {}, _INSTALLED, kind="implement", prefer=["claude"], now=NOW)
    assert preferred.lane is not None and preferred.lane.id == "claude"
    off = decide(_settings(*settings.lanes, enabled=False), {}, _INSTALLED, kind="plan", now=NOW)
    assert off.code == DECISION_DISABLED and off.lane is None
    empty = decide(_settings(), {}, (), kind="plan", now=NOW)
    assert empty.code == DECISION_NO_LANE and "install" in empty.reason


def test_every_kind_has_a_pick_on_a_full_house() -> None:
    for kind in TASK_KINDS:
        assert decide(_full_house(), {}, _INSTALLED, kind=kind, now=NOW).code == DECISION_OK


# ── service ──


def _router(tmp_path: Path, installed: dict[str, str] | None = None) -> HarnessRouter:
    return HarnessRouter(home=tmp_path, which=_which(installed or _ALL_BINS), env={})


def test_resolve_route_lane_and_harness(tmp_path: Path) -> None:
    (tmp_path / "routing.json").write_text(
        json.dumps(
            {"lanes": [{"id": "pro", "harness": "codex"}, {"id": "max", "harness": "claude"}]}
        ),
        encoding="utf-8",
    )
    router = _router(tmp_path)
    routed = router.resolve("route", kind="plan")
    assert routed.routed and routed.lane.id == "max" and routed.backend == "claude"
    assert router.resolve("pro").lane.id == "pro"
    by_harness = router.resolve("codex")
    assert by_harness.lane.id == "pro" and not by_harness.routed
    # A harness with no lane still resolves to its profile when installed.
    assert router.resolve("grok").lane.harness == "grok"
    with pytest.raises(RoutingError) as unknown:
        router.resolve("nope")
    assert unknown.value.code == "unknown_target"


def test_resolve_refuses_uninstalled_harness(tmp_path: Path) -> None:
    router = _router(tmp_path, {"grok": "/b/grok"})
    with pytest.raises(RoutingError) as err:
        router.resolve("cursor")
    assert err.value.code == "not_installed"
    assert router.resolve("route", kind="research").lane.id == "grok"


def test_next_lane_skips_tried_and_resting(tmp_path: Path) -> None:
    router = _router(tmp_path)
    first = router.resolve("route", kind="research").lane
    assert first.id == "grok"
    failure = router.record_failure("grok", text="Authentication required")
    assert failure == limits.FAILURE_AUTH
    nxt = router.next_lane("research", [first.id])
    assert nxt is not None and nxt.id not in ("grok",)
    assert router.resolve("route", kind="research").lane.id != "grok"


def test_settings_reload_on_file_change(tmp_path: Path) -> None:
    router = _router(tmp_path)
    assert router.settings().source == "auto"
    path = tmp_path / "routing.json"
    path.write_text(json.dumps({"lanes": [{"id": "only", "harness": "grok"}]}), encoding="utf-8")
    later = time.time() + 5
    import os

    os.utime(path, (later, later))
    assert [lane.id for lane in router.settings().lanes] == ["only"]


def test_status_shape(tmp_path: Path) -> None:
    router = _router(tmp_path)
    router.record_dispatch("claude", "plan")
    status = router.status()
    assert status["code"] == "ok" and status["source"] == "auto"
    assert set(status["preview"]) == set(TASK_KINDS)
    claude = next(row for row in status["lanes"] if row["id"] == "claude")
    assert claude["window_used"] == 1 and claude["installed"] is True


# ── provider factory seam ──


def test_backend_override_resolution() -> None:
    from warding.config.loader import resolve_acp_backend_override

    assert resolve_acp_backend_override("kiro") == ""
    assert resolve_acp_backend_override("opencode") == "opencode"
    with pytest.raises(ValueError):
        resolve_acp_backend_override("not-a-harness")


def test_factory_honours_per_session_backend(tmp_path: Path) -> None:
    from warding.config.loader import WardingConfig

    cfg = WardingConfig()
    cfg.agent.acp_backend = "cursor"
    factory = cfg.create_provider_factory()
    default = factory("k1", cwd=str(tmp_path))
    override = factory("k2", cwd=str(tmp_path), acp_backend_override="codex")
    assert default._client.backend == "cursor"
    assert override._client.backend == "codex"


def _factory_kwargs(cfg: Any, session_key: str, **call: Any) -> dict[str, Any]:
    """AcpProvider construction kwargs for one factory call, provider stubbed."""
    from unittest.mock import MagicMock, patch

    with patch("warding.providers.acp.AcpProvider") as mock_provider:
        mock_provider.return_value = MagicMock()
        factory = cfg.create_provider_factory()
        factory(session_key, **call)
        assert mock_provider.called, "factory did not construct AcpProvider"
        return mock_provider.call_args.kwargs


def test_factory_keeps_kiro_spelled_model_on_the_kiro_harness(tmp_path: Path) -> None:
    from warding.acp.types import ACP_BACKEND_KIRO
    from warding.config.loader import WardingConfig

    cfg = WardingConfig()
    cfg.agent.acp_backend = ACP_BACKEND_KIRO
    cfg.agent.model = "opus-4.8-1m"  # canonical -> kiro's "claude-opus-4.8"
    kwargs = _factory_kwargs(cfg, "k1", cwd=str(tmp_path))
    assert kwargs["acp_backend"] == ACP_BACKEND_KIRO
    assert kwargs["model"] == "claude-opus-4.8"


def test_factory_does_not_leak_the_global_model_to_a_foreign_harness(tmp_path: Path) -> None:
    from warding.acp.types import ACP_BACKEND_KIRO
    from warding.config.loader import WardingConfig

    cfg = WardingConfig()
    cfg.agent.acp_backend = ACP_BACKEND_KIRO
    cfg.agent.model = "opus-4.8-1m"
    kwargs = _factory_kwargs(cfg, "k2", cwd=str(tmp_path), acp_backend_override="codex")
    assert kwargs["acp_backend"] == "codex"
    assert kwargs["model"] == ""


def test_factory_does_not_leak_a_foreign_global_model_to_a_kiro_override(tmp_path: Path) -> None:
    from warding.config.loader import WardingConfig

    cfg = WardingConfig()
    cfg.agent.acp_backend = "codex"
    cfg.agent.model = "codex-native"
    kwargs = _factory_kwargs(cfg, "k3", cwd=str(tmp_path), acp_backend_override="kiro")
    assert kwargs["acp_backend"] == ""
    assert kwargs["model"] == ""


def test_factory_keeps_an_explicit_model_on_its_own_foreign_harness(tmp_path: Path) -> None:
    from warding.config.loader import DEFAULT_MODEL, WardingConfig

    cfg = WardingConfig()
    cfg.agent.acp_backend = "codex"
    cfg.agent.model = "codex-native"
    # The configured harness keeps the operator's own pick (that namespace).
    assert _factory_kwargs(cfg, "k4", cwd=str(tmp_path))["model"] == "codex-native"
    # The auto-derived kiro spec model is not the operator's pick, so it stays home.
    cfg.agent.model = DEFAULT_MODEL
    assert _factory_kwargs(cfg, "k5", cwd=str(tmp_path))["model"] == ""


def test_factory_passes_a_routed_lane_model_through_untouched(tmp_path: Path) -> None:
    from warding.config.loader import WardingConfig

    cfg = WardingConfig()
    kwargs = _factory_kwargs(
        cfg,
        "k6",
        cwd=str(tmp_path),
        model_override="openrouter/deepseek/deepseek-v4",
        acp_backend_override="opencode",
    )
    assert kwargs["model"] == "openrouter/deepseek/deepseek-v4"


def test_factory_pairs_the_model_with_the_auto_selected_harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from warding.acp.runtimes import builtin_specs
    from warding.acp.types import ACP_BACKEND_CURSOR, ACP_BACKEND_KIRO
    from warding.config.loader import WardingConfig

    cfg = WardingConfig()  # acp_backend "auto"
    cfg.agent.model = "opus-4.8-1m"
    # ``auto`` is resolved once per provider creation, so the harness the
    # provider runs and the model it is handed always agree: a foreign harness
    # keeps the operator's pick verbatim, Kiro gets it translated.
    monkeypatch.setattr(
        "warding.acp.runtimes.select_runtime",
        lambda *_a, **_k: builtin_specs()[ACP_BACKEND_CURSOR],
    )
    foreign = _factory_kwargs(cfg, "k7", cwd=str(tmp_path))
    assert (foreign["acp_backend"], foreign["model"]) == (ACP_BACKEND_CURSOR, "opus-4.8-1m")
    monkeypatch.setattr(
        "warding.acp.runtimes.select_runtime",
        lambda *_a, **_k: builtin_specs()[ACP_BACKEND_KIRO],
    )
    kiro = _factory_kwargs(cfg, "k8", cwd=str(tmp_path))
    assert (kiro["acp_backend"], kiro["model"]) == (ACP_BACKEND_KIRO, "claude-opus-4.8")


def test_factory_with_no_harness_installed_sends_no_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from warding.acp.runtimes import RuntimeNotFoundError
    from warding.config.loader import WardingConfig

    def _no_runtime(*_a: object, **_k: object) -> object:
        raise RuntimeNotFoundError("none installed")

    monkeypatch.setattr("warding.acp.runtimes.select_runtime", _no_runtime)
    cfg = WardingConfig()  # acp_backend "auto", nothing installed
    cfg.agent.model = "claude-sonnet-4.6"
    kwargs = _factory_kwargs(cfg, "k9", cwd=str(tmp_path))
    # ``auto`` stays unresolved (no namespace is known), and the configured
    # model is not sent into it.
    assert (kwargs["acp_backend"], kwargs["model"]) == ("auto", "")


def test_factory_resolves_an_explicit_auto_override_like_auto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from warding.acp.runtimes import builtin_specs
    from warding.acp.types import ACP_BACKEND_CURSOR, ACP_BACKEND_KIRO
    from warding.config.loader import WardingConfig

    monkeypatch.setattr(
        "warding.acp.runtimes.select_runtime",
        lambda *_a, **_k: builtin_specs()[ACP_BACKEND_CURSOR],
    )
    cfg = WardingConfig()
    cfg.agent.acp_backend = ACP_BACKEND_KIRO
    cfg.agent.model = "opus-4.8-1m"
    kwargs = _factory_kwargs(cfg, "k10", cwd=str(tmp_path), acp_backend_override="auto")
    # An explicit ``auto`` override picks the installed runtime even when the
    # configured harness is Kiro, and the kiro-spelled global is not carried over.
    assert (kwargs["acp_backend"], kwargs["model"]) == (ACP_BACKEND_CURSOR, "")


def test_pool_decisions_name_the_harness_bypass() -> None:
    from warding.session import POOL_DECISIONS

    assert "bypass_harness" in POOL_DECISIONS


# ── tool surfaces ──


def test_spawn_run_schema_accepts_routing_fields() -> None:
    from warding.validation import SPAWN_RUN_SCHEMA, ValidationError, validate_tool_args

    cleaned = validate_tool_args(
        {"task": "t", "harness": "route", "kind": "review"}, SPAWN_RUN_SCHEMA
    )
    assert cleaned["harness"] == "route" and cleaned["kind"] == "review"
    with pytest.raises(ValidationError):
        validate_tool_args({"task": "t", "kind": "dance"}, SPAWN_RUN_SCHEMA)
    with pytest.raises(ValidationError):
        validate_tool_args({"task": "t", "harness": "../etc"}, SPAWN_RUN_SCHEMA)


def test_spawn_run_forwards_per_task_harness_and_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    from warding import mcp_core
    from warding.mcp_tools import spawn

    bodies: list[dict[str, Any]] = []

    def fake_post(path: str, body: dict[str, Any] | None = None, **_kw: Any) -> dict[str, Any]:
        if path == "/api/spawn":
            assert body is not None
            bodies.append(body)
            return {
                "id": f"id{len(bodies)}",
                "route": {
                    "harness": body.get("harness"),
                    "lane": body.get("harness"),
                    "routed": False,
                },
            }
        return {}

    monkeypatch.setattr(mcp_core, "_post", fake_post)
    monkeypatch.setattr(mcp_core, "_resolve_session_key", lambda: "dashboard:x")
    out = spawn.spawn_run(
        "spawn_run",
        {"tasks": ["a", "b"], "harnesses": ["claude", "codex"], "kinds": ["plan", "implement"]},
    )
    assert [(b["harness"], b["kind"]) for b in bodies] == [
        ("claude", "plan"),
        ("codex", "implement"),
    ]
    assert "on claude/claude" in out and "on codex/codex" in out
    mismatch = spawn.spawn_run("spawn_run", {"tasks": ["a", "b"], "harnesses": ["claude"]})
    assert mismatch.startswith("Error: harnesses length")


def test_route_task_tool_renders_the_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    from warding import mcp_core
    from warding.mcp_tools import routing

    seen: list[str] = []
    decision = decide(_full_house(), {}, _INSTALLED, kind="review", now=NOW).to_dict()

    def fake_get(path: str, session_key: str | None = None) -> dict[str, Any]:
        seen.append(path)
        return decision

    monkeypatch.setattr(mcp_core, "_get", fake_get)
    out = routing.route_task("route_task", {"kind": "review"})
    assert seen == ["/api/routing/decide?kind=review"]
    assert "lane 'claude'" in out and "harness='route'" in out


@pytest.mark.asyncio
async def test_api_decide_and_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from aiohttp.test_utils import make_mocked_request

    from warding.harness_router import api

    router = _router(tmp_path)
    monkeypatch.setattr(api, "get_router", lambda: router)
    resp = await api.api_decide(make_mocked_request("GET", "/api/routing/decide?kind=research"))
    body = json.loads(resp.body)
    assert body["code"] == "ok" and body["lane"] == "grok"
    status = json.loads((await api.api_status(make_mocked_request("GET", "/"))).body)
    assert status["code"] == "ok"


# ── subagent failover ──


class _FakeManager:
    """Just enough of SubagentManager for ``_run_accounted``."""

    def __init__(self, outcomes: list[Exception | None]) -> None:
        self._outcomes = outcomes
        self.ran_on: list[str] = []
        self.teardowns = 0
        self.events: list[dict[str, Any]] = []

    async def _run_inner(self, info: Any, session_key: str) -> None:
        self.ran_on.append(info.harness)
        outcome = self._outcomes.pop(0)
        if outcome is not None:
            raise outcome

    async def _teardown_run_session(self, info: Any, session_key: str) -> None:
        self.teardowns += 1

    async def _fire_event(self, name: str, info: Any, payload: dict[str, Any]) -> None:
        self.events.append(payload)


def _bind(manager: _FakeManager) -> SimpleNamespace:
    from warding.subagent import SubagentManager

    ns = SimpleNamespace()
    ns._run_inner = manager._run_inner
    ns._teardown_run_session = manager._teardown_run_session
    ns._fire_event = manager._fire_event
    ns._failover_lane = SubagentManager._failover_lane.__get__(ns)
    return ns


@pytest.mark.asyncio
async def test_routed_subagent_fails_over_after_a_usage_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from warding import subagent as subagent_mod
    from warding.harness_router import service
    from warding.subagent import SubagentInfo, SubagentManager

    router = _router(tmp_path)
    monkeypatch.setattr(service, "get_router", lambda: router)
    manager = _FakeManager(
        [RuntimeError("You've hit your usage limit. try again in 1 hours"), None]
    )
    info = SubagentInfo(
        id="a1", task="t", harness="codex", lane="codex", route_kind="implement", routed=True
    )
    monkeypatch.setattr(
        subagent_mod, "sel", lambda: SimpleNamespace(log_api_access=lambda **_: None)
    )
    await SubagentManager._run_accounted(_bind(manager), info, "subagent:a1")
    assert manager.ran_on[0] == "codex" and manager.ran_on[1] != "codex"
    assert info.lane == info.harness == manager.ran_on[1]
    assert manager.teardowns == 1
    usage = router.ledger.snapshot()
    assert usage["codex"].cooldown_reason == "usage_limit"
    assert usage[info.lane].ok == 1
    # Each outcome names the harness that produced it.
    assert usage["codex"].harness == "codex"
    assert usage[info.lane].harness == info.harness


@pytest.mark.asyncio
async def test_a_stalled_opencode_run_fails_over(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """OpenCode silent on a rate limit: the watchdog's AcpTurnStalled moves the run."""
    from warding import subagent as subagent_mod
    from warding.acp.client import AcpTurnStalled
    from warding.harness_router import service
    from warding.subagent import SubagentInfo, SubagentManager

    router = _router(tmp_path)
    monkeypatch.setattr(service, "get_router", lambda: router)
    manager = _FakeManager([AcpTurnStalled("opencode", 301.0), None])
    info = SubagentInfo(
        id="a5", task="t", harness="opencode", lane="opencode", route_kind="bulk", routed=True
    )
    monkeypatch.setattr(
        subagent_mod, "sel", lambda: SimpleNamespace(log_api_access=lambda **_: None)
    )
    await SubagentManager._run_accounted(_bind(manager), info, "subagent:a5")
    assert manager.ran_on[0] == "opencode" and manager.ran_on[1] != "opencode"
    assert router.ledger.snapshot()["opencode"].cooldown_reason == "rate_limit"


@pytest.mark.asyncio
async def test_pinned_subagent_does_not_move(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from warding.harness_router import service
    from warding.subagent import SubagentInfo, SubagentManager

    router = _router(tmp_path)
    monkeypatch.setattr(service, "get_router", lambda: router)
    manager = _FakeManager([RuntimeError("usage limit reached")])
    info = SubagentInfo(id="a2", task="t", harness="codex", lane="codex", routed=False)
    with pytest.raises(RuntimeError):
        await SubagentManager._run_accounted(_bind(manager), info, "subagent:a2")
    assert manager.ran_on == ["codex"]
    assert router.ledger.snapshot()["codex"].cooling(time.time())


@pytest.mark.asyncio
async def test_task_failure_is_not_a_lane_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from warding.harness_router import service
    from warding.subagent import SubagentInfo, SubagentManager

    router = _router(tmp_path)
    monkeypatch.setattr(service, "get_router", lambda: router)
    manager = _FakeManager([ValueError("the tests still fail")])
    info = SubagentInfo(id="a3", task="t", harness="codex", lane="codex", routed=True)
    with pytest.raises(ValueError):
        await SubagentManager._run_accounted(_bind(manager), info, "subagent:a3")
    assert manager.ran_on == ["codex"]
    assert not router.ledger.snapshot()["codex"].cooling(time.time())


@pytest.mark.asyncio
async def test_unaccounted_subagent_skips_the_router(monkeypatch: pytest.MonkeyPatch) -> None:
    from warding.harness_router import service
    from warding.subagent import SubagentInfo, SubagentManager

    def boom() -> None:
        raise AssertionError("router must not be consulted")

    monkeypatch.setattr(service, "get_router", boom)
    manager = _FakeManager([None])
    info = SubagentInfo(id="a4", task="t")
    await SubagentManager._run_accounted(_bind(manager), info, "subagent:a4")
    assert manager.ran_on == [""]


# ── connecting harnesses ──


class _FakeProvider:
    def __init__(self, error: Exception | None = None, models: int = 0) -> None:
        self._error = error
        self.shut = False
        entries = [{"modelId": f"m{i}"} for i in range(models)]
        self._client = SimpleNamespace(available_models=lambda: entries)

    async def start(self) -> None:
        if self._error is not None:
            raise self._error

    async def shutdown(self) -> None:
        self.shut = True


@pytest.mark.asyncio
async def test_probe_maps_outcomes_to_statuses() -> None:
    from warding.harness_router import connect

    made: list[_FakeProvider] = []

    def maker(error: Exception | None, models: int = 0):
        def make(harness: str, model: str) -> _FakeProvider:
            made.append(_FakeProvider(error, models))
            return made[-1]

        return make

    ok = await connect.probe_harness("codex", installed=True, make_provider=maker(None, 3))
    assert ok.status == connect.STATUS_CONNECTED and ok.models == 3
    assert len(ok.advertised) == 3
    auth = await connect.probe_harness(
        "grok",
        installed=True,
        make_provider=maker(RuntimeError("JSON-RPC error: Authentication required")),
    )
    assert auth.status == connect.STATUS_NEEDS_LOGIN and "Authentication" in auth.detail
    adapter = await connect.probe_harness(
        "claude",
        installed=True,
        make_provider=maker(RuntimeError("claude-agent-acp not found. Install it with 'npm i'")),
    )
    assert adapter.status == connect.STATUS_NOT_INSTALLED
    other = await connect.probe_harness(
        "cursor", installed=True, make_provider=maker(RuntimeError("boom"))
    )
    assert other.status == connect.STATUS_ERROR
    missing = await connect.probe_harness("cursor", installed=False, make_provider=maker(None))
    assert missing.status == connect.STATUS_NOT_INSTALLED
    assert all(p.shut for p in made) and len(made) == 4


@pytest.mark.asyncio
async def test_probe_times_out() -> None:
    from warding.harness_router import connect

    class Hang(_FakeProvider):
        async def start(self) -> None:
            import asyncio

            await asyncio.sleep(10)

    result = await connect.probe_harness(
        "codex", installed=True, timeout=0.01, make_provider=lambda h, m: Hang()
    )
    assert result.status == connect.STATUS_TIMEOUT


def test_probe_store_round_trip(tmp_path: Path) -> None:
    from warding.harness_router.connect import AdvertisedModel, ProbeResult, ProbeStore

    store = ProbeStore(tmp_path)
    assert store.load() == {}
    advertised = (AdvertisedModel("gpt-5.5", "GPT-5.5"), AdvertisedModel("gpt-5.5-mini"))
    store.save(ProbeResult("codex", "connected", models=2, checked_at=NOW, advertised=advertised))
    store.save(ProbeResult("grok", "needs_login", detail="x", checked_at=NOW))
    loaded = store.load()
    assert loaded["codex"].models == 2 and loaded["grok"].status == "needs_login"
    assert loaded["codex"].advertised == advertised
    assert loaded["grok"].advertised == ()


def test_probe_keeps_what_the_harness_advertised() -> None:
    from warding.harness_router.connect import PROBE_MODELS_MAX, ProbeResult

    raw = {
        "status": "connected",
        "advertised": [
            {"modelId": "anthropic/claude-x", "name": "Claude X"},
            {"value": "openrouter/deepseek"},
            {"modelId": "anthropic/claude-x"},  # duplicate
            {"modelId": ""},  # no id
            "not-a-dict",
        ],
    }
    parsed = ProbeResult.from_dict("opencode", raw)
    assert [(m.id, m.name) for m in parsed.advertised] == [
        ("anthropic/claude-x", "Claude X"),
        ("openrouter/deepseek", ""),
    ]
    many = {"advertised": [{"id": f"m{i}"} for i in range(PROBE_MODELS_MAX + 5)]}
    assert len(ProbeResult.from_dict("opencode", many).advertised) == PROBE_MODELS_MAX


def test_connected_within_is_fresh_connected_only() -> None:
    from warding.harness_router.connect import ProbeResult

    assert ProbeResult("codex", "connected", checked_at=NOW).connected_within(60, now=NOW + 30)
    assert not ProbeResult("codex", "connected", checked_at=NOW).connected_within(60, now=NOW + 61)
    assert not ProbeResult("codex", "needs_login", checked_at=NOW).connected_within(60, now=NOW)
    # A clock that went backwards is not evidence of a recent connection.
    assert not ProbeResult("codex", "connected", checked_at=NOW).connected_within(60, now=NOW - 5)


@pytest.mark.asyncio
async def test_verified_connection_reuses_a_fresh_probe_and_collapses_bursts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import asyncio
    import time as time_mod

    from warding.harness_router import connect, service

    router = _router(tmp_path)
    calls: list[str] = []

    async def fake_probe(harness: str, *, installed: bool, model: str = "", timeout: float) -> Any:
        calls.append(harness)
        await asyncio.sleep(0)
        return connect.ProbeResult(harness, connect.STATUS_CONNECTED, checked_at=time_mod.time())

    monkeypatch.setattr(service, "probe_harness", fake_probe)
    # Nothing recorded yet: a burst of callers shares one probe.
    results = await asyncio.gather(
        *(service.verified_connection("codex", max_age_secs=60, router=router) for _ in range(4))
    )
    assert calls == ["codex"]
    assert {r.status for r in results} == {connect.STATUS_CONNECTED}
    # Fresh enough: answered from the record, nothing spawned.
    await service.verified_connection("codex", max_age_secs=60, router=router)
    assert calls == ["codex"]
    # Stale: probed again.
    router.probes.save(connect.ProbeResult("codex", connect.STATUS_CONNECTED, checked_at=NOW))
    await service.verified_connection("codex", max_age_secs=60, router=router)
    assert calls == ["codex", "codex"]


def _check_router(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> HarnessRouter:
    """A router with a codex and a claude lane whose probes both start cleanly."""
    from warding.harness_router import connect

    (tmp_path / "routing.json").write_text(
        json.dumps(
            {"lanes": [{"id": "pro", "harness": "codex"}, {"id": "max", "harness": "claude"}]}
        ),
        encoding="utf-8",
    )

    async def fake_probe(harness: str, *, installed: bool, model: str = "") -> Any:
        return connect.ProbeResult(harness, connect.STATUS_CONNECTED, models=3, checked_at=NOW)

    monkeypatch.setattr(connect, "probe_harness", fake_probe)
    return _router(tmp_path)


def _check_lines(out: str) -> dict[str, str]:
    """``route check`` result lines keyed by lane id (the progress text before ``\\r`` dropped)."""
    lines: dict[str, str] = {}
    for raw in out.splitlines():
        line = raw.rsplit("\r", 1)[-1]
        cells = line.split()
        if cells and cells[0] in ("pro", "max"):
            lines[cells[0]] = line
    return lines


@pytest.mark.asyncio
async def test_route_check_reports_a_started_harness_as_auth_unverified(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from warding.harness_router import cli, connect

    router = _check_router(tmp_path, monkeypatch)
    code = await cli._check(router, [])
    out = capsys.readouterr().out
    lines = _check_lines(out)
    # The probe sends no prompt, so a harness that starts has not shown its sign-in works.
    assert "auth unverified" in lines["pro"] and "auth unverified" in lines["max"]
    assert "connected" not in out
    assert 'warding route run --harness LANE "reply ok"' in out
    assert code == 0
    # The stored machine status is unchanged; the gates that read it are not this command's.
    assert router.probes.load()["codex"].status == connect.STATUS_CONNECTED


@pytest.mark.asyncio
async def test_route_check_reports_needs_login_after_a_routed_run_failed_sign_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import time as time_mod

    from warding.harness_router import cli

    router = _check_router(tmp_path, monkeypatch)
    # A real prompt on the claude lane failed sign-in long enough ago that its rest is over.
    router.ledger.record_outcome(
        "max",
        ok=False,
        failure=limits.FAILURE_AUTH,
        text="Authentication required: OAuth session expired",
        harness="claude",
        now=time_mod.time() - 2 * 3600,
    )
    code = await cli._check(router, [])
    out = capsys.readouterr().out
    lines = _check_lines(out)
    assert "needs_login" in lines["max"] and "failed sign-in" in lines["max"]
    assert "log in: claude auth login" in out
    assert "auth unverified" in lines["pro"]
    assert code == 1

    # A later successful prompt clears the failed sign-in; the probe alone still shows
    # only that the harness starts.
    router.ledger.record_outcome("max", ok=True, harness="claude")
    code = await cli._check(router, [])
    lines = _check_lines(capsys.readouterr().out)
    assert "auth unverified" in lines["max"]
    assert code == 0


@pytest.mark.asyncio
async def test_route_check_reads_each_lane_ledger_after_its_probe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from warding.harness_router import cli, connect

    router = _check_router(tmp_path, monkeypatch)
    router.record_failure("max", text="Authentication required", harness="claude")

    async def probe_while_runs_finish(harness: str, *, installed: bool, model: str = "") -> Any:
        # Each probe can take minutes, so routed runs land while the check is going.
        if harness == "codex":
            # A routed prompt on claude succeeds while codex is still being probed...
            router.record_success("max", harness="claude")
            # ...and one on codex fails sign-in before its own probe returns.
            router.record_failure("pro", text="Authentication required", harness="codex")
        return connect.ProbeResult(harness, connect.STATUS_CONNECTED, models=3, checked_at=NOW)

    monkeypatch.setattr(connect, "probe_harness", probe_while_runs_finish)
    code = await cli._check(router, [])
    lines = _check_lines(capsys.readouterr().out)
    assert "needs_login" in lines["pro"]
    assert "auth unverified" in lines["max"]
    assert code == 1


@pytest.mark.asyncio
async def test_a_late_success_from_a_replaced_harness_keeps_the_new_harnesss_sign_in_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from warding.harness_router import cli

    router = _check_router(tmp_path, monkeypatch)
    # Lane "pro" now runs codex; a run started while it still ran claude is in flight.
    router.record_failure("pro", text="Authentication required", harness="codex")
    router.record_success("pro", harness="claude")
    used = router.ledger.snapshot()["pro"]
    assert (used.harness, used.cooldown_reason) == ("codex", limits.FAILURE_AUTH)
    assert used.ok == 1, "the stale run still counts as a completed run"
    code = await cli._check(router, [])
    lines = _check_lines(capsys.readouterr().out)
    assert "needs_login" in lines["pro"]
    assert code == 1

    # A success on the lane's current harness proves it works, whatever was recorded.
    router.record_success("pro", harness="codex")
    used = router.ledger.snapshot()["pro"]
    assert (used.harness, used.cooldown_reason, used.cooldown_until) == ("codex", "", 0.0)


@pytest.mark.asyncio
async def test_a_success_on_the_current_harness_clears_a_failure_the_old_harness_recorded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    router = _check_router(tmp_path, monkeypatch)
    router.record_failure("pro", text="Authentication required", harness="claude")
    router.record_success("pro", harness="codex")
    used = router.ledger.snapshot()["pro"]
    assert (used.harness, used.cooldown_reason, used.cooldown_until) == ("codex", "", 0.0)


def test_the_ledger_applies_a_success_unconditionally_when_no_current_harness_is_given(
    tmp_path: Path,
) -> None:
    ledger = UsageLedger(tmp_path)
    ledger.record_outcome("pro", ok=False, failure=limits.FAILURE_AUTH, text="x", harness="codex")
    ledger.record_outcome("pro", ok=True, harness="claude")
    used = ledger.snapshot()["pro"]
    assert (used.harness, used.cooldown_reason) == ("claude", "")


def test_a_success_reads_the_lanes_harness_only_while_the_ledger_lock_is_held(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    router = _check_router(tmp_path, monkeypatch)
    router.record_failure("pro", text="Authentication required", harness="codex")
    held = {"now": False, "asked": []}
    real_locked = router.ledger._locked

    @contextlib.contextmanager
    def watched_lock() -> Any:
        with real_locked():
            held["now"] = True
            try:
                yield
            finally:
                held["now"] = False

    real_settings = router.settings

    def watched_settings() -> Any:
        held["asked"].append(held["now"])
        return real_settings()

    monkeypatch.setattr(router.ledger, "_locked", watched_lock)
    monkeypatch.setattr(router, "settings", watched_settings)
    router.record_success("pro", harness="claude")
    assert held["asked"] == [True], "a mapping read before the lock could be reassigned meanwhile"
    assert router.ledger.snapshot()["pro"].cooldown_reason == limits.FAILURE_AUTH


def test_the_ledger_resolves_a_callable_current_harness_when_it_records(tmp_path: Path) -> None:
    ledger = UsageLedger(tmp_path)
    ledger.record_outcome("pro", ok=False, failure=limits.FAILURE_AUTH, text="x", harness="codex")
    ledger.record_outcome("pro", ok=True, harness="claude", current_harness=lambda: "codex")
    used = ledger.snapshot()["pro"]
    assert (used.harness, used.cooldown_reason) == ("codex", limits.FAILURE_AUTH)
    ledger.record_outcome("pro", ok=True, harness="codex", current_harness=lambda: "codex")
    used = ledger.snapshot()["pro"]
    assert (used.harness, used.cooldown_reason) == ("codex", "")


def test_a_success_still_records_when_the_lane_mapping_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    router = _check_router(tmp_path, monkeypatch)
    router.record_failure("pro", text="Authentication required", harness="codex")

    def broken_settings() -> Any:
        raise OSError("routing.json unreadable")

    monkeypatch.setattr(router, "settings", broken_settings)
    router.record_success("pro", harness="claude")
    used = router.ledger.snapshot()["pro"]
    # With no mapping to compare against the success applies as it did before the guard.
    assert (used.ok, used.harness, used.cooldown_reason) == (1, "claude", "")


@pytest.mark.asyncio
async def test_route_check_ignores_a_sign_in_failure_recorded_for_another_harness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from warding.harness_router import cli

    router = _check_router(tmp_path, monkeypatch)
    # Lane "pro" ran claude before routing.json pointed it at codex.
    router.record_failure("pro", text="Authentication required", harness="claude")
    assert router.ledger.snapshot()["pro"].harness == "claude"
    # A record that names no harness cannot say which sign-in failed.
    router.ledger.record_outcome("max", ok=False, failure=limits.FAILURE_AUTH, text="run /login")
    code = await cli._check(router, [])
    lines = _check_lines(capsys.readouterr().out)
    assert "auth unverified" in lines["pro"] and "auth unverified" in lines["max"]
    assert code == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("auth_harness", ["claude", "codex", ""])
async def test_route_check_keeps_auth_failure_attribution_after_an_ordinary_task_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    auth_harness: str,
) -> None:
    from warding.harness_router import cli

    router = _check_router(tmp_path, monkeypatch)
    router.ledger.record_outcome(
        "pro",
        ok=False,
        failure=limits.FAILURE_AUTH,
        text="Authentication required",
        harness=auth_harness,
        now=time.time() - 2 * 3600,
    )
    before = router.ledger.snapshot()["pro"]
    assert router.record_failure("pro", text="ordinary task failed", harness="codex") == (
        limits.FAILURE_OTHER
    )
    usage = router.ledger.snapshot()["pro"]
    assert usage.cooldown_reason == limits.FAILURE_AUTH
    assert usage.cooldown_until == before.cooldown_until
    assert usage.harness == auth_harness
    assert usage.failed == before.failed + 1 and usage.limited == before.limited

    code = await cli._check(router, [])
    out = capsys.readouterr().out
    lines = _check_lines(out)
    if auth_harness == "codex":
        assert "needs_login" in lines["pro"]
        assert "log in: codex login" in out
        assert code == 1
    else:
        assert "auth unverified" in lines["pro"]
        assert "log in:" not in out
        assert code == 0


def test_apply_lane_edit_updates_or_appends_and_validates() -> None:
    from warding.harness_router.lanes import RoutingConfigError, apply_lane_edit

    doc = {"lanes": [{"id": "max", "harness": "claude", "affinity": {"plan": 0.9}}]}
    new_doc, lane = apply_lane_edit(doc, "claude", {"weight": 3, "enabled": False})
    assert lane["id"] == "max" and lane["weight"] == 3.0 and lane["enabled"] is False
    assert new_doc["lanes"][0]["affinity"] == {"plan": 0.9}
    assert doc["lanes"][0].get("weight") is None  # input untouched
    appended, grok = apply_lane_edit(new_doc, "grok", {"billing": "metered"})
    assert grok["harness"] == "grok" and grok["billing"] == "metered"
    assert [ln["harness"] for ln in appended["lanes"]] == ["claude", "grok"]
    for bad in (
        {"weight": 0},
        {"weight": "3"},
        {"billing": "free-ish"},
        {"window_limit": -1},
        {"model": "../etc"},
        {"affinity": {}},
        {"enabled": "yes"},
    ):
        with pytest.raises(RoutingConfigError):
            apply_lane_edit(doc, "claude", bad)
    with pytest.raises(RoutingConfigError):
        apply_lane_edit(doc, "nope", {"enabled": True})


def test_save_lane_edit_materializes_and_refuses_a_broken_file(tmp_path: Path) -> None:
    from warding.harness_router.lanes import RoutingConfigError, save_lane_edit

    lane = save_lane_edit(
        "codex", {"window_limit": 150}, home=tmp_path, which=_which(_ALL_BINS), env={}
    )
    assert lane["window_limit"] == 150
    written = json.loads((tmp_path / "routing.json").read_text(encoding="utf-8"))
    assert {ln["harness"] for ln in written["lanes"]} >= {"claude", "codex", "grok"}
    (tmp_path / "routing.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(RoutingConfigError):
        save_lane_edit("codex", {"weight": 2}, home=tmp_path, which=_which(_ALL_BINS), env={})
    assert (tmp_path / "routing.json").read_text(encoding="utf-8") == "{broken"


def test_harnesses_view_lists_featured_and_installed(tmp_path: Path) -> None:
    from warding.harness_router.connect import ProbeResult

    router = _router(tmp_path, {"grok": "/b/grok", "goose": "/b/goose"})
    router.probes.save(ProbeResult("grok", "connected", models=2, checked_at=NOW))
    view = router.harnesses_view()
    names = [row["harness"] for row in view["harnesses"]]
    assert names[:5] == ["claude", "codex", "cursor", "grok", "opencode"]
    assert "goose" in names
    by = {row["harness"]: row for row in view["harnesses"]}
    assert by["grok"]["installed"] and by["grok"]["routed"]
    assert by["grok"]["probe"]["status"] == "connected"
    assert by["claude"]["installed"] is False and by["claude"]["probe"]["status"] == "unknown"
    assert by["claude"]["setup"]["login"] == "claude auth login"
    assert by["goose"]["setup"] is None and by["goose"]["hint"]
    assert view["preview"]["research"] == "grok"


@pytest.mark.asyncio
async def test_api_check_and_lane_edit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from aiohttp.test_utils import make_mocked_request

    from warding.harness_router import api, connect, service

    router = _router(tmp_path)
    monkeypatch.setattr(api, "get_router", lambda: router)

    async def fake_probe(harness: str, *, installed: bool, model: str = "", timeout: float) -> Any:
        return connect.ProbeResult(harness, connect.STATUS_NEEDS_LOGIN, checked_at=NOW)

    monkeypatch.setattr(service, "probe_harness", fake_probe)
    req = make_mocked_request(
        "POST", "/api/routing/harnesses/codex/check", match_info={"harness": "codex"}
    )
    body = json.loads((await api.api_check_harness(req)).body)
    assert body["probe"]["status"] == "needs_login"
    assert router.probes.load()["codex"].status == "needs_login"
    unknown = make_mocked_request("POST", "/x", match_info={"harness": "nope"})
    resp = await api.api_check_harness(unknown)
    assert resp.status == 404 and json.loads(resp.body)["code"] == "unknown_harness"

    class _Req:
        match_info = {"harness": "codex"}

        def __init__(self, payload: Any) -> None:
            self._payload = payload

        async def json(self) -> Any:
            return self._payload

    ok = await api.api_edit_lane(_Req({"weight": 2}))  # type: ignore[arg-type]
    assert json.loads(ok.body)["lane"]["weight"] == 2.0
    bad = await api.api_edit_lane(_Req({"weight": -5}))  # type: ignore[arg-type]
    assert bad.status == 400 and json.loads(bad.body)["code"] == "invalid_lane_edit"


@pytest.mark.asyncio
async def test_complete_setup_with_agents_needs_a_connected_agent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from aiohttp.test_utils import make_mocked_request

    from warding.dashboard.handlers import kiro_prerequisite as gate
    from warding.harness_router import service
    from warding.harness_router.connect import ProbeResult

    router = _router(tmp_path)
    monkeypatch.setattr(service, "get_router", lambda: router)

    async def owner(_request: Any) -> None:
        return None

    completed: list[bool] = []

    class _Service:
        async def complete_setup_without_kiro(self) -> dict[str, Any]:
            completed.append(True)
            return {"ready": False, "initial_setup_complete": True}

    monkeypatch.setattr(gate, "_dashboard_owner_only", owner)
    monkeypatch.setattr(gate, "_service", lambda _request: _Service())
    monkeypatch.setattr(gate, "sel", lambda: SimpleNamespace(log_api_access=lambda **_: None))

    req = make_mocked_request("POST", "/api/kiro-prerequisite/complete-with-agents")
    refused = await gate.api_kiro_prerequisite_complete_with_agents(req)
    assert refused.status == 409 and json.loads(refused.body)["code"] == "no_connected_agent"
    assert completed == []

    router.probes.save(ProbeResult("codex", "connected", checked_at=NOW))
    ok = await gate.api_kiro_prerequisite_complete_with_agents(req)
    body = json.loads(ok.body)
    assert ok.status == 200 and body["initial_setup_complete"] is True
    assert completed == [True]


def test_route_tasks_defaults_off_and_reads_strictly() -> None:
    assert parse_settings({"lanes": []}).route_tasks is False
    assert parse_settings({"lanes": [], "route_tasks": True}).route_tasks is True
    assert parse_settings({"lanes": [], "route_tasks": "yes"}).route_tasks is False


def test_save_settings_edit_materializes_validates_and_refuses_a_broken_file(
    tmp_path: Path,
) -> None:
    from warding.harness_router.lanes import RoutingConfigError, save_settings_edit

    saved = save_settings_edit({"route_tasks": True}, home=tmp_path, which=_which(_ALL_BINS))
    assert saved == {"route_tasks": True}
    written = json.loads((tmp_path / "routing.json").read_text(encoding="utf-8"))
    assert written["route_tasks"] is True and written["lanes"]  # detected lanes kept
    for bad in ({"route_tasks": "on"}, {"max_failover": 5}, {}):
        with pytest.raises(RoutingConfigError):
            save_settings_edit(bad, home=tmp_path, which=_which(_ALL_BINS))
    (tmp_path / "routing.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(RoutingConfigError):
        save_settings_edit({"route_tasks": False}, home=tmp_path)
    assert (tmp_path / "routing.json").read_text(encoding="utf-8") == "{broken"


@pytest.mark.parametrize("settings_first", [True, False])
def test_concurrent_settings_and_lane_edits_preserve_both_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings_first: bool
) -> None:
    from warding.harness_router import lanes

    path = lanes.routing_path(tmp_path)
    path.write_text(json.dumps(template_document(["codex"])), encoding="utf-8")
    first_read = threading.Event()
    second_started = threading.Event()
    second_read = threading.Event()
    release_first = threading.Event()
    real_read = lanes.current_document
    reads = 0
    read_lock = threading.Lock()

    def controlled_read(**kwargs):
        nonlocal reads
        document = real_read(**kwargs)
        with read_lock:
            reads += 1
            first = reads == 1
        if first:
            first_read.set()
            assert release_first.wait(5)
        else:
            second_read.set()
        return document

    monkeypatch.setattr(lanes, "current_document", controlled_read)

    def edit(settings, *, second=False):
        if second:
            second_started.set()
        if settings:
            return lanes.save_settings_edit({"route_tasks": True}, home=tmp_path)
        return lanes.save_lane_edit("codex", {"weight": 7.25}, home=tmp_path)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(edit, settings_first)
        try:
            assert first_read.wait(5)
            second = pool.submit(edit, not settings_first, second=True)
            assert second_started.wait(5)
            # Without serialization, finish the second stale-snapshot writer
            # before releasing the first, making the lost update reproducible.
            if second_read.wait(0.1):
                second.result(timeout=5)
        finally:
            release_first.set()
        first.result(timeout=5)
        second.result(timeout=5)

    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["route_tasks"] is True
    assert next(lane for lane in written["lanes"] if lane["harness"] == "codex")["weight"] == 7.25


@pytest.mark.asyncio
async def test_api_edit_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from warding.harness_router import api

    router = _router(tmp_path)
    monkeypatch.setattr(api, "get_router", lambda: router)

    class _Req:
        def __init__(self, payload: Any) -> None:
            self._payload = payload

        async def json(self) -> Any:
            return self._payload

    ok = await api.api_edit_settings(_Req({"route_tasks": True}))  # type: ignore[arg-type]
    assert json.loads(ok.body) == {"code": "ok", "settings": {"route_tasks": True}}
    assert router.harnesses_view()["route_tasks"] is True
    assert router.status()["route_tasks"] is True
    bad = await api.api_edit_settings(_Req({"route_tasks": 1}))  # type: ignore[arg-type]
    assert bad.status == 400 and json.loads(bad.body)["code"] == "invalid_settings_edit"
