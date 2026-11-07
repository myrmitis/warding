"""E2E smoke tests using ``spawn_feature_gateway`` harness.

Phase 5 of the Warding Testing & Release Plan. These tests spawn a real
gateway subprocess, hit its HTTP endpoints with the token from the READY
line, and verify core functionality works end-to-end.

Gated behind ``WARDING_E2E=1`` because they spawn a real gateway process
(5-15s startup). CI runs them on a shared test fleet; local devs opt in.

Requires: ``warding.testing.harness`` and composable
CLI flags.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import pytest

# Gate all tests behind WARDING_E2E so they don't slow down local pytest runs.
pytestmark = pytest.mark.skipif(
    not os.environ.get("WARDING_E2E"),
    reason="E2E smoke tests. Set WARDING_E2E=1 to run.",
)


@pytest.fixture(scope="module")
def gateway():
    """Spawn one gateway for all smoke tests (amortize 5-15s startup).

    No state cleanup between tests; each test must be tolerant of
    prior-test side effects, or use a fresh per-test gateway.
    """
    from warding.testing import fake_acp_backend
    from warding.testing.harness import spawn_feature_gateway

    previous = os.environ.get("WARDING_KIRO_BIN")
    os.environ["WARDING_KIRO_BIN"] = str(fake_acp_backend.__file__)
    try:
        with spawn_feature_gateway(fixture="minimal", approval="reads") as handle:
            yield handle
    finally:
        if previous is None:
            os.environ.pop("WARDING_KIRO_BIN", None)
        else:
            os.environ["WARDING_KIRO_BIN"] = previous


_openers: dict[int, urllib.request.OpenerDirector] = {}


def _opener(gateway) -> urllib.request.OpenerDirector:
    """Return a cookie-jar opener primed with the durable session cookie.

    The harness hands us a one-time *link* token. Re-presenting it as a
    ``?token=`` query param on every request works for normal routes, but
    ``mixed_internal`` routes (/api/crons, /api/lessons, /api/chat/slots,
    /api/artifacts) validate the query token against the revoked-nonce
    denylist and 403 once the link nonce is revoked after first use. So mint
    the durable ``mc_token_<port>`` session cookie once via a normal-path GET
    (which carries the link token and Set-Cookies the session), then send
    that cookie on every later request with no ``?token=`` -- the minted
    session token has a fresh, non-revoked nonce so mixed_internal writes
    pass.
    """
    opener = _openers.get(gateway.port)
    if opener is None:
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        prime = urllib.request.Request(
            f"http://localhost:{gateway.port}/api/status?token={gateway.token}"
        )
        with opener.open(prime, timeout=10):
            pass
        _openers[gateway.port] = opener
    return opener


def _api_get(gateway, path: str) -> dict:
    """GET an API endpoint via the session cookie, return parsed JSON."""
    req = urllib.request.Request(f"http://localhost:{gateway.port}{path}")
    with _opener(gateway).open(req, timeout=10) as resp:
        return json.loads(resp.read())


def _api_post(gateway, path: str, body: dict) -> dict:
    """POST to an API endpoint via the session cookie, return parsed JSON."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"http://localhost:{gateway.port}{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with _opener(gateway).open(req, timeout=30) as resp:
        return json.loads(resp.read())


# --- Smoke tests ---


def test_health_check(gateway):
    """Gateway responds to /api/status with uptime and version."""
    data = _api_get(gateway, "/api/status")
    assert "uptime" in data
    assert "version" in data


def test_sessions_list(gateway):
    """Gateway lists sessions (minimal fixture ships one starter session)."""
    data = _api_get(gateway, "/api/sessions")
    assert "sessions" in data
    # minimal fixture ships dashboard_starter.jsonl
    assert data["total"] >= 1


def test_create_chat_slot(gateway):
    """Can create a new chat slot via the API."""
    data = _api_post(gateway, "/api/chat/slots", {})
    assert "key" in data
    slot_key = data["key"]
    assert slot_key  # non-empty string


def test_cron_list_fixture_crons(gateway):
    """Cron list returns the fixture's crons (minimal has 2: active + paused)."""
    data = _api_get(gateway, "/api/crons")
    assert "jobs" in data
    # minimal fixture ships 2 crons
    assert len(data["jobs"]) >= 2


def test_memory_workspace_exists(gateway):
    """Memory workspace directory exists in the seeded home."""
    workspace_dir = gateway.home / "workspace" / "memory"
    assert workspace_dir.is_dir()
    assert (workspace_dir / "preferences.md").is_file()


# --- API round-trip tests ---


def _api_delete(gateway, path: str) -> dict:
    """DELETE an API endpoint via the session cookie, return parsed JSON."""
    req = urllib.request.Request(f"http://localhost:{gateway.port}{path}", method="DELETE")
    with _opener(gateway).open(req, timeout=10) as resp:
        return json.loads(resp.read())


def _api_post_with_session(
    gateway, path: str, body: dict, session_key: str = "dashboard:ui"
) -> dict:
    """POST via the session cookie + X-Session-Key header."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"http://localhost:{gateway.port}{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Session-Key", session_key)
    with _opener(gateway).open(req, timeout=30) as resp:
        return json.loads(resp.read())


def test_cron_create_and_delete(gateway):
    """Can create a cron job via API and then delete it."""
    body = {"name": "e2e-test-cron", "every": 3600, "message": "hello from e2e"}
    data = _api_post(gateway, "/api/crons", body)
    assert "id" in data
    job_id = data["id"]
    assert job_id

    try:
        # Verify it appears in the list
        crons = _api_get(gateway, "/api/crons")
        assert any(j["id"] == job_id for j in crons["jobs"])
    finally:
        _api_delete(gateway, f"/api/crons/{job_id}")


def test_lessons_create_and_list(gateway):
    """Can create a lesson and see it in the list."""
    body = {"rule": "e2e test lesson", "category": "knowledge"}
    _api_post_with_session(gateway, "/api/lessons", body)

    data = _api_get(gateway, "/api/lessons")
    assert "lessons" in data
    assert any("e2e test lesson" in str(lesson) for lesson in data["lessons"])


def test_chat_slot_lifecycle(gateway):
    """Create a slot, get its detail, then delete it."""
    # Create
    create_data = _api_post(gateway, "/api/chat/slots", {})
    slot_key = create_data["key"]
    assert slot_key

    try:
        # Detail
        detail = _api_get(gateway, f"/api/chat/slots/{slot_key}")
        assert detail["key"] == slot_key
        assert "messages" in detail
    finally:
        _api_delete(gateway, f"/api/chat/slots/{slot_key}")


def test_session_detail(gateway):
    """Can fetch detail for the fixture-seeded session (returns message list).

    The minimal fixture ships ``dashboard_starter.jsonl`` -- assert against
    that known session rather than depending on ambient state.
    """
    sessions = _api_get(gateway, "/api/sessions")
    assert sessions["total"] >= 1, "minimal fixture must seed at least one session"
    # Use the fixture-seeded session (known precondition)
    first_key = sessions["sessions"][0]["key"]

    detail = _api_get(gateway, f"/api/sessions/{first_key}")
    assert isinstance(detail, list)


def test_session_search(gateway):
    """Session search endpoint returns results without errors."""
    data = _api_get(gateway, "/api/sessions/search?q=test")
    assert "sessions" in data


# --- Send -> assert (fake ACP backend) ---------------------------------------
#
# The control-plane tests above never exercise a model turn. This section
# stands up a *fake* ACP backend and drives a real chat turn end-to-end
# (gateway HTTP -> chat runner -> subprocess spawn -> ACP handshake -> streamed
# agent_message_chunk -> assembled assistant reply), fully offline.
#
# Seam: the gateway's provider already defaults to ``acp`` (the minimal fixture
# omits ``agent.provider``), so pointing ``WARDING_KIRO_BIN`` at the fake makes
# a turn spawn the fake instead of a real ``kiro-cli`` -- no new provider enum,
# no config-key override, nothing remotely selectable.


@pytest.fixture()
def acp_gateway(monkeypatch):
    """Gateway whose ``kiro-cli`` is the offline fake ACP backend.

    Function-scoped (separate from the module ``gateway``): only these tests
    want the fake wired in, and it must not leak ``WARDING_KIRO_BIN`` into the
    control-plane gateway. ``monkeypatch`` restores the env on teardown.
    """
    from warding.testing import fake_acp_backend
    from warding.testing.harness import spawn_feature_gateway

    # Execute the packaged fake itself so readiness probes and ACP turns use
    # the same deterministic backend rather than a test-only copy.
    monkeypatch.setenv("WARDING_KIRO_BIN", str(fake_acp_backend.__file__))

    with spawn_feature_gateway(fixture="minimal", approval="reads") as handle:
        # The WARDING_KIRO_BIN seam only fires when the provider resolves to
        # ``acp`` (the minimal fixture omits ``agent.provider``, which defaults
        # to acp). Fail fast with a clear message if that assumption ever
        # breaks, rather than surfacing it 60s later as a "no reply" timeout.
        cfg = handle.home / "config.json"
        if cfg.is_file():
            provider = (
                json.loads(cfg.read_text(encoding="utf-8")).get("agent", {}).get("provider", "acp")
            )
            assert provider == "acp", (
                "acp_gateway needs provider=acp for the WARDING_KIRO_BIN seam; "
                f"minimal fixture resolved provider={provider!r}"
            )
        yield handle


def _await_assistant_reply(gateway, slot: str, timeout: float = 60.0) -> dict:
    """Poll a slot's history until a non-empty assistant reply appears."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        detail = _api_get(gateway, f"/api/chat/slots/{slot}")
        for msg in detail.get("messages", []):
            if msg.get("role") == "assistant" and str(msg.get("content", "")).strip():
                return msg
        time.sleep(0.5)
    raise AssertionError(f"no non-empty assistant reply within {timeout:.0f}s")


def test_chat_send_receives_reply(acp_gateway):
    """A chat turn against the fake ACP backend yields a non-empty reply.

    This is the send->assert gate: it proves the whole gateway<->subprocess<->
    ACP path works (spawn, initialize/session-new handshake, prompt, streamed
    ``agent_message_chunk``, reply assembly + persistence) with a deterministic
    offline backend -- no Bedrock, no network, no auth.
    """
    slot = _api_post(acp_gateway, "/api/chat/slots", {})["key"]
    assert slot

    # ws=1: POST returns immediately; the reply is delivered over the WebSocket
    # AND persisted to the slot's message history, which we poll below.
    _api_post(
        acp_gateway,
        "/api/chat?ws=1",
        {"message": "ping", "slot": slot, "agent": "warding"},
    )

    reply = _await_assistant_reply(acp_gateway, slot)
    # Search the serialized message so the assertion doesn't couple to the
    # exact content field name after display preparation/redaction.
    assert "pong from the fake ACP backend" in json.dumps(reply)


def test_chat_tool_call_renders(acp_gateway):
    """A ``[[TOOL]]`` prompt drives the fake's tool-call path end-to-end.

    The fake emits a ``tool_call`` update + a ``tool_call_update`` (no
    permission) before the reply. Asserting the final reply still arrives
    proves the gateway processed the tool-call updates without stalling the
    turn -- the offline tool-card coverage the Playwright E2E builds on. The
    ``[[PERMISSION]]`` approval-modal path needs a UI to resolve the modal, so
    it is exercised by Playwright, not this headless suite.
    """
    slot = _api_post(acp_gateway, "/api/chat/slots", {})["key"]
    assert slot

    _api_post(
        acp_gateway,
        "/api/chat?ws=1",
        {"message": "please [[TOOL]] run the demo", "slot": slot, "agent": "warding"},
    )

    reply = _await_assistant_reply(acp_gateway, slot)
    assert "pong from the fake ACP backend" in json.dumps(reply)


# --- Concurrent config.json writers ------------------------------------------
#
# ``PUT /api/apps/registries`` and ``DELETE /api/security/trusted-apps/{name}``
# each rewrite the whole ``config.json``. Each one must read and write the file
# as one transaction. Otherwise a change that lands between its read and its
# write is lost when it writes back its older copy. These tests run both
# endpoints at the same time over HTTP. Then they check that every change is
# still in the API and on disk.

_RACE_GRANTS = 16  # trust grants revoked while registries PUTs run
_RACE_ROUNDS = 16  # registries PUTs sent while trust revocations run
_RACE_WRITERS = 4  # threads that keep the other endpoint busy
_RACE_MAX_WRITES = 1000  # per-thread cap, so a stuck request cannot loop forever
_RACE_TIMEOUT = 120.0  # seconds to wait for one side of a race to finish


@pytest.fixture(scope="module")
def race_gateway():
    """A separate gateway for the concurrent-writer tests.

    These tests replace the registries list and edit the trust grants. They use
    their own data home, so the shared ``gateway`` keeps its state.
    """
    from warding.testing import fake_acp_backend
    from warding.testing.harness import spawn_feature_gateway

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("WARDING_KIRO_BIN", str(fake_acp_backend.__file__))
        with spawn_feature_gateway(fixture="minimal", approval="reads") as handle:
            yield handle


def _api_call(gateway, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    """Send one request with the session cookie, and return its status and JSON body.

    An error status is returned, not raised, so that a worker thread can report it.
    """
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"http://localhost:{gateway.port}{path}", data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with _opener(gateway).open(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"body": raw}


def _repeat_until(stop: threading.Event, call: Callable[[], tuple[int, dict]]) -> list[int]:
    """Send *call* again and again until *stop* is set, and return every status.

    The first request goes out even when *stop* is already set.
    """
    statuses: list[int] = []
    while len(statuses) < _RACE_MAX_WRITES:
        statuses.append(call()[0])
        if stop.is_set():
            break
    return statuses


def _stored_grants(gateway) -> set[str]:
    """Every trust grant that ``config.json`` holds, effective or not."""
    status, body = _api_call(gateway, "GET", "/api/security/trusted-apps")
    assert status == 200, body
    return set(body["apps"]) | set(body["ineffective"])


def _registries(gateway) -> list[dict]:
    """The operator registries that ``GET /api/apps/registries`` reports."""
    status, body = _api_call(gateway, "GET", "/api/apps/registries")
    assert status == 200, body
    return body["registries"]


def _config_on_disk(gateway) -> dict:
    return json.loads((gateway.home / "config.json").read_text(encoding="utf-8"))


def _seed_trust_grants(gateway, names: list[str]) -> None:
    """Add *names* to ``agent.apps_trusted``, as an operator edits ``config.json``.

    No app with these names is installed. So a revocation removes the grant and
    stops no app code. The edit replaces the file with one rename.
    """
    path = gateway.home / "config.json"
    data = _config_on_disk(gateway)
    agent = data.setdefault("agent", {})
    agent["apps_trusted"] = sorted(set(agent.get("apps_trusted") or []) | set(names))
    staged = path.with_name(path.name + ".e2e-seed")
    staged.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(staged, path)


def _as_stored(rows: list[dict]) -> list[dict]:
    """*rows* as the registries API stores them: an operator row has the index tier."""
    return [{**row, "trust": "index"} for row in rows]


def test_trust_revocation_survives_concurrent_registries_puts(race_gateway):
    """A registries PUT that runs during a trust revocation must not restore the grant.

    The PUTs continue until every revocation has returned. A lost revocation
    stays lost, because each later PUT copies the restored grant forward.
    """
    names = [f"e2e-revoke-{i:02d}" for i in range(_RACE_GRANTS)]
    rows = [{"name": "e2e-race-a", "repo": "E2eRaceAppsA", "branch": "main"}]
    _opener(race_gateway)  # Mint the session cookie before the threads share it.
    _seed_trust_grants(race_gateway, names)
    assert set(names) <= _stored_grants(race_gateway), "the gateway did not load the seed"

    def put() -> tuple[int, dict]:
        return _api_call(race_gateway, "PUT", "/api/apps/registries", {"registries": rows})

    def revoke(name: str) -> tuple[int, dict]:
        return _api_call(race_gateway, "DELETE", f"/api/security/trusted-apps/{name}")

    stop = threading.Event()
    with ThreadPoolExecutor(max_workers=_RACE_WRITERS + _RACE_GRANTS) as pool:
        putters = [pool.submit(_repeat_until, stop, put) for _ in range(_RACE_WRITERS)]
        try:
            revokes = list(pool.map(revoke, names, timeout=_RACE_TIMEOUT))
        finally:
            stop.set()
        put_statuses = [s for f in putters for s in f.result(timeout=_RACE_TIMEOUT)]

    assert [status for status, _ in revokes] == [200] * len(names), revokes
    assert set(put_statuses) == {200}, put_statuses
    restored = sorted(set(names) & _stored_grants(race_gateway))
    assert not restored, f"a concurrent registries PUT restored revoked grants: {restored}"
    on_disk = _config_on_disk(race_gateway)
    assert not set(names) & set(on_disk.get("agent", {}).get("apps_trusted") or [])
    assert _registries(race_gateway) == _as_stored(rows)
    assert on_disk["registries"] == _as_stored(rows)


def test_registries_put_survives_concurrent_trust_revocations(race_gateway):
    """A trust revocation that runs during a registries PUT must not restore the old list.

    A revocation rewrites ``config.json`` even for a name that holds no grant.
    The revocations continue while the PUTs run one at a time. Each PUT sends a
    new list, and a GET after each PUT must return that list.
    """
    _opener(race_gateway)  # Mint the session cookie before the threads share it.

    def revoke(index: int) -> tuple[int, dict]:
        path = f"/api/security/trusted-apps/e2e-absent-{index}"
        return _api_call(race_gateway, "DELETE", path)

    stop = threading.Event()
    sent: list[list[dict]] = []
    seen: list[list[dict]] = []
    put_statuses: list[int] = []
    with ThreadPoolExecutor(max_workers=_RACE_WRITERS) as pool:
        revokers = [
            pool.submit(_repeat_until, stop, lambda i=i: revoke(i)) for i in range(_RACE_WRITERS)
        ]
        try:
            for round_no in range(_RACE_ROUNDS):
                # Each round's repo has a different length, so each PUT changes
                # the file size. The gateway's config cache keys on mtime and
                # size, and on a coarse clock two writes can share one mtime.
                rows = [
                    {
                        "name": f"e2e-race-b{round_no:02d}",
                        "repo": f"E2eRaceAppsB{round_no:02d}" + "x" * round_no,
                        "branch": "main",
                    }
                ]
                status, _ = _api_call(
                    race_gateway, "PUT", "/api/apps/registries", {"registries": rows}
                )
                put_statuses.append(status)
                sent.append(_as_stored(rows))
                seen.append(_registries(race_gateway))
        finally:
            stop.set()
        revoke_statuses = [s for f in revokers for s in f.result(timeout=_RACE_TIMEOUT)]

    assert put_statuses == [200] * _RACE_ROUNDS, put_statuses
    assert set(revoke_statuses) == {200}, revoke_statuses
    lost = [round_no for round_no, (want, got) in enumerate(zip(sent, seen)) if want != got]
    assert not lost, f"a concurrent trust revocation restored an older list in rounds {lost}"
    assert _registries(race_gateway) == sent[-1]
    assert _config_on_disk(race_gateway)["registries"] == sent[-1]
