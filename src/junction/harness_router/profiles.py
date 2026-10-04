"""The built-in profile of every dockable harness.

A *profile* is what the router assumes about a harness before the operator says
anything: which kinds of work it is good at (affinity, 0..1) and how it is paid
for (billing). Both are defaults. ``routing.json`` overrides either per lane.

Affinities are a starting point, not a benchmark. They encode the common
operator experience (Claude Code for planning and review, Codex for
implementation and debugging, Cursor for fast edits, Grok for research, an
OpenCode lane on OpenRouter for bulk and overflow) and exist so a fresh install
routes sensibly with zero configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from junction.acp.types import (
    ACP_BACKEND_CLAUDE,
    ACP_BACKEND_CODEX,
    ACP_BACKEND_CURSOR,
    ACP_BACKEND_DROID,
    ACP_BACKEND_DSH,
    ACP_BACKEND_GOOSE,
    ACP_BACKEND_GROK,
    ACP_BACKEND_KIMI,
    ACP_BACKEND_KIRO_NAME,
    ACP_BACKEND_OPENCODE,
    ACP_BACKEND_PI,
)

# ── Billing ──
# ``subscription``: flat-rate plan with a usage window. Unused quota is lost at
#   reset, so the router spends it first.
# ``free``: no marginal cost (free-tier models). Treated like a subscription.
# ``metered``: pay per token (OpenRouter, raw API keys). Last resort unless its
#   affinity for the kind clearly wins.
BILLING_SUBSCRIPTION = "subscription"
BILLING_FREE = "free"
BILLING_METERED = "metered"
BILLING_TYPES: tuple[str, ...] = (BILLING_SUBSCRIPTION, BILLING_FREE, BILLING_METERED)

# Neutral affinity for a harness with no opinionated profile.
NEUTRAL_AFFINITY = 0.7


@dataclass(frozen=True)
class HarnessProfile:
    """Default assumptions about one harness."""

    harness: str
    label: str
    billing: str
    affinity: Mapping[str, float] = field(default_factory=dict)
    note: str = ""

    def affinity_for(self, kind: str) -> float:
        return float(self.affinity.get(kind, NEUTRAL_AFFINITY))


def _aff(**values: float) -> Mapping[str, float]:
    return MappingProxyType(dict(values))


# Keyed by the operator-facing harness name (``kiro`` rather than the empty
# backend string) so routing.json and the CLI read naturally.
HARNESS_PROFILES: Mapping[str, HarnessProfile] = MappingProxyType(
    {
        ACP_BACKEND_CLAUDE: HarnessProfile(
            harness=ACP_BACKEND_CLAUDE,
            label="Claude Code",
            billing=BILLING_SUBSCRIPTION,
            affinity=_aff(
                plan=1.0,
                review=0.95,
                docs=0.95,
                implement=0.9,
                debug=0.9,
                test=0.85,
                research=0.6,
                quick=0.6,
                bulk=0.5,
            ),
            note="Claude Pro / Max plan through Claude Code.",
        ),
        ACP_BACKEND_CODEX: HarnessProfile(
            harness=ACP_BACKEND_CODEX,
            label="Codex (ChatGPT)",
            billing=BILLING_SUBSCRIPTION,
            affinity=_aff(
                implement=0.95,
                debug=0.95,
                test=0.9,
                review=0.9,
                plan=0.85,
                docs=0.7,
                quick=0.7,
                bulk=0.7,
                research=0.6,
            ),
            note="ChatGPT Plus / Pro plan through the Codex CLI.",
        ),
        ACP_BACKEND_CURSOR: HarnessProfile(
            harness=ACP_BACKEND_CURSOR,
            label="Cursor Agent",
            billing=BILLING_SUBSCRIPTION,
            affinity=_aff(
                quick=0.95,
                implement=0.85,
                bulk=0.8,
                debug=0.8,
                test=0.8,
                review=0.7,
                plan=0.7,
                docs=0.7,
                research=0.5,
            ),
            note="Cursor plan through the cursor-agent CLI.",
        ),
        ACP_BACKEND_GROK: HarnessProfile(
            harness=ACP_BACKEND_GROK,
            label="Grok Build",
            billing=BILLING_SUBSCRIPTION,
            affinity=_aff(
                research=1.0,
                quick=0.85,
                plan=0.75,
                debug=0.75,
                implement=0.75,
                bulk=0.75,
                review=0.7,
                docs=0.7,
                test=0.7,
            ),
            note="SuperGrok / X Premium plan through the grok CLI.",
        ),
        ACP_BACKEND_OPENCODE: HarnessProfile(
            harness=ACP_BACKEND_OPENCODE,
            label="OpenCode",
            billing=BILLING_METERED,
            affinity=_aff(
                bulk=0.9,
                quick=0.8,
                implement=0.75,
                test=0.75,
                docs=0.75,
                debug=0.7,
                review=0.65,
                plan=0.65,
                research=0.6,
            ),
            note="Any provider OpenCode is logged into; OpenRouter is pay per token.",
        ),
        ACP_BACKEND_KIMI: HarnessProfile(
            harness=ACP_BACKEND_KIMI, label="Kimi Code", billing=BILLING_SUBSCRIPTION
        ),
        ACP_BACKEND_DSH: HarnessProfile(
            harness=ACP_BACKEND_DSH, label="DeepSeek Harness", billing=BILLING_METERED
        ),
        ACP_BACKEND_GOOSE: HarnessProfile(
            harness=ACP_BACKEND_GOOSE, label="Goose", billing=BILLING_METERED
        ),
        ACP_BACKEND_PI: HarnessProfile(
            harness=ACP_BACKEND_PI,
            label="Pi",
            billing=BILLING_METERED,
        ),
        ACP_BACKEND_DROID: HarnessProfile(
            harness=ACP_BACKEND_DROID, label="Factory Droid", billing=BILLING_SUBSCRIPTION
        ),
        ACP_BACKEND_KIRO_NAME: HarnessProfile(
            harness=ACP_BACKEND_KIRO_NAME, label="Kiro CLI", billing=BILLING_SUBSCRIPTION
        ),
    }
)


def profile_for(harness: str) -> HarnessProfile:
    """Profile for *harness*, or a neutral subscription profile when unknown."""
    found = HARNESS_PROFILES.get(harness)
    if found is not None:
        return found
    return HarnessProfile(harness=harness, label=harness, billing=BILLING_SUBSCRIPTION)
