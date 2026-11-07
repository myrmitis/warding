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

import contextlib
import http.cookiejar
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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


# --- Managed-agent identity in the boot sweep --------------------------------
#
# ``warding gateway`` sweeps ``kiro_session_pids.txt`` at boot, before READY.
# For each recorded PID that is still alive, it checks that the PID runs an
# agent that Warding launches, so it never signals a PID that the OS recycled
# onto an unrelated process. This test records the test's own disposable
# children in an isolated data home, boots the real gateway on that home, and
# reads which records the sweep kept. The sweep never signals a child that is
# younger than its spawn grace, so every child outlives the boot, and the test
# stops them itself.

#: Above the PID limit of every supported OS, so the recording gateway reads as
#: dead and the boot sweep handles its records.
_DEAD_GATEWAY_PID = 2_000_000_000
_CHILD_SLEEP_SECONDS = "600"


@contextlib.contextmanager
def _gateway_on_home(home: Path) -> Iterator[subprocess.Popen[bytes]]:
    """Run ``warding gateway`` on an existing data home until READY, then stop it.

    ``spawn_feature_gateway`` seeds a new, empty home, and the boot sweep runs
    before READY. A record must exist before the boot, so this starts the CLI
    on a prepared home with the same isolation environment as the harness.
    """
    from warding.kiro_prerequisite import FAKE_ACP_TEST_MODE_ENV
    from warding.testing import fake_acp_backend
    from warding.testing.harness import DEFAULT_READY_TIMEOUT, parse_ready_line, terminate_pgid

    src = Path(__file__).resolve().parents[1] / "src"
    env = {
        **os.environ,
        "PYTHONPATH": str(src) + os.pathsep + os.environ.get("PYTHONPATH", ""),
        "WARDING_HOME": str(home),
        "KIRO_HOME": str(home / "kiro"),
        "WARDING_KIRO_BIN": str(fake_acp_backend.__file__),
        FAKE_ACP_TEST_MODE_ENV: "1",
        "PYTHONUNBUFFERED": "1",
        "WARDING_SKIP_MODEL_DOWNLOAD": "1",
    }
    cmd = [sys.executable, "-m", "warding", "gateway", "--test-mode", "--approval", "reads"]
    out_log, err_log = home.parent / "gateway.out", home.parent / "gateway.err"
    with open(out_log, "wb") as out, open(err_log, "wb") as err:
        proc = subprocess.Popen(
            cmd + ["--no-crons"],
            env=env,
            stdout=out,
            stderr=err,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    try:
        deadline = time.monotonic() + DEFAULT_READY_TIMEOUT
        while True:
            lines = out_log.read_text(encoding="utf-8", errors="replace").splitlines()
            ready = [line for line in lines if line.startswith("WARDING_READY:")]
            if ready:
                parse_ready_line(ready[0])
                break
            tail = err_log.read_text(encoding="utf-8", errors="replace")[-2000:]
            assert proc.poll() is None, f"gateway exited before READY:\n{tail}"
            assert time.monotonic() < deadline, f"no READY line in time:\n{tail}"
            time.sleep(0.1)
        yield proc
    finally:
        terminate_pgid(proc.pid, wait=proc.wait)


def _spawn_child(argv: list[str], visible: str) -> subprocess.Popen[bytes]:
    """Start a disposable child and wait until an argv element contains *visible*.

    The argv becomes readable only after the child's exec. A probe that runs
    earlier reads an empty or a pre-exec vector. *visible* holds no space,
    because macOS reports the argv split on whitespace.
    """
    from warding import platform_compat

    child = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.monotonic() + 10
    while not any(visible in element for element in platform_compat.process_argv(child.pid) or ()):
        assert time.monotonic() < deadline, f"argv of {argv!r} never showed {visible!r}"
        time.sleep(0.05)
    return child


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks, bash and exec -a")
def test_boot_sweep_keeps_only_records_of_agent_launchers(tmp_path: Path) -> None:
    """The boot sweep keeps a record only when its PID runs an agent launcher.

    A path through a directory named like an agent (``.claude/worktrees``), an
    argument value, a script name, a ``-c`` payload, a positional word, or the
    Claude Code CLI on its own names no agent, so the sweep drops the record.
    Every launcher form that Warding records stays tracked: kiro-cli and its
    exec'd siblings, the claude-agent-acp adapter as an executable, as a Node
    entry script and as an npm title, the Linux sandbox launcher, and KAS.
    """
    from warding import platform_compat

    sleep_bin, bash = shutil.which("sleep"), shutil.which("bash")
    assert sleep_bin and bash
    tools = tmp_path / "tools"

    def link(rel: str) -> str:
        path = tools / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(sleep_bin)
        return str(path)

    launcher = tools / "run" / "warding_sandbox_1_e2e.py"
    launcher.parent.mkdir(parents=True)
    launcher.write_text(f"import time\ntime.sleep({_CHILD_SLEEP_SECONDS})\n", encoding="utf-8")
    entry = tools / "lib/node_modules/@agentclientprotocol/claude-agent-acp/dist/index.js"
    kas = tools / "kas/1.0/node_modules/@kiro/agent/dist/server/acp-server.js"
    title = "npm exec @agentclientprotocol/claude-agent-acp@^0.60.0"
    idle = f"sleep {_CHILD_SLEEP_SECONDS}; :"  # the trailing ':' stops bash exec'ing sleep
    decoy_path = link(".claude/worktrees/wt/bin/sleep")
    claude_cli = link("bin/claude")
    kiro = link("bin/kiro-cli")
    kiro_chat = link("bin/kiro-cli-chat")
    adapter = link("bin/claude-agent-acp")
    # name: (argv, an element that shows once the child has exec'd)
    unmanaged = {
        "plain sleep": ([sleep_bin, _CHILD_SLEEP_SECONDS], sleep_bin),
        "path under .claude/worktrees": ([decoy_path, _CHILD_SLEEP_SECONDS], decoy_path),
        "argument value naming .claude": (
            [bash, "-c", idle, "sh", f"--config={tools}/.claude/settings.json"],
            f"--config={tools}/.claude/settings.json",
        ),
        "script named myclaude.sh": ([bash, "-c", idle, "myclaude.sh"], "myclaude.sh"),
        "-c payload naming claude, .claude and kiro-cli": (
            [bash, "-c", f"{idle} claude {tools}/.claude/notes --log={tools}/kiro-cli.log"],
            f"--log={tools}/kiro-cli.log",
        ),
        "positional word claude": ([bash, "-c", idle, "sh", "claude"], "claude"),
        "Claude Code CLI named claude": ([claude_cli, _CHILD_SLEEP_SECONDS], claude_cli),
    }
    managed = {
        "kiro-cli": ([kiro, _CHILD_SLEEP_SECONDS], kiro),
        "kiro-cli-chat": ([kiro_chat, _CHILD_SLEEP_SECONDS], kiro_chat),
        "claude-agent-acp": ([adapter, _CHILD_SLEEP_SECONDS], adapter),
        "sandbox launcher": ([sys.executable, str(launcher), kiro, "acp"], str(launcher)),
        "node adapter entry": ([sys.executable, str(launcher), str(entry)], str(entry)),
        "npm title": (
            [bash, "-c", f'exec -a "$0" sleep {_CHILD_SLEEP_SECONDS}', title],
            title.rsplit(" ", 1)[-1],
        ),
        "KAS": (
            [
                sys.executable,
                str(launcher),
                "--experimental-wasm-modules",
                str(kas),
                "--transport=stdio",
                "--auth=acp-callback",
            ],
            str(kas),
        ),
    }
    home = tmp_path / "home"
    home.mkdir()
    children: dict[str, subprocess.Popen[bytes]] = {}
    try:
        for name, (argv, visible) in {**unmanaged, **managed}.items():
            children[name] = _spawn_child(argv, visible)
        records = []
        for child in children.values():
            token = platform_compat.get_process_start_id(child.pid)
            suffix = f":{token}" if token else ""
            records.append(f"{_DEAD_GATEWAY_PID}:{child.pid}{suffix}")
        (home / "kiro_session_pids.txt").write_text("\n".join(records) + "\n", encoding="utf-8")

        with _gateway_on_home(home):
            kept_pids = set()
            for line in (home / "kiro_session_pids.txt").read_text(encoding="utf-8").split():
                gateway, _, rest = line.partition(":")
                if gateway == str(_DEAD_GATEWAY_PID):
                    kept_pids.add(int(rest.split(":", 1)[0]))
            kept = {name for name, child in children.items() if child.pid in kept_pids}

        assert not kept & set(unmanaged), f"records of non-agents survived: {kept & set(unmanaged)}"
        assert (
            set(managed) <= kept
        ), f"records of agent launchers were dropped: {set(managed) - kept}"
        signalled = [name for name, child in children.items() if child.poll() is not None]
        assert (
            not signalled
        ), f"the boot sweep signalled a child inside its spawn grace: {signalled}"
    finally:
        for child in children.values():
            child.kill()
            child.wait(timeout=5)
