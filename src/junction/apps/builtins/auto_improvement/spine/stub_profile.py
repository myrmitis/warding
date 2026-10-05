"""Re-export shim for :class:`StubProfile` — the no-op profile behind ``--dry-run``.

The class itself lives in :mod:`.profile` next to the Target Profile protocols it
implements, but ``driver._run_dry`` imports it from ``.stub_profile``. Without this
shim that import raises ImportError and ``--dry-run`` dies on entry.

Kept as a shim rather than moving the class: ``StubProfile`` shares the contract wiring
with the real profile, and splitting it out would either duplicate that or invert the
dependency.
"""

from __future__ import annotations

from .profile import StubProfile

__all__ = ["StubProfile"]
