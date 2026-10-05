"""Usage ledger: what each lane has done recently, and which lanes are resting.

The router spreads work by *observed* usage, so it needs a record that
survives restarts and is shared by every process that dispatches (the
gateway, ``warding route run``). The ledger is one small JSON file under the
data home, rewritten atomically under an advisory lock. It holds timestamps,
counters and a truncated, credential-redacted last error — never prompts or
keys.

All methods are synchronous file I/O. Call them from async code through
``asyncio.to_thread``.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from junction.harness_router.lanes import MAX_WINDOW_HOURS
from junction.harness_router.limits import LANE_FAILURES, cooldown_seconds

logger = logging.getLogger(__name__)

LEDGER_DIRNAME = "routing"
LEDGER_FILENAME = "ledger.json"
LOCK_FILENAME = "ledger.lock"
LEDGER_SCHEMA_VERSION = 1

# Dispatch timestamps older than the longest window any lane may declare are
# useless for scoring. The count cap bounds the file for a lane that is
# dispatched to in a tight loop.
RETENTION_SECS = MAX_WINDOW_HOURS * 3600
MAX_DISPATCHES_PER_LANE = 4000
# Stored error text is for the operator's eyes in `warding route status`.
LAST_ERROR_MAX_CHARS = 300


@dataclass
class LaneUsage:
    """Recorded state of one lane."""

    dispatches: list[float] = field(default_factory=list)
    ok: int = 0
    failed: int = 0
    limited: int = 0
    kinds: dict[str, int] = field(default_factory=dict)
    cooldown_until: float = 0.0
    cooldown_reason: str = ""
    last_error: str = ""
    last_used: float = 0.0
    # The harness that produced or cleared the cooldown reason. Ordinary task
    # failures leave that reason and its producer together; "" names no harness.
    harness: str = ""

    def count_since(self, since: float) -> int:
        return sum(1 for ts in self.dispatches if ts >= since)

    def cooling(self, now: float) -> bool:
        return self.cooldown_until > now

    def to_dict(self) -> dict[str, Any]:
        return {
            "dispatches": self.dispatches,
            "ok": self.ok,
            "failed": self.failed,
            "limited": self.limited,
            "kinds": self.kinds,
            "cooldown_until": self.cooldown_until,
            "cooldown_reason": self.cooldown_reason,
            "last_error": self.last_error,
            "last_used": self.last_used,
            "harness": self.harness,
        }

    @classmethod
    def from_dict(cls, raw: object) -> "LaneUsage":
        if not isinstance(raw, dict):
            return cls()
        dispatches = [
            float(ts)
            for ts in raw.get("dispatches") or []
            if isinstance(ts, (int, float)) and not isinstance(ts, bool)
        ]
        kinds_raw = raw.get("kinds")
        kinds = (
            {str(k): int(v) for k, v in kinds_raw.items() if isinstance(v, int)}
            if isinstance(kinds_raw, dict)
            else {}
        )
        return cls(
            dispatches=dispatches,
            ok=_nonneg_int(raw.get("ok")),
            failed=_nonneg_int(raw.get("failed")),
            limited=_nonneg_int(raw.get("limited")),
            kinds=kinds,
            cooldown_until=_nonneg_float(raw.get("cooldown_until")),
            cooldown_reason=str(raw.get("cooldown_reason") or ""),
            last_error=str(raw.get("last_error") or ""),
            last_used=_nonneg_float(raw.get("last_used")),
            harness=str(raw.get("harness") or ""),
        )


def _nonneg_int(raw: object) -> int:
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0 else 0


def _nonneg_float(raw: object) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return 0.0
    return max(0.0, float(raw))


def _scrub(text: str) -> str:
    """Credential-redact and truncate error text before it is persisted."""
    if not text:
        return ""
    try:
        from junction.security import redact

        text = redact(text)
    except Exception:
        logger.debug("ledger redaction unavailable", exc_info=True)
    text = " ".join(text.split())
    if len(text) > LAST_ERROR_MAX_CHARS:
        text = text[: LAST_ERROR_MAX_CHARS - 1] + "…"
    return text


class UsageLedger:
    """File-backed per-lane usage record."""

    def __init__(self, directory: Path | None = None) -> None:
        if directory is None:
            from junction.config.paths import data_home

            directory = data_home() / LEDGER_DIRNAME
        self._dir = directory
        self._path = directory / LEDGER_FILENAME
        self._lock_path = directory / LOCK_FILENAME

    @property
    def path(self) -> Path:
        return self._path

    # ── Persistence ──

    @contextmanager
    def _locked(self) -> Iterator[None]:
        from junction.platform_compat import file_lock

        self._dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self._lock_path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            with file_lock(fd, exclusive=True):
                yield
        finally:
            os.close(fd)

    def _read(self) -> dict[str, LaneUsage]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            # A corrupt ledger only costs usage history; routing still works.
            logger.warning("routing ledger unreadable (%s); starting fresh", exc)
            return {}
        lanes = raw.get("lanes") if isinstance(raw, dict) else None
        if not isinstance(lanes, dict):
            return {}
        return {str(k): LaneUsage.from_dict(v) for k, v in lanes.items()}

    def _write(self, state: dict[str, LaneUsage]) -> None:
        from junction.atomic_write import atomic_write

        payload = {
            "version": LEDGER_SCHEMA_VERSION,
            "lanes": {k: v.to_dict() for k, v in sorted(state.items())},
        }
        atomic_write(self._path, json.dumps(payload, separators=(",", ":")), mode=0o600)

    @staticmethod
    def _prune(usage: LaneUsage, now: float) -> None:
        horizon = now - RETENTION_SECS
        kept = [ts for ts in usage.dispatches if ts >= horizon]
        usage.dispatches = kept[-MAX_DISPATCHES_PER_LANE:]

    # ── Reads ──

    def snapshot(self) -> dict[str, LaneUsage]:
        """Current state of every lane the ledger has seen (unlocked read)."""
        return self._read()

    # ── Writes ──

    def record_dispatch(self, lane_id: str, kind: str = "", *, now: float | None = None) -> None:
        """Count one unit of work sent to *lane_id*."""
        moment = time.time() if now is None else now
        with self._locked():
            state = self._read()
            usage = state.setdefault(lane_id, LaneUsage())
            usage.dispatches.append(moment)
            usage.last_used = moment
            if kind:
                usage.kinds[kind] = usage.kinds.get(kind, 0) + 1
            self._prune(usage, moment)
            self._write(state)

    def record_outcome(
        self,
        lane_id: str,
        *,
        ok: bool,
        failure: str = "",
        text: str = "",
        harness: str = "",
        current_harness: str | Callable[[], str] = "",
        now: float | None = None,
    ) -> float:
        """Record how a dispatch ended on *harness*. Returns the lane's cooldown deadline.

        A lane-level *failure* (usage or rate limit, auth, unavailable) rests the
        lane until the reset the error text names, or a class default. A plain
        task failure only increments ``failed``: the task would fail anywhere.

        *current_harness* is the harness the lane runs now, when the caller knows it:
        a name, or a callable that is evaluated once the lock is held. A success from
        any other harness is a run that outlived a reassignment: it counts, but it
        says nothing about the harness the lane runs now, so it must not clear what
        that harness recorded. Asking after the lock is taken means a failure
        recorded under a reassignment cannot slip in between the answer and the write.
        """
        moment = time.time() if now is None else now
        with self._locked():
            state = self._read()
            usage = state.setdefault(lane_id, LaneUsage())
            if ok:
                usage.ok += 1
                current = current_harness() if callable(current_harness) else current_harness
                if not (harness and current and harness != current):
                    usage.harness = harness
                    # Success proves the lane is usable again, whatever it said before.
                    usage.cooldown_until = 0.0
                    usage.cooldown_reason = ""
            else:
                usage.failed += 1
                usage.last_error = _scrub(text)
                if failure in LANE_FAILURES:
                    usage.harness = harness
                    usage.limited += 1
                    rest = cooldown_seconds(failure, text, now=moment)
                    usage.cooldown_until = max(usage.cooldown_until, moment + rest)
                    usage.cooldown_reason = failure
            self._prune(usage, moment)
            self._write(state)
            return usage.cooldown_until

    def set_cooldown(
        self, lane_id: str, seconds: float, reason: str, *, now: float | None = None
    ) -> float:
        moment = time.time() if now is None else now
        with self._locked():
            state = self._read()
            usage = state.setdefault(lane_id, LaneUsage())
            usage.cooldown_until = moment + max(0.0, seconds)
            usage.cooldown_reason = reason if seconds > 0 else ""
            self._write(state)
            return usage.cooldown_until

    def clear_cooldown(self, lane_id: str | None = None) -> list[str]:
        """Lift the cooldown on one lane, or on every lane when *lane_id* is None."""
        cleared: list[str] = []
        with self._locked():
            state = self._read()
            for key, usage in state.items():
                if lane_id is not None and key != lane_id:
                    continue
                if usage.cooldown_until or usage.cooldown_reason:
                    cleared.append(key)
                usage.cooldown_until = 0.0
                usage.cooldown_reason = ""
            self._write(state)
        return cleared
