"""Profile resolution — decides which edition loads at boot.

The profile is a *load trigger*, not a security decision: capability comes from
the installed companion package, not from the profile claim.  A forged signal at
worst loads a stricter posture on a host that has nothing to enforce it.

Precedence (first match wins):
  1. ``WARDING_PROFILE`` env var (explicit operator/dev override).
  2. A non-empty ``warding.plugins`` entry-point group (companion installed) —
     the cheap, authoritative signal: capability comes from the installed
     companion, so its presence is what actually matters.
  3. Identity signal: a present SSO-marker path (``WARDING_SSO_MARKER_PATH``),
     but ONLY when the opt-in ``WARDING_SSO_PROFILE_PROBE`` env var is truthy.  A cheap filesystem stat (no
     subprocess) that flags an enterprise host which has NOT installed the
     companion, so discovery fails closed instead of running open defaults.  The
     probe is OFF by default so the public open-source edition is never forced
     into the enterprise profile by a stray marker directory left behind by some
     other tool (which would otherwise brick every command at boot — there is no
     companion to compose, so discovery raises).  A companion's managed launcher
     sets the probe env var to ``1`` to re-enable the fail-closed identity
     heuristic on hosts where it is meaningful.
  4. Otherwise ``standalone``.

Note: the core does NOT spawn a subprocess to read the SSO issuer — that added a
blocking subprocess to every standalone boot and baked an edition-specific string
into the open-source core.  Entry-point presence + the opt-in marker stat cover
the trigger cases; the companion's own identity provider refines the principal
once loaded.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from warding.constants import env_flag_enabled
from warding.platform.context import PROFILE_ENTERPRISE, PROFILE_STANDALONE

if TYPE_CHECKING:
    from warding.config.loader import WardingConfig

logger = logging.getLogger(__name__)

_VALID_PROFILES = frozenset({PROFILE_STANDALONE, PROFILE_ENTERPRISE})

# Opt-in gate for the SSO-marker identity heuristic (precedence step 3).  Off by
# default so a stray marker directory cannot force the public edition into the
# enterprise profile (which has no companion to compose and would fail-closed at
# boot).  A companion's managed launcher sets this truthy.

_SSO_PROBE_ENV = "WARDING_SSO_PROFILE_PROBE"

# Env var naming the path stat'd for the identity heuristic when the probe is
# opted in, so a companion can point it at its own SSO marker.  With no path
# configured the probe has nothing to check.
_SSO_MARKER_ENV = "WARDING_SSO_MARKER_PATH"


def resolve_profile(cfg: "WardingConfig", *, entry_points: "Sequence[object]") -> str:
    """Resolve the active profile.  See module docstring for precedence."""
    # 1. Explicit env override.
    env = os.environ.get("WARDING_PROFILE", "").strip().lower()
    if env in _VALID_PROFILES:
        return env
    if env:
        logger.warning("Unknown WARDING_PROFILE=%r; falling back to standalone", env)
        return PROFILE_STANDALONE

    # 2. Companion installed (cheap, authoritative — no subprocess, no marker).
    if entry_points:
        return PROFILE_ENTERPRISE

    # 3. Identity signal — a cheap marker stat (no subprocess), gated behind an
    #    explicit opt-in so the public edition is never forced into the
    #    enterprise profile by a leftover marker.  Flags an enterprise host
    #    without the companion so discovery fails closed.
    marker = os.environ.get(_SSO_MARKER_ENV, "").strip()
    if marker and env_flag_enabled(_SSO_PROBE_ENV):
        try:
            if Path(marker).exists():
                return PROFILE_ENTERPRISE
        except Exception:
            logger.debug("SSO-marker probe failed", exc_info=True)

    # 4. Default.
    return PROFILE_STANDALONE
