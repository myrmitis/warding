"""Test utilities for Junction consumers.

Everything under ``junction.testing`` is intended for downstream test
suites that want to exercise code against a populated ``$JUNCTION_HOME``
without hand-rolling setup. The module is in the runtime wheel (not
``dev_requirements``) so third-party packages can ``pip install junction``
and use it immediately.

Public entry points:

- :mod:`junction.testing.fixtures` — ``seeded_home`` plain context manager
  and ``seeded_home_fixture`` pytest fixture for setting up an isolated
  ``$JUNCTION_HOME`` from a named fixture.
- :mod:`junction.testing.harness` — ``spawn_feature_gateway`` context
  manager that spins up an isolated, headless gateway from the workspace
  source tree (compose with ``--test-mode`` / ``--json-ready``); yields a
  ``GatewayHandle`` with the dashboard URL and tears down on exit.
- :mod:`junction.testing.channel_fixtures` — vendor-API fixtures carrying
  provenance (``live_probe`` / ``vendor_doc`` / ``assumed``), plus
  ``shape_of`` / ``assert_same_shape`` for comparing a live response against
  a recorded one by key/type skeleton. Import it directly; the fixtures root
  is always caller-supplied.
- :mod:`junction.testing.fake_channel_wire` — ``FakeWireSession`` /
  ``FakeWireWebSocket``, drop-in stand-ins for the ``aiohttp`` session a
  messaging-channel client owns. Assign one onto ``client._session`` and the
  real client, transport, dispatcher, pipeline and renderer all run against
  pinned vendor request/response shapes with no credentials or network.

Import submodules directly (``from junction.testing.fixtures import ...``,
``from junction.testing.harness import ...``); no top-level re-exports,
so the package namespace stays pytest-free for non-pytest consumers.
"""

# Bind submodules onto the package namespace so ``unittest.mock.patch``
# can traverse paths like ``junction.testing.harness.TERMINATE_GRACE_SECONDS``
# (patch walks dotted paths via getattr; without these binds the lookup
# fails even though the modules are in sys.modules). Both submodules are
# pytest-free at import time, so this doesn't pull pytest into consumers
# that only need the runtime helpers.
from junction.testing import fake_channel_wire, fixtures, harness  # noqa: E402,F401
