"""The auto-improvement SPINE — the target-agnostic engine.

The fixed engine that ships once and never changes per target: driver, proposer,
gate, measurer, keeper, ledger, plus the results archive. Every target-specific
touchpoint is a NAMED extension point on :class:`~.contracts.TargetProfile`, never
a hard-coded value — so a grep of this package finds no target-environment tokens
(build tools, the model provider, config flags, or any target-specific path).

Public surface:
  - :class:`profile.TargetProfile` and the six profile fields (the target seam);
    re-exported from :mod:`contracts`.
  - :class:`driver.Driver` / :func:`driver.main` (the durable while-loop; ``--dry-run``).
  - :class:`proposer.Proposer`, :class:`gate.Gate`, :class:`measurer.Measurer`,
    :class:`keeper.Keeper` (the per-cycle phases B–E).
  - :class:`ledger.Ledger` (content-fingerprint dedup).
  - :class:`archive.Archive` (the ``results/`` population store).
  - :class:`stub_profile.StubProfile` (the no-op profile that drives ``--dry-run``).
"""

from __future__ import annotations

from . import pr_description
from .archive import Archive
from .bug_gate import BugGate
from .contracts import (
    BUG_ERROR,
    BUG_FAILED_BUILD,
    BUG_FAILED_LINT,
    BUG_FILED,
    BUG_NOT_GREEN,
    BUG_NOT_RED,
    BUG_REGRESSED,
    BUG_TEST_FLAKY,
    BUG_TEST_INVALID,
    TRACK_BUG,
    TRACK_PERF,
    BugGateResult,
    BugReproducingTest,
    Candidate,
    DiscoveryResult,
    GateResult,
    Measurement,
    Proposal,
    StageBreakdown,
    Verdict,
)
from .cost import CostMeter, TokenRates
from .driver import BudgetCaps, Driver, PushEnabledError, Stats
from .gate import Gate
from .keeper import KEPT, Keeper
from .ledger import STATUS_DUPLICATE, Ledger, LedgerEntry, fingerprint, map_bug_reason_to_status
from .measurer import Measurer, SameShaError
from .pollute import PolluteResult, run_do_not_pollute
from .pr_pipeline import PrOutcome, PrPipeline
from .preflight import (
    CalibrationError,
    HostPollutionError,
    PreflightResult,
    RulerNotTrustedError,
    calibrate_and_prove,
    compute_noise_band,
)

# The Target Profile seam is defined in .profile and is the canonical
# import home; .contracts re-exports it for back-compat (see contracts module docstring).
from .profile import (
    BugRunner,
    BuildGate,
    CalibrationParams,
    EditAllowlist,
    IsolationRecipe,
    PRRecipe,
    Ruler,
    StubProfile,
    TargetProfile,
)
from .proposer import Proposer

__all__ = [
    # contracts / seam
    "TargetProfile",
    "Ruler",
    "BuildGate",
    "BugRunner",
    "EditAllowlist",
    "IsolationRecipe",
    "PRRecipe",
    "CalibrationParams",
    "StubProfile",
    "Candidate",
    "BugReproducingTest",
    "DiscoveryResult",
    "Proposal",
    "GateResult",
    "BugGateResult",
    "Measurement",
    "StageBreakdown",
    "Verdict",
    "TRACK_PERF",
    "TRACK_BUG",
    # bug-track gate reasons (mapped to ledger statuses by the driver)
    "BUG_FILED",
    "BUG_FAILED_BUILD",
    "BUG_FAILED_LINT",
    "BUG_TEST_INVALID",
    "BUG_NOT_RED",
    "BUG_TEST_FLAKY",
    "BUG_NOT_GREEN",
    "BUG_REGRESSED",
    "BUG_ERROR",
    # engine
    "Driver",
    "BudgetCaps",
    "Stats",
    "PushEnabledError",
    "Proposer",
    "Gate",
    "BugGate",
    "Measurer",
    "SameShaError",
    "Keeper",
    "KEPT",
    "Ledger",
    "LedgerEntry",
    "fingerprint",
    "map_bug_reason_to_status",
    "STATUS_DUPLICATE",
    "Archive",
    # Phase-1 pre-flight trust gate + do-not-pollute + cost meter
    "PreflightResult",
    "calibrate_and_prove",
    "compute_noise_band",
    "RulerNotTrustedError",
    "HostPollutionError",
    "CalibrationError",
    "PolluteResult",
    "run_do_not_pollute",
    "CostMeter",
    "TokenRates",
    # PR emission pipeline (verify → REPRODUCE → draft PR → ledger)
    "PrPipeline",
    "PrOutcome",
    "pr_description",
]
