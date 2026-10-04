"""Idle manager for Mochi — pause the autonomous half when the user is away.

Pauses the queue poller and watchlist service on screen lock / suspend / long
system idle, and resumes (triggering catch-up) when the user comes back.

NOTES
-----

**This module is the state machine only; the plumbing belongs to the owner.** The
pet's shell relays power events and idle readings to the gateway, so the owner
calls :meth:`handle_power_event` for each event and :meth:`check_idle` on its own
~60s cadence (:data:`IDLE_CHECK_INTERVAL_MS` is exported for that loop). There is
no timer wiring here: elsewhere a timer becomes ``tick(now_ms)``, but here the
interval leaves the module entirely, because its body has no time-derived state
at all.

**Lock and suspend share one ``locked`` flag, and the pairs CROSS.**
``suspend`` sets it, but ``unlock-screen`` clears it too (and vice versa for
``lock-screen`` / ``resume``), so an unlock event resumes a suspend-pause.
This is deliberate.

**The auto-resume threshold is a literal 60, not the named constant.** Resume
fires only when paused AND not locked AND idle < 60 seconds — the lock guard
exists because the lock animation itself generates an HID event that would
otherwise instantly un-pause a locked machine. Pause is ``idle >= threshold``
(closed boundary), resume is ``idle < 60`` (open boundary).

**Pause and resume are idempotent by guard, not by accident.** Repeated lock
events call back exactly once; an unlock while never paused calls back never.
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)

# Idle threshold in seconds — pause after 30 minutes of inactivity.
IDLE_THRESHOLD_SECS = 30 * 60

# How often the OWNER should call check_idle.
IDLE_CHECK_INTERVAL_MS = 60_000

# Auto-resume only below this idle level.
_RESUME_IDLE_SECS = 60

# The four power events handled, with their flag effects.
_LOCKING_EVENTS = ("lock-screen", "suspend")
_UNLOCKING_EVENTS = ("unlock-screen", "resume")


class IdleCallbacks(Protocol):
    """Sinks for pause/resume transitions."""

    def on_pause(self) -> None: ...

    def on_resume(self) -> None: ...


class IdleManager:
    """Away-detection state machine: paused/locked flags plus the transitions."""

    def __init__(self, callbacks: IdleCallbacks) -> None:
        self._callbacks = callbacks
        self._paused = False
        # Screen locked or system suspended — the idle check must not
        # auto-resume; only the explicit unlock/resume event may.
        self._locked = False

    # ── Public API ─────────────────────────────────────────────────────────

    @property
    def is_paused(self) -> bool:
        return self._paused

    def handle_power_event(self, event: str) -> None:
        """Feed a power event: lock-screen / unlock-screen / suspend / resume.

        Unknown events are ignored (the owner feeds events in, so anything can
        arrive).
        """
        if event in _LOCKING_EVENTS:
            self._locked = True
            self._pause(event)
        elif event in _UNLOCKING_EVENTS:
            self._locked = False
            self._resume("wake" if event == "resume" else event)

    def check_idle(self, idle_secs: int) -> None:
        """Call every ~60s with the system idle time in seconds."""
        if not self._paused and idle_secs >= IDLE_THRESHOLD_SECS:
            self._pause(f"idle-{idle_secs}s")
        elif self._paused and not self._locked and idle_secs < _RESUME_IDLE_SECS:
            # Only auto-resume from an idle-timeout pause, not from
            # lock/suspend — those require the explicit event.
            self._resume("activity")

    # ── Internal ───────────────────────────────────────────────────────────

    def _pause(self, reason: str) -> None:
        if self._paused:
            return
        self._paused = True
        logger.info("[IdleManager] Paused — %s", reason)
        self._callbacks.on_pause()

    def _resume(self, reason: str) -> None:
        if not self._paused:
            return
        self._paused = False
        logger.info("[IdleManager] Resumed — %s", reason)
        self._callbacks.on_resume()
