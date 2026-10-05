"""Classify a harness failure and estimate when its lane is usable again.

Subscription harnesses report exhaustion as text: Claude Code's "5-hour limit
reached · resets 3pm", Codex's "You've hit your usage limit … try again in 2
hours 5 minutes", OpenRouter's "Insufficient credits". The router needs two
facts from that text: *which* failure it was, and *how long* to rest the lane.
Everything here is pure (no I/O) so it is cheap to call on any error path.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta

# ── Failure classes ──
FAILURE_USAGE_LIMIT = "usage_limit"  # plan quota spent until a reset
FAILURE_RATE_LIMIT = "rate_limit"  # short throttle (429, overloaded)
FAILURE_AUTH = "auth"  # harness not logged in / key rejected
FAILURE_UNAVAILABLE = "unavailable"  # harness binary missing or would not start
FAILURE_OTHER = "other"  # ordinary task failure; not the lane's fault

# Classes that say the LANE is unusable right now, so work should move to
# another lane. An ordinary task failure would fail on any lane.
LANE_FAILURES: frozenset[str] = frozenset(
    {FAILURE_USAGE_LIMIT, FAILURE_RATE_LIMIT, FAILURE_AUTH, FAILURE_UNAVAILABLE}
)

# ── Cooldowns (seconds) when the text names no reset time ──
# A usage limit with no stated reset is re-probed after an hour rather than
# waiting out a guessed 5-hour window: an early probe costs one failed
# dispatch, a late one wastes quota that was already back.
DEFAULT_COOLDOWN_SECS: dict[str, float] = {
    FAILURE_USAGE_LIMIT: 60 * 60,
    FAILURE_RATE_LIMIT: 2 * 60,
    FAILURE_AUTH: 30 * 60,
    FAILURE_UNAVAILABLE: 10 * 60,
}
# Weekly plan limits are the longest reset any harness states.
MAX_COOLDOWN_SECS = 8 * 24 * 60 * 60
MIN_COOLDOWN_SECS = 30

_USAGE_LIMIT_RE = re.compile(
    r"usage limit|usage cap|hit your (?:\w+ )?limit|reached your (?:\w+ )?limit"
    r"|(?:usage|plan|session|message|request|credit)s? limit (?:has been |was )?reached"
    r"|(?:5|five)[- ]hour limit|weekly limit|daily limit|monthly limit"
    r"|quota (?:exceeded|exhausted)|exceeded your current quota|free-models-per-day"
    r"|insufficient (?:credits|quota|balance)|out of credits|credit balance is too low"
    r"|upgrade to (?:pro|plus|max)\b|MonthlyLimitError|FreeTierLimitExceeded"
    r"|ServiceQuotaExceededException",
    re.IGNORECASE,
)
_RATE_LIMIT_RE = re.compile(
    r"rate.?limit|too many requests|(?:status|code|error|http)\W{0,3}(?:429|529)\b"
    r"|throttl|overloaded|TooManyRequestsException|ThrottlingException"
    r"|capacity (?:exceeded|constraints)",
    re.IGNORECASE,
)
_AUTH_RE = re.compile(
    r"not logged in|log ?in required|please (?:log|sign) ?in|authentication (?:required|failed)"
    r"|auth(?:entication)?_required|unauthori[sz]ed|(?:status|code|error|http)\W{0,3}401\b"
    r"|invalid api key|api key (?:is )?(?:missing|invalid|not set)|no api key|login expired"
    r"|run `?[a-z][\w-]* (?:auth )?login|run /login\b",
    re.IGNORECASE,
)
_UNAVAILABLE_RE = re.compile(
    r"is not installed|No ACP runtime found|failed to spawn|Unknown ACP runtime"
    r"|not found\. Install it with",
    re.IGNORECASE,
)

# "in 2 hours 5 minutes", "in 3h 20m", "after 30 seconds", "in 45 min".
# Longest spellings first and a word boundary after the unit, so "hours" is
# never read as "h" followed by junk that ends the repetition early.
_UNIT = r"(?:days?|d|hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b"
_DURATION_PART_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(" + _UNIT + ")", re.IGNORECASE)
_RELATIVE_RE = re.compile(
    r"(?:in|after|wait|retry[- ]after:?)\s+((?:\d+(?:\.\d+)?\s*" + _UNIT + r"[\s,]*(?:and\s+)?)+)",
    re.IGNORECASE,
)
# "resets 3pm", "resets at 5:00 PM", "try again at 15:05"
_CLOCK_RE = re.compile(
    r"(?:resets?|try again|available again|retry)\s+(?:at\s+)?"
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
    re.IGNORECASE,
)
# Claude Code's legacy "usage limit reached|1727300000" epoch suffix.
_EPOCH_RE = re.compile(r"\|\s*(\d{10})\b")

_UNIT_SECS = {"d": 86400, "h": 3600, "m": 60, "s": 1}


def classify_failure(text: str) -> str:
    """Map failure *text* onto one of the ``FAILURE_*`` classes."""
    if not text:
        return FAILURE_OTHER
    # Usage limit before rate limit: "usage limit … 429" is a spent quota, and
    # resting it for two minutes would burn a dispatch every two minutes.
    if _USAGE_LIMIT_RE.search(text):
        return FAILURE_USAGE_LIMIT
    if _RATE_LIMIT_RE.search(text):
        return FAILURE_RATE_LIMIT
    if _AUTH_RE.search(text):
        return FAILURE_AUTH
    if _UNAVAILABLE_RE.search(text):
        return FAILURE_UNAVAILABLE
    return FAILURE_OTHER


def classify_exception(exc: BaseException) -> str:
    """Classify an exception from a harness turn.

    ``AcpAuthRequired`` and ``AcpTurnStalled`` are recognised by class name so
    this module stays import-light, and a ``FileNotFoundError`` means the harness
    binary is missing; everything else is classified from its message. A stalled
    turn is a harness that went silent while retrying its model provider, which
    in practice is a rate limit it never reported.
    """
    failure = getattr(exc, "failure", "")
    if isinstance(failure, str) and failure in LANE_FAILURES:
        return failure
    if type(exc).__name__ == "AcpAuthRequired":
        return FAILURE_AUTH
    if type(exc).__name__ == "AcpTurnStalled":
        return FAILURE_RATE_LIMIT
    if isinstance(exc, FileNotFoundError):
        # The harness executable itself is missing at spawn.
        return FAILURE_UNAVAILABLE
    return classify_failure(str(exc) or type(exc).__name__)


def _parse_relative(text: str) -> float | None:
    match = _RELATIVE_RE.search(text)
    if not match:
        return None
    total = 0.0
    for amount, unit in _DURATION_PART_RE.findall(match.group(1)):
        total += float(amount) * _UNIT_SECS[unit[0].lower()]
    return total or None


def _parse_clock(text: str, now: float) -> float | None:
    match = _CLOCK_RE.search(text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = (match.group(3) or "").lower()
    if meridiem and not match.group(2) and hour > 12:
        return None
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    if not meridiem and not match.group(2):
        # A bare "resets 3" is too ambiguous to trust.
        return None
    current = datetime.fromtimestamp(now)
    target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= current:
        target += timedelta(days=1)
    return target.timestamp() - now


def _parse_epoch(text: str, now: float) -> float | None:
    match = _EPOCH_RE.search(text)
    if not match:
        return None
    delta = float(match.group(1)) - now
    return delta if delta > 0 else None


def parse_reset_seconds(text: str, *, now: float | None = None) -> float | None:
    """Seconds until the limit named in *text* resets, or ``None`` if unstated.

    Clock times ("resets 3pm") are read in the host's local time zone, which is
    the zone the harness CLI printed them in.
    """
    if not text:
        return None
    moment = time.time() if now is None else now
    for parser in (_parse_epoch, _parse_clock):
        found = parser(text, moment)
        if found is not None:
            return found
    return _parse_relative(text)


def cooldown_seconds(failure: str, text: str = "", *, now: float | None = None) -> float:
    """How long to rest a lane after *failure*. Zero for an ordinary failure."""
    if failure not in LANE_FAILURES:
        return 0.0
    stated = parse_reset_seconds(text, now=now)
    seconds = stated if stated is not None else DEFAULT_COOLDOWN_SECS[failure]
    return max(MIN_COOLDOWN_SECS, min(MAX_COOLDOWN_SECS, seconds))


# Short replies can be legitimate answers about login or quota. Only a
# recognizable notice at the start of the whole reply can rest a lane; the
# broader exception classifier is deliberately not used on successful output.
LIMIT_NOTICE_MAX_CHARS = 400
_NOTICE_BOUNDARY = r"(?=$|\s*[.!:;|·∙\n]|\s+(?:resets?|try again)\b)"
_USAGE_NOTICE_RE = re.compile(
    r"(?:you(?:['’]ve| have) (?:hit|reached) your (?:(?:daily|weekly|monthly) )?"
    r"(?:(?:usage|plan|session|message|request|credit) )?limit"
    r"|(?:claude(?: ai)? )?(?:usage|plan|session|message|request|credit)s? limit "
    r"(?:has been |was )?reached"
    r"|(?:(?:5|five)[- ]hour|weekly|daily|monthly) limit (?:reached|exceeded)"
    r"|quota (?:exceeded|exhausted)|you exceeded your current quota"
    r"|insufficient (?:credits|quota|balance)|out of credits|credit balance is too low)"
    + _NOTICE_BOUNDARY,
    re.IGNORECASE,
)
_AUTH_NOTICE_RE = re.compile(
    r"(?:(?:not logged in|log ?in required|authentication (?:required|failed)"
    r"|auth(?:entication)?_required|unauthori[sz]ed|invalid api key"
    r"|api key (?:is )?(?:missing|invalid|not set)|no api key|login expired)"
    + _NOTICE_BOUNDARY
    + r"|please run /login(?: first)?[.!]?\Z)",
    re.IGNORECASE,
)


class HarnessLaneFailure(RuntimeError):
    """A turn ended normally but its reply was the harness's own limit notice."""

    def __init__(self, failure: str, notice: str) -> None:
        super().__init__(f"{failure}: {notice.strip()}")
        self.failure = failure
        self.notice = notice


def limit_notice_failure(reply: str) -> str:
    """Failure class when *reply* is a plan-limit or login notice, else ``""``.

    Some harnesses end a turn with ``end_turn`` and put "You've hit your usage
    limit" in the message instead of returning a JSON-RPC error. Callers apply
    this only to a turn that ran no tools. A short answer about login or quota
    is not itself evidence that the harness failed.
    """
    text = (reply or "").strip()
    if not text or len(text) > LIMIT_NOTICE_MAX_CHARS:
        return ""
    if _USAGE_NOTICE_RE.match(text):
        return FAILURE_USAGE_LIMIT
    if _AUTH_NOTICE_RE.match(text):
        return FAILURE_AUTH
    return ""
