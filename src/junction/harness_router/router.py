"""Pick the lane for one unit of work.

The objective is *maximum useful work from what the operator already pays
for*:

1. **Spend flat-rate quota first.** A subscription's unused window is lost at
   reset, so subscription and free lanes outrank metered ones unless the
   metered lane is clearly better at the task.
2. **Spread load by headroom.** Each lane's usage in its rolling window is
   compared with its capacity (``window_limit`` when stated, else ``weight``
   times a nominal allowance). A lane near its cap yields to one with room, so
   no plan hits its limit while another sits idle.
3. **Match the task.** Affinity for the task kind (plan, implement, review, …)
   decides between lanes with similar headroom.
4. **Route around trouble.** A lane resting after a usage limit, rate limit or
   failed login is skipped until its reset; a metered lane past its daily cap
   is skipped outright.

Scoring is pure over (lanes, ledger snapshot, installed set) so it is cheap,
deterministic and testable without spawning anything.
"""

from __future__ import annotations

import time
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from junction.harness_router.kinds import normalize_kind
from junction.harness_router.lanes import Lane, RoutingSettings
from junction.harness_router.ledger import LaneUsage
from junction.harness_router.profiles import BILLING_METERED

# Nominal dispatches per window for one unit of weight when a lane states no
# window_limit. Only the ratio between lanes matters for spreading load; the
# absolute value decides how fast an unlimited lane's headroom falls.
NOMINAL_WINDOW_DISPATCHES = 40

# Score = billing_factor × (AFFINITY_WEIGHT × affinity + HEADROOM_WEIGHT × headroom)
AFFINITY_WEIGHT = 0.6
HEADROOM_WEIGHT = 0.4
# Metered lanes compete at this fraction of their score: a clearly better fit
# (bulk work on a cheap OpenRouter model) can still win, a tie cannot.
METERED_FACTOR = 0.6
# A lane at or past its stated window_limit is not excluded (the stated limit
# may be conservative) but falls behind every lane with room.
EXHAUSTED_FACTOR = 0.15
# Bonus for a lane or harness the caller prefers.
PREFER_BONUS = 0.08
# Hard dispatch caps use a rolling day, independent of each lane's plan window.
DAILY_LIMIT_WINDOW_SECS = 24 * 3600

DECISION_OK = "ok"
DECISION_NO_LANE = "no_lane"
DECISION_DISABLED = "routing_disabled"

EXCLUDED_DISABLED = "disabled"
EXCLUDED_NOT_INSTALLED = "not_installed"
EXCLUDED_COOLDOWN = "cooldown"
EXCLUDED_DAILY_CAP = "daily_cap"
EXCLUDED_BY_CALLER = "excluded"


@dataclass(frozen=True)
class Candidate:
    """One lane's standing for a decision."""

    lane: Lane
    score: float
    affinity: float
    headroom: float
    window_used: int
    window_capacity: int
    excluded: str = ""
    cooldown_until: float = 0.0
    note: str = ""

    @property
    def eligible(self) -> bool:
        return not self.excluded

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane.id,
            "harness": self.lane.harness,
            "label": self.lane.label,
            "billing": self.lane.billing,
            "model": self.lane.model,
            "score": round(self.score, 4),
            "affinity": round(self.affinity, 3),
            "headroom": round(self.headroom, 3),
            "window_used": self.window_used,
            "window_capacity": self.window_capacity,
            "eligible": self.eligible,
            "excluded": self.excluded,
            "cooldown_until": self.cooldown_until,
            "note": self.note,
        }


@dataclass(frozen=True)
class Decision:
    """The router's answer: the chosen lane plus the ranked field."""

    kind: str
    code: str
    chosen: Candidate | None
    candidates: tuple[Candidate, ...] = field(default_factory=tuple)
    reason: str = ""

    @property
    def lane(self) -> Lane | None:
        return self.chosen.lane if self.chosen else None

    @property
    def fallbacks(self) -> tuple[Lane, ...]:
        chosen_id = self.chosen.lane.id if self.chosen else ""
        return tuple(c.lane for c in self.candidates if c.eligible and c.lane.id != chosen_id)

    def to_dict(self) -> dict[str, Any]:
        lane = self.lane
        return {
            "code": self.code,
            "kind": self.kind,
            "lane": lane.id if lane else "",
            "harness": lane.harness if lane else "",
            "model": lane.model if lane else "",
            "label": lane.label if lane else "",
            "reason": self.reason,
            "fallbacks": [f.id for f in self.fallbacks],
            "candidates": [c.to_dict() for c in self.candidates],
        }


def _window_capacity(lane: Lane) -> int:
    if lane.window_limit > 0:
        return lane.window_limit
    return max(1, round(NOMINAL_WINDOW_DISPATCHES * lane.weight))


def score_lane(
    lane: Lane,
    kind: str,
    usage: LaneUsage | None,
    *,
    now: float,
    installed: bool,
    excluded_by_caller: bool = False,
    preferred: bool = False,
) -> Candidate:
    """Score one lane for *kind*. Pure."""
    usage = usage or LaneUsage()
    affinity = lane.affinity_for(kind)
    window_used = usage.count_since(now - lane.window_hours * 3600)
    capacity = _window_capacity(lane)
    headroom = max(0.0, 1.0 - window_used / capacity)
    excluded = ""
    note = ""
    if excluded_by_caller:
        excluded = EXCLUDED_BY_CALLER
    elif not lane.enabled:
        excluded = EXCLUDED_DISABLED
    elif not installed:
        excluded = EXCLUDED_NOT_INSTALLED
    elif usage.cooling(now):
        excluded = EXCLUDED_COOLDOWN
        note = usage.cooldown_reason
    elif (
        lane.daily_limit > 0
        and usage.count_since(now - DAILY_LIMIT_WINDOW_SECS) >= lane.daily_limit
    ):
        excluded = EXCLUDED_DAILY_CAP
    score = AFFINITY_WEIGHT * affinity + HEADROOM_WEIGHT * headroom
    if lane.billing == BILLING_METERED:
        score *= METERED_FACTOR
    if lane.window_limit > 0 and window_used >= lane.window_limit:
        score *= EXHAUSTED_FACTOR
        note = note or "window limit reached"
    if preferred:
        score += PREFER_BONUS
    return Candidate(
        lane=lane,
        score=score if not excluded else 0.0,
        affinity=affinity,
        headroom=headroom,
        window_used=window_used,
        window_capacity=capacity,
        excluded=excluded,
        cooldown_until=usage.cooldown_until if usage.cooling(now) else 0.0,
        note=note,
    )


def _explain(chosen: Candidate, kind: str, runner_up: Candidate | None) -> str:
    lane = chosen.lane
    parts = [
        f"{lane.id} ({lane.label}) for {kind}: affinity {chosen.affinity:.2f}, "
        f"headroom {chosen.headroom:.0%} ({chosen.window_used}/{chosen.window_capacity} "
        f"in {lane.window_hours:g}h), {lane.billing}"
    ]
    if runner_up is not None:
        parts.append(f"next best {runner_up.lane.id} at {runner_up.score:.2f}")
    return "; ".join(parts)


def decide(
    settings: RoutingSettings,
    usage: Mapping[str, LaneUsage],
    installed: Collection[str],
    *,
    kind: str | None = None,
    role: str | None = None,
    prefer: Iterable[str] = (),
    exclude: Iterable[str] = (),
    now: float | None = None,
) -> Decision:
    """Rank every lane for *kind* and pick the best eligible one.

    *installed* holds operator-facing harness names this host can spawn.
    *prefer* and *exclude* accept lane ids or harness names.
    """
    moment = time.time() if now is None else now
    task_kind = normalize_kind(kind, role=role)
    prefer_set = {p.strip().lower() for p in prefer if p}
    exclude_set = {e.strip().lower() for e in exclude if e}
    if not settings.enabled:
        return Decision(
            kind=task_kind,
            code=DECISION_DISABLED,
            chosen=None,
            reason="routing is disabled in routing.json",
        )
    candidates = [
        score_lane(
            lane,
            task_kind,
            usage.get(lane.id),
            now=moment,
            installed=lane.harness in installed,
            excluded_by_caller=bool({lane.id, lane.harness} & exclude_set),
            preferred=bool({lane.id, lane.harness} & prefer_set),
        )
        for lane in settings.lanes
    ]
    order = {lane.id: idx for idx, lane in enumerate(settings.lanes)}
    candidates.sort(key=lambda c: (not c.eligible, -c.score, order[c.lane.id]))
    eligible = [c for c in candidates if c.eligible]
    if not eligible:
        if not settings.lanes:
            reason = "no harness is installed; install one (see `warding route status`)"
        else:
            reason = "every lane is excluded, disabled, resting after a limit, or not installed"
        return Decision(
            kind=task_kind,
            code=DECISION_NO_LANE,
            chosen=None,
            candidates=tuple(candidates),
            reason=reason,
        )
    chosen = eligible[0]
    runner_up = eligible[1] if len(eligible) > 1 else None
    return Decision(
        kind=task_kind,
        code=DECISION_OK,
        chosen=chosen,
        candidates=tuple(candidates),
        reason=_explain(chosen, task_kind, runner_up),
    )
