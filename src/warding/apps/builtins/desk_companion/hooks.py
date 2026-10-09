"""Lifecycle hooks — the companion's runtime follows the app's enabled state.

The gateway's lifecycle dispatcher calls :func:`on_startup` when the app is
enabled (and at gateway boot if it is already enabled) and :func:`on_shutdown`
when it is disabled or the gateway stops. Both are idempotent, because a
re-enable calls startup again on a process that never restarted.

There is nothing to launch (an ``onEnable`` script that fails rolls an enable
BACK), and therefore nothing to fail: the state the user toggles and the state the
runtime follows are the same state.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from warding.apps.builtins.desk_companion.appearances import AppearanceStore
from warding.apps.builtins.desk_companion.store import CompanionStore

logger = logging.getLogger(__name__)

#: Process-wide runtime. A module global rather than something hung off ``ctx``
#: because the routes need to reach the same instance, and the dispatcher hands
#: each hook its own context object.
_store: CompanionStore | None = None
_appearances: AppearanceStore | None = None


def get_appearances() -> AppearanceStore:
    """The appearance store.

    Unlike the reminder store this is created eagerly on first use rather than by the
    startup hook: listing packs is a pure read of a directory, so there is nothing to
    schedule and nothing to tear down — and a gallery that works before the first tick
    is one less ordering dependency.
    """
    if _appearances is None:
        raise RuntimeError("desk-companion: appearance store not initialised")
    return _appearances


def get_store() -> CompanionStore | None:
    """The live runtime, or None when the app is disabled or not yet started.

    Routes use this to answer 503 rather than 500 while the hook has not run —
    "not started yet" and "broken" are different answers and the caller can
    retry only one of them.
    """
    return _store


async def on_startup(ctx: Any) -> None:
    """Load persisted state and start ticking. Idempotent.

    Async because loading touches the disk: awaited off the event loop so
    enabling the app never blocks the gateway on file I/O.
    """
    global _store, _appearances

    data_dir = Path(ctx.data_dir)

    # Before the early return below: shutdown clears this, so a disable-then-enable
    # cycle would otherwise leave the gallery with no store and every appearance
    # request raising. It holds no timer, so rebuilding it is free.
    if _appearances is None:
        appearances = AppearanceStore(data_dir)
        await asyncio.to_thread(appearances.load)
        _appearances = appearances

    if _store is not None:
        # Re-enable after a disable: the same instance resumes rather than
        # building a second one that would double-fire every reminder.
        _store.start()
        return

    """
    Push a fire the moment it is queued, instead of waiting out the overlay's poll.

    The store is in the gateway and the overlay polls over HTTP, which adds up to
    the poll interval on top of the tick — without a push the reminder would be late
    by seconds, and it would show.

    `ctx.events` is the gateway's app event bus, present only when the manifest
    declares the event under `permissions.events`. When it is absent the poll is
    the only path: slower, never broken.
    """
    bus = getattr(ctx, "events", None)

    def announce_fire() -> None:
        if bus is None:
            return
        # No payload: this is a doorbell, not the delivery. The overlay drains
        # /pending itself, which keeps ONE ordering authority (the cursor) instead of
        # a pushed copy that could arrive out of order or duplicate what it polls.
        bus.publish("desk-companion:fire")

    store = CompanionStore(data_dir, on_fire=announce_fire)
    await asyncio.to_thread(store.load)
    store.start()
    _store = store
    logger.info("desk-companion: runtime started (data dir %s)", data_dir)


async def on_shutdown(ctx: Any) -> None:  # noqa: ARG001 — ctx unused, kept for the ABI
    """Stop ticking and flush state to disk. Idempotent.

    The instance is deliberately KEPT rather than dropped, so a disable followed
    by an enable resumes with the accumulated stats and the in-flight break
    schedule instead of starting from zero.
    """
    if _store is not None:
        await asyncio.to_thread(_store.stop)
        logger.info("desk-companion: runtime stopped")


def _reset_for_tests() -> None:
    """Drop the process-global runtime. Tests only."""
    global _store, _appearances
    if _store is not None:
        _store.stop()
    _store = None
    # The appearance store holds no timer, so there is nothing to stop — but it is
    # cleared so a re-enable rebuilds it against the data dir it is given then.
    _appearances = None
