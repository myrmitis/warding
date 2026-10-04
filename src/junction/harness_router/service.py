"""One object every surface uses: gateway, CLI, and subagent dispatch.

``HarnessRouter`` resolves a *target* (``route``, a lane id, or a harness name)
into a concrete lane, records dispatches and outcomes in the ledger, and picks
the next lane when one fails at the lane level. It holds no per-caller state:
settings are re-read when ``routing.json`` changes, and the installed-harness
probe is cached briefly because it walks ``PATH``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from junction.harness_router.connect import (
    FEATURED_HARNESSES,
    PROBE_TIMEOUT_SECS,
    STATUS_UNKNOWN,
    ProbeResult,
    ProbeStore,
    login_hint,
    ordered_harnesses,
    probe_harness,
    setup_for,
)
from junction.harness_router.kinds import TASK_KINDS, normalize_kind
from junction.harness_router.lanes import (
    Lane,
    RoutingSettings,
    WhichFn,
    harness_name,
    installed_harnesses,
    is_routable_harness,
    lane_from_profile,
    load_settings,
    routing_path,
)
from junction.harness_router.ledger import LEDGER_DIRNAME, UsageLedger
from junction.harness_router.limits import (
    FAILURE_OTHER,
    LANE_FAILURES,
    classify_exception,
    classify_failure,
)
from junction.harness_router.profiles import profile_for
from junction.harness_router.router import DECISION_OK, Decision, decide

logger = logging.getLogger(__name__)

# Targets that ask the router to choose.
ROUTE_TARGETS: frozenset[str] = frozenset({"route", "routed", "best"})

# PATH walks are cheap but not free; a harness installed mid-session shows up
# within this many seconds.
INSTALLED_CACHE_SECS = 30.0


class RoutingError(LookupError):
    """A target could not be resolved to a usable lane."""

    def __init__(self, message: str, *, code: str, decision: Decision | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.decision = decision


@dataclass(frozen=True)
class Resolution:
    """A resolved dispatch target."""

    lane: Lane
    kind: str
    routed: bool  # True when the router chose; False for an explicit target
    decision: Decision | None = None

    @property
    def backend(self) -> str:
        return self.lane.backend

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane.id,
            "harness": self.lane.harness,
            "model": self.lane.model,
            "kind": self.kind,
            "routed": self.routed,
            "reason": self.decision.reason if self.decision else "explicit target",
        }


class HarnessRouter:
    """Subscription-aware harness router."""

    def __init__(
        self,
        *,
        home: Path | None = None,
        ledger: UsageLedger | None = None,
        which: WhichFn | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._home = home
        self._which = which
        self._env = env
        self._ledger = ledger or UsageLedger((home / LEDGER_DIRNAME) if home is not None else None)
        self._lock = threading.Lock()
        self._settings: RoutingSettings | None = None
        self._settings_mtime: float | None = -1.0
        self._settings_installed: tuple[str, ...] = ()
        self._installed: tuple[str, ...] = ()
        self._installed_at = 0.0

    @property
    def ledger(self) -> UsageLedger:
        return self._ledger

    @property
    def home(self) -> Path | None:
        return self._home

    @property
    def probes(self) -> ProbeStore:
        """Last connection probe per harness, stored beside the ledger."""
        return ProbeStore(self._ledger.path.parent)

    # ── Inputs ──

    def settings(self) -> RoutingSettings:
        path = routing_path(self._home)
        try:
            mtime: float | None = path.stat().st_mtime
        except OSError:
            mtime = None
        # Detected lanes track the installed set, so a harness installed while
        # the gateway runs becomes a lane without a restart.
        installed = self.installed()
        with self._lock:
            cached = self._settings
            stale = (
                cached is None
                or mtime != self._settings_mtime
                or (cached.source == "auto" and installed != self._settings_installed)
            )
            if stale:
                cached = load_settings(home=self._home, which=self._which, env=self._env)
                self._settings = cached
                self._settings_mtime = mtime
                self._settings_installed = installed
                for warning in cached.warnings:
                    logger.warning("routing: %s", warning)
            assert cached is not None
            return cached

    def installed(self, *, refresh: bool = False) -> tuple[str, ...]:
        now = time.monotonic()
        with self._lock:
            if refresh or not self._installed_at or now - self._installed_at > INSTALLED_CACHE_SECS:
                self._installed = tuple(installed_harnesses(which=self._which, env=self._env))
                self._installed_at = now
            return self._installed

    # ── Decisions ──

    def decide(
        self,
        kind: str | None = None,
        *,
        role: str | None = None,
        prefer: Iterable[str] = (),
        exclude: Iterable[str] = (),
    ) -> Decision:
        return decide(
            self.settings(),
            self._ledger.snapshot(),
            self.installed(),
            kind=kind,
            role=role,
            prefer=prefer,
            exclude=exclude,
        )

    def resolve(
        self,
        target: str | None,
        *,
        kind: str | None = None,
        role: str | None = None,
        exclude: Collection[str] = (),
    ) -> Resolution:
        """Turn ``route`` / a lane id / a harness name into a lane.

        An explicit lane or harness is honoured even while it is resting: the
        caller asked for it by name, and the harness's own error is a better
        message than a refusal from here.
        """
        value = (target or "").strip().lower()
        task_kind = normalize_kind(kind, role=role)
        if not value or value in ROUTE_TARGETS:
            decision = self.decide(task_kind, exclude=exclude)
            if decision.code != DECISION_OK or decision.lane is None:
                raise RoutingError(decision.reason, code=decision.code, decision=decision)
            return Resolution(lane=decision.lane, kind=task_kind, routed=True, decision=decision)
        settings = self.settings()
        lane = settings.lane(value)
        if lane is None:
            matches = [ln for ln in settings.lanes_for_harness(value) if ln.enabled]
            if matches:
                # Several lanes on one harness: let the scorer pick among them.
                decision = decide(
                    RoutingSettings(lanes=tuple(matches)),
                    self._ledger.snapshot(),
                    self.installed(),
                    kind=task_kind,
                )
                lane = decision.lane or matches[0]
            elif is_routable_harness(value):
                lane = lane_from_profile(profile_for(value))
        if lane is None:
            raise RoutingError(
                f"unknown lane or harness {target!r}; see `warding route status`",
                code="unknown_target",
            )
        if lane.harness not in self.installed():
            raise RoutingError(
                f"harness {lane.harness!r} is not installed on this host",
                code="not_installed",
            )
        return Resolution(lane=lane, kind=task_kind, routed=False)

    def next_lane(self, kind: str, tried: Collection[str]) -> Lane | None:
        """Best eligible lane not in *tried*, for failover. ``None`` when none remain."""
        decision = self.decide(kind, exclude=tried)
        return decision.lane if decision.code == DECISION_OK else None

    # ── Recording (never raises: accounting must not fail a run) ──

    def record_dispatch(self, lane_id: str, kind: str = "") -> None:
        try:
            self._ledger.record_dispatch(lane_id, kind)
        except Exception:
            logger.warning("routing: could not record dispatch to %s", lane_id, exc_info=True)

    def _current_harness(self, lane_id: str) -> str:
        """The harness *lane_id* runs now; ``""`` when the mapping cannot be read."""
        try:
            lane = self.settings().lane(lane_id)
        except Exception:
            logger.warning("routing: could not read the harness of %s", lane_id, exc_info=True)
            return ""
        return lane.harness if lane else ""

    def record_success(self, lane_id: str, *, harness: str = "") -> None:
        try:
            # Resolved by the ledger once it holds its lock: a mapping read before that
            # could be reassigned, and a failure recorded for the new harness, in between.
            self._ledger.record_outcome(
                lane_id,
                ok=True,
                harness=harness,
                current_harness=lambda: self._current_harness(lane_id),
            )
        except Exception:
            logger.warning("routing: could not record success on %s", lane_id, exc_info=True)

    def record_failure(
        self,
        lane_id: str,
        *,
        exc: BaseException | None = None,
        text: str = "",
        harness: str = "",
    ) -> str:
        """Record a failed dispatch on *harness*. Returns the failure class."""
        detail = text or (str(exc) if exc is not None else "")
        failure = classify_exception(exc) if exc is not None else classify_failure(detail)
        if failure == FAILURE_OTHER and exc is not None and text:
            failure = classify_failure(text)
        try:
            until = self._ledger.record_outcome(
                lane_id, ok=False, failure=failure, text=detail, harness=harness
            )
            if failure in LANE_FAILURES:
                logger.warning(
                    "routing: lane %s resting (%s) for %.0fs",
                    lane_id,
                    failure,
                    max(0.0, until - time.time()),
                )
        except Exception:
            logger.warning("routing: could not record failure on %s", lane_id, exc_info=True)
        return failure

    # ── Status ──

    def harnesses_view(self) -> dict[str, Any]:
        """Every connectable harness with install state, last probe, and its lane.

        What the dashboard's Agents & plans panel renders: the featured
        subscriptions always, plus any other harness that is installed or has a
        lane. Setup commands and probe outcomes are machine data; the dashboard
        owns every displayed word.
        """
        settings = self.settings()
        installed = self.installed(refresh=True)
        usage = self._ledger.snapshot()
        probes = self.probes.load()
        now = time.time()
        rows = []
        for name in ordered_harnesses(installed, [ln.harness for ln in settings.lanes]):
            profile = profile_for(name)
            lanes = settings.lanes_for_harness(name)
            lane = lanes[0] if lanes else None
            used = usage.get(lane.id) if lane else None
            setup = setup_for(name)
            probe = probes.get(name) or ProbeResult(harness=name, status=STATUS_UNKNOWN)
            rows.append(
                {
                    "harness": name,
                    "label": profile.label,
                    "billing": lane.billing if lane else profile.billing,
                    "featured": name in FEATURED_HARNESSES,
                    "installed": name in installed,
                    "setup": setup.to_dict() if setup else None,
                    "hint": "" if setup else login_hint(name),
                    "lane": lane.to_dict() if lane else None,
                    "lane_count": len(lanes),
                    "routed": bool(lane and lane.enabled and name in installed),
                    "window_used": (
                        used.count_since(now - lane.window_hours * 3600) if used and lane else 0
                    ),
                    "day_used": used.count_since(now - 86400) if used else 0,
                    "cooldown_until": used.cooldown_until if used and used.cooling(now) else 0.0,
                    "cooldown_reason": used.cooldown_reason if used and used.cooling(now) else "",
                    "probe": probe.to_dict(),
                }
            )
        preview = {kind: self.decide(kind).to_dict()["lane"] for kind in TASK_KINDS}
        return {
            "code": "ok",
            "enabled": settings.enabled,
            "route_tasks": settings.route_tasks,
            "source": settings.source,
            "path": settings.path,
            "warnings": list(settings.warnings),
            "kinds": list(TASK_KINDS),
            "preview": preview,
            "harnesses": rows,
        }

    def status(self) -> dict[str, Any]:
        """Everything `warding route status` and the dashboard show."""
        settings = self.settings()
        installed = self.installed(refresh=True)
        usage = self._ledger.snapshot()
        now = time.time()
        lanes_out = []
        for lane in settings.lanes:
            used = usage.get(lane.id)
            row = lane.to_dict()
            row["installed"] = lane.harness in installed
            row["window_used"] = used.count_since(now - lane.window_hours * 3600) if used else 0
            row["day_used"] = used.count_since(now - 86400) if used else 0
            row["ok"] = used.ok if used else 0
            row["failed"] = used.failed if used else 0
            row["limited"] = used.limited if used else 0
            row["cooldown_until"] = used.cooldown_until if used and used.cooling(now) else 0.0
            row["cooldown_reason"] = used.cooldown_reason if used and used.cooling(now) else ""
            row["last_error"] = used.last_error if used else ""
            row["last_used"] = used.last_used if used else 0.0
            lanes_out.append(row)
        configured = {lane.harness for lane in settings.lanes}
        preview = {kind: self.decide(kind).to_dict()["lane"] for kind in TASK_KINDS}
        return {
            "code": "ok",
            "enabled": settings.enabled,
            "source": settings.source,
            "path": settings.path,
            "warnings": list(settings.warnings),
            "installed": list(installed),
            "unrouted_installed": [h for h in installed if h not in configured],
            "lanes": lanes_out,
            "kinds": list(TASK_KINDS),
            "preview": preview,
            "max_failover": settings.max_failover,
            "route_tasks": settings.route_tasks,
        }


_default: HarnessRouter | None = None
_default_lock = threading.Lock()


def get_router() -> HarnessRouter:
    """Process-wide router bound to the current data home.

    Rebuilt when the data home changes (a test pinning ``JUNCTION_HOME``), so a
    router never writes one home's ledger while reading another's settings.
    """
    from junction.config.paths import data_home

    global _default
    home = data_home()
    with _default_lock:
        if _default is None or _default.home != home:
            _default = HarnessRouter(home=home)
        return _default


def reset_router() -> None:
    """Forget the process-wide router (tests, data-home switch)."""
    global _default
    with _default_lock:
        _default = None


# One probe per harness at a time: a double-clicked Check, or a Check racing a
# readiness re-probe, must not spawn two harness processes. Gateway-process
# state, keyed by harness name.
_probe_locks: dict[str, asyncio.Lock] = {}


async def _probe_and_record(router: HarnessRouter, harness: str, timeout: float) -> ProbeResult:
    installed = harness in await asyncio.to_thread(router.installed, refresh=True)
    settings = await asyncio.to_thread(router.settings)
    lanes = settings.lanes_for_harness(harness)
    result = await probe_harness(
        harness,
        installed=installed,
        model=lanes[0].model if lanes else "",
        timeout=timeout,
    )
    await asyncio.to_thread(router.probes.save, result)
    logger.info("routing probe %s: %s", harness, result.status)
    return result


async def check_harness(
    harness: str,
    *,
    router: HarnessRouter | None = None,
    timeout: float = PROBE_TIMEOUT_SECS,
) -> ProbeResult:
    """Probe *harness* now and record the outcome."""
    router = router or get_router()
    async with _probe_locks.setdefault(harness, asyncio.Lock()):
        return await _probe_and_record(router, harness, timeout)


async def verified_connection(
    harness: str,
    *,
    max_age_secs: float,
    router: HarnessRouter | None = None,
    timeout: float = PROBE_TIMEOUT_SECS,
) -> ProbeResult:
    """The last probe of *harness* when it connected recently enough, else a new one.

    For callers that must not act on a stale answer (a rerun that rewrites
    history first). The freshness check runs under the per-harness lock, so a
    burst of callers collapses onto one probe.
    """
    router = router or get_router()
    async with _probe_locks.setdefault(harness, asyncio.Lock()):
        last = (await asyncio.to_thread(router.probes.load)).get(harness)
        if last is not None and last.connected_within(max_age_secs, now=time.time()):
            return last
        return await _probe_and_record(router, harness, timeout)


__all__ = [
    "HarnessRouter",
    "Resolution",
    "RoutingError",
    "ROUTE_TARGETS",
    "check_harness",
    "get_router",
    "harness_name",
    "reset_router",
    "verified_connection",
]
