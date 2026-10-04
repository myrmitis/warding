"""Harness-router dispatch for task-runner steps.

Opt-in: a run routes its steps only when routing.json's ``route_tasks`` is on
(or the start request asked for it), fixed on the run when it first executes.
Otherwise every step runs on the configured agent, exactly as before.

A routed step asks the router for the best lane for its kind, runs on that
lane's harness (and model), and reports the outcome to the routing ledger, so a
usage limit hit by one step rests that lane for every later step, subagent and
run. The rules mirror routed subagents (``SubagentManager._run_accounted``):

* A step keeps its lane while its conversation lives: a retry after an ordinary
  failure (tests red, a review issue) stays on the same agent.
* A lane-level failure (usage or rate limit, sign-in, missing harness, a silent
  stall) releases the lane, so the next attempt goes to the next best one.
  Before any tool ran that move is free (the attempt is not counted), up to
  ``max_failover`` free hops per step; after a tool ran it costs an attempt,
  since the step already changed the workspace.
* Initially no eligible lane (every one resting, none installed) falls back to
  the configured agent. Once a step has encountered a lane failure, exhaustion
  fails the step instead of retrying a cooling harness without lane accounting.
  A hard daily-cap refusal also fails closed on initial selection.
* A step's lane outlives the process. The executor writes the lane (and its
  model, or the configured-agent fallback) onto the task before each dispatch,
  and a paused or crash-recovered step restores exactly that lane
  (``StepRoute.for_task``) instead of re-scoring headroom that its own earlier
  dispatch already reduced. A saved lane that is gone, disabled, uninstalled,
  re-pointed at another harness, resting or at its daily cap refuses the resume
  rather than moving a half-done step to another provider. The restored lane may
  already have changed the workspace, so its first lane-level failure is never a
  free move.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import threading
import time
from collections.abc import Collection
from typing import Any

from junction.harness_router import service
from junction.harness_router.kinds import normalize_kind
from junction.harness_router.limits import LANE_FAILURES
from junction.harness_router.router import DAILY_LIMIT_WINDOW_SECS, EXCLUDED_DAILY_CAP
from junction.harness_router.service import RoutingError

logger = logging.getLogger(__name__)

# The router picks; see harness_router.service.ROUTE_TARGETS.
_ROUTE_TARGET = "route"
# Role whose default kind a step without a named kind routes as.
_STEP_ROLE = "execution"

# ``Task.lane_id`` of a step that fell back to the configured agent. Not a valid
# lane id (``LANE_ID_PATTERN``), so it cannot collide with a routing.json lane.
CONFIGURED_AGENT_LANE = "@configured"
# RoutingError code for a saved lane that cannot take its step back.
LANE_UNAVAILABLE = "lane_unavailable"

# Parallel task steps must publish the selected lane's usage before another
# step scores the ledger. Only selection and dispatch accounting hold this
# process-local lock; model execution remains parallel.
_dispatch_lock = threading.Lock()


def route_tasks_enabled() -> bool:
    """routing.json's ``route_tasks`` switch. Unreadable settings mean off."""
    try:
        router = service.get_router()
        settings = router.settings()
        return bool(settings.enabled and settings.route_tasks)
    except Exception:
        logger.warning("routing settings unreadable; task steps stay unrouted", exc_info=True)
        return False


@dataclasses.dataclass(frozen=True)
class LaneBinding:
    """The lane a step was last dispatched on, as saved on its ``Task``."""

    lane_id: str
    model: str = ""
    harness: str = ""


class StepRoute:
    """The lane one routed step (or review pass) runs on, and its accounting."""

    def __init__(
        self,
        kind: str,
        *,
        router: Any = None,
        avoid: Collection[str] = (),
        restore: LaneBinding | None = None,
    ) -> None:
        self.kind = normalize_kind(kind, role=_STEP_ROLE)
        self._router = router
        # Lanes to prefer not to use (a review avoids the lane that did the
        # work) — honoured only while another lane is eligible.
        self._avoid = tuple(lane for lane in avoid if lane)
        self.lane: Any = None
        self._resolved = False
        self.tried: list[str] = []
        self.free_hops = 0
        # The saved lane to rehydrate on the first pick (see for_task). Cleared
        # when that lane is released, so a later pick resolves normally.
        self._restore = restore
        # True while on a restored lane: an earlier process may already have
        # worked the step, so a lane-level failure there is not a free move.
        self._resumed = False

    @classmethod
    def for_task(cls, task: Any, **kwargs: Any) -> "StepRoute":
        """The route for *task*, restoring the lane it was last dispatched on."""
        lane_id = str(getattr(task, "lane_id", "") or "")
        saved = (
            LaneBinding(
                lane_id,
                str(getattr(task, "lane_model", "") or ""),
                str(getattr(task, "harness", "") or ""),
            )
            if lane_id
            else None
        )
        return cls(getattr(task, "kind", ""), restore=saved, **kwargs)

    @property
    def binding(self) -> tuple[str, str]:
        """``(lane id, model)`` to save on the task; ``("", "")`` when unbound.

        A step that fell back to the configured agent saves
        ``CONFIGURED_AGENT_LANE``, so a resume does not cross to a lane that
        has since recovered.
        """
        if self.lane is not None:
            return self.lane.id, self.lane.model
        if self._resolved:
            return CONFIGURED_AGENT_LANE, ""
        return "", ""

    def _get_router(self) -> Any:
        if self._router is None:
            self._router = service.get_router()
        return self._router

    async def pick(self) -> Any:
        """The lane for this attempt, recording a dispatch; ``None`` = unrouted.

        Sticky: an attempt after an ordinary failure reuses the current lane.
        """
        return await asyncio.to_thread(self._pick_and_record)

    def _pick_and_record(self) -> Any:
        with _dispatch_lock:
            if not self._resolved:
                if self._restore is not None:
                    self.lane = self._rehydrate(self._restore)
                    self._resumed = self.lane is not None
                else:
                    self.lane = self._resolve()
                self._resolved = True  # A configured-agent fallback is sticky too.
            if self.lane is not None:
                router = self._get_router()
                # Conversation affinity cannot waive a hard dispatch budget.
                # Refuse a capped retry without moving its provider attribution.
                current = router.settings().lane(self.lane.id) or self.lane
                if current.daily_limit > 0:
                    usage = router.ledger.snapshot().get(self.lane.id)
                    if (
                        usage is not None
                        and usage.count_since(time.time() - DAILY_LIMIT_WINDOW_SECS)
                        >= current.daily_limit
                    ):
                        raise RoutingError(
                            "Task lane reached its daily dispatch cap", code=EXCLUDED_DAILY_CAP
                        )
                router.record_dispatch(self.lane.id, self.kind)
            return self.lane

    def _rehydrate(self, saved: LaneBinding) -> Any:
        """The lane *saved* names, or ``RoutingError``: a resume never switches providers."""
        if saved.lane_id == CONFIGURED_AGENT_LANE:
            return None  # The step ran on the configured agent; so does its resume.
        try:
            router = self._get_router()
            settings = router.settings()
            lane = settings.lane(saved.lane_id)
            problem = ""
            if lane is None:
                problem = "is no longer configured"
            elif saved.harness and lane.harness != saved.harness:
                problem = f"now runs {lane.harness}, not {saved.harness}"
            elif not settings.enabled or not lane.enabled:
                problem = "is disabled"
            elif lane.harness not in router.installed():
                problem = f"has no {lane.harness} harness installed"
            else:
                usage = router.ledger.snapshot().get(lane.id)
                if usage is not None and usage.cooling(time.time()):
                    problem = f"is resting after {usage.cooldown_reason or 'a limit'}"
        except Exception as exc:
            raise RoutingError(
                f"Cannot read routing settings to resume task lane {saved.lane_id}",
                code=LANE_UNAVAILABLE,
            ) from exc
        if problem:
            raise RoutingError(
                f"Task lane {saved.lane_id} {problem}; its unfinished step stays on that "
                "agent, so retry the task to start it on another",
                code=LANE_UNAVAILABLE,
            )
        self.tried.append(lane.id)
        # The step keeps the model it started on, even if the lane's configured
        # model changed while the run was paused.
        return lane if lane.model == saved.model else dataclasses.replace(lane, model=saved.model)

    def _resolve(self) -> Any:
        router = self._get_router()
        attempts = (
            [(*self.tried, *self._avoid), tuple(self.tried)] if self._avoid else [tuple(self.tried)]
        )
        capped = False
        for exclude in attempts:
            try:
                resolution = router.resolve(_ROUTE_TARGET, kind=self.kind, exclude=exclude)
            except RoutingError as exc:
                # A cooldown can mask the cap in the scoring exclusion reason.
                # Inspect the actual budget before permitting initial fallback.
                usage = router.ledger.snapshot()
                capped = capped or bool(
                    exc.decision
                    and any(
                        candidate.lane.daily_limit > 0
                        and candidate.lane.id in usage
                        and usage[candidate.lane.id].count_since(
                            time.time() - DAILY_LIMIT_WINDOW_SECS
                        )
                        >= candidate.lane.daily_limit
                        for candidate in exc.decision.candidates
                    )
                )
                logger.info("task step (%s): no lane excluding %s: %s", self.kind, exclude, exc)
                continue
            except Exception:
                if self.tried:
                    raise
                logger.warning("task step routing failed; running unrouted", exc_info=True)
                return None
            self.tried.append(resolution.lane.id)
            return resolution.lane
        if self.tried:
            raise RoutingError(
                "No eligible task lane remains after lane failure", code="no_eligible_lane"
            )
        if capped:
            raise RoutingError(
                "Task lanes reached their daily dispatch cap", code=EXCLUDED_DAILY_CAP
            )
        logger.warning(
            "task step (%s): no eligible lane; running on the configured agent", self.kind
        )
        return None

    async def succeeded(self) -> None:
        if self.lane is not None:
            await asyncio.to_thread(self._get_router().record_success, self.lane.id)

    async def failed(self, exc: BaseException, *, tool_ran: bool) -> bool:
        """Record a failed attempt. True when the step moves lanes for free.

        A lane-level failure always releases the lane, so the next attempt
        resolves a new one; it is free (the caller does not count the attempt)
        only before any tool ran and within ``max_failover`` hops.
        """
        if self.lane is None:
            return False
        router = self._get_router()
        failure = await asyncio.to_thread(router.record_failure, self.lane.id, exc=exc)
        if failure not in LANE_FAILURES:
            return False
        previous = self.lane.id
        resumed = self._resumed
        self.lane = None
        self._resolved = False
        self._restore = None
        self._resumed = False
        if tool_ran or resumed:
            logger.warning(
                "task step: lane %s failed (%s) after %s",
                previous,
                failure,
                "tool use" if tool_ran else "a resume that may have already changed the workspace",
            )
            return False
        settings = await asyncio.to_thread(router.settings)
        if self.free_hops >= settings.max_failover:
            return False
        self.free_hops += 1
        logger.warning("task step: lane %s failed (%s); moving to another lane", previous, failure)
        return True
