"""Steward HTTP surface — the Stewards dashboard page and the stewards' own writes.

Registered from ``routes.register_routes`` (one import, one call) rather than by
the app manifest, so this app still has exactly ONE place that lists its routes.
It lives in its own module because ``routes.py`` is already 200KB and the steward
surface is a separate feature with its own store; the shared request plumbing
(``_key_from_request``, ``_str_field``, ``_st``, ``_require_enabled``,
``_pr_action_preamble``, ``_audit``) is imported from ``routes`` rather than
re-derived, because a second copy of a gate is how one of them eventually ships
without the check.

Routes, all under ``/api/apps/issue-radar``:

  GET    /stewards?owner&repo          -> {owner,repo,provider,host, stewards[], settings,
                                           counts{on_duty,working,paused}}
  POST   /stewards                     -> {steward}
  GET    /stewards/names?owner&repo    -> {suggestions[]}
  GET    /steward?owner&repo&id        -> {owner,repo,provider,host, steward, items[],
                                           events[], settings, skipped_numbers[],
                                           recent_skips[], counts{open}}
  PUT    /steward                      -> {steward}
  DELETE /steward                      -> {steward}     (retire — the record survives)
  GET    /steward/fabric?owner&repo    -> {schema, owner,repo,provider,host,
                                           generated_at, phases[], items[]}
  PUT    /steward/work                 -> {item, event, skip}
  POST   /steward/pause                -> {steward}
  GET    /stewards/settings?owner&repo -> {settings}
  PUT    /stewards/settings            -> {settings}
  POST   /issue/comment                -> {comment_id, url, number}

There is deliberately NO route through which a human answers a steward, and no queue
of items a steward is holding for one. A steward that needs a human decision or a human
investigation says so on the issue, labels it with the repo's
``needs_human_label``, records the pass and releases its claim — so the place that
work waits is the issue tracker the person already reads, not a dashboard-local
inbox that only exists while this app is running.

WRITE-PERMISSION DECISION (the one this module had to make). Two tiers:

  * ``POST /issue/comment`` is a FORGE write and goes through
    ``routes._pr_action_preamble``, which is the existing gate chain used by every
    mutating pull-request route: JSON body -> owner/repo -> connected repo ->
    ``_repo_can_write`` (fail-closed: ``None`` from a transient ``gh`` failure is
    DENIED). Nothing about a steward earns a weaker gate than a human clicking the
    same button.

  * Every LOCAL steward route (stewards, steward, work, pause, settings) requires the repo
    to be CONNECTED but **not** writable. Three reasons, in the order they
    mattered:
      1. Precedent: ``_handle_put_investigation`` is the same shape — per-repo
         local state, nothing reaches the forge — and is gated on connected only.
      2. ``_repo_can_write`` FAILS CLOSED, and these writes are how a steward records
         work it has ALREADY done. Gating them on a remote permission read means a
         network blip leaves a steward holding a dirty worktree with no way to persist
         its phase or its reason — losing local truth to an unrelated outage. The
         forge writes it would then attempt are each gated on their own.
      3. A read-only repo can still use a steward: Issue Radar already degrades to
         suggest-only there, and a steward that investigates and records what it found
         without pushing is a legitimate configuration. Permissions can also be
         granted later without recreating the steward.
    The exposure this accepts is bounded and local: a user who can reach the
    dashboard can create steward records on a repo they cannot write to. Those records
    cannot mutate the repo — the first forge write refuses.

``steward_store.StewardStoreError`` maps to **409**, never 500: every raise is a
user-visible condition (a duplicate steward name, a second item trying to enter an
editing phase). "Unknown steward" is caught earlier and answered 404, because a
missing record is not a conflict.

WHO A STEWARD IS (the identity decision). Exactly two routes are reachable by an
AGENT — ``GET /steward`` and ``PUT /steward/work``, the pair behind the
``issue_radar_steward_read`` / ``issue_radar_steward_record`` MCP tools. For an agent
caller (loopback + ``X-Internal-Secret``, which the auth middleware marks as
``request["internal_auth"]``), owner, repo and steward id are derived from the
AUTHENTICATED SESSION KEY: ``X-Session-Key`` is matched against the steward record's
``slot_key``. They are never taken from the request. That is the whole security
property — an agent cannot NAME a repo, so it cannot reach a same-numbered issue
in another repo, and it cannot reach another steward's ledger at all (which would
also defeat the store's per-steward "one editing item" invariant). A query or body
that names a DIFFERENT owner/repo/steward is refused **403**, not quietly rewritten:
a cross-steward attempt must fail where someone can see it. The dashboard, which
authenticates with a cookie, keeps passing ``owner``/``repo``/``id`` unchanged.

Every OTHER steward route refuses an internal-secret caller outright — see
``_AGENT_REACHABLE``. This gate lives here and not in the middleware allowlist
because the allowlist cannot express it: ``dashboard.server`` entries are matched
``path == p or path.startswith(p + "/")`` and carry no method, so the ``/steward``
entry admits ``/steward/pause`` as well, and no path-only entry can separate
``GET /steward`` from ``PUT``/``DELETE /steward``. Deny-by-default HERE is what makes
"those two endpoints and only those two" true, including for any route added under
``/steward/`` later.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
from functools import partial, wraps
from typing import Any

from aiohttp import web

from . import provider, routes, steward_runtime, steward_store, store

logger = logging.getLogger("junction.app.issue-radar.stewards")

_BASE = "/api/apps/issue-radar"

#: Phases in which the steward is NOT the actor: it is waiting on CI, on a human's
#: merge, or on a human's reply. It is never waiting on a human's DECISION — that
#: is recorded as a pass and the claim released, so no phase represents it.
#:
#: A THIRD classification of ``steward_store.PHASES``, deliberately not one of the
#: store's two — and it coincides with neither. TTL_ACTIVE is about which claims
#: age; EDITING is about worktrees. This one is about who the surface should show
#: as busy, which is a presentation question, which is why it lives in the route
#: module and not in the store.
PARKED_PHASES = frozenset({"awaiting-ci", "awaiting-merge", "awaiting-reply"})

#: The ``(method, sub-path)`` pairs an internal-secret caller — an agent running a
#: steward's MCP tools — may reach. Everything else in this module refuses one.
#:
#: EXACT method+path pairs, because that is the shape of the claim and the
#: middleware allowlist cannot make it: see the identity section of the module
#: docstring. Adding a pair here is granting an unattended agent a new capability,
#: so it is deliberately a one-line, reviewable change.
_AGENT_REACHABLE: frozenset[tuple[str, str]] = frozenset(
    {("GET", "/steward"), ("PUT", "/steward/work")}
)

#: Work-item fields ``PUT /steward/work`` forwards to ``upsert_work_item``.
#:
#: Listed explicitly so the envelope keys (owner/repo/steward_id/number/event/
#: event_kind) cannot land in the patch, and so this route's writable surface is
#: readable in one place. The store validates each field's TYPE and drops
#: unknowns, so this list is about legibility, not safety.
_WORK_PATCH_FIELDS = (
    "phase", "decision", "why", "next", "worktree", "branch", "base_sha",
    "pr_number", "claim_comment_id", "ci_state", "labels_applied",
    "outcome", "tried_approach", "tried_rejected_because",
)

#: Bound on ``GET /steward?limit=`` — the ledger is append-only and a steward that ran
#: for weeks has thousands of lines; an unbounded read is a whole file into RAM
#: and down the websocket on a page open.
_MAX_EVENTS = 500
_DEFAULT_EVENTS = 200

#: Bound on ``GET /stewards/names?limit=`` — the pool is 24 names and the create
#: dialog shows a handful of chips.
_MAX_SUGGESTIONS = 24

#: Bound on ``recent_skips`` in the ``GET /steward`` payload. Its siblings' bounds
#: exist to keep a whole file out of RAM; this one exists to keep the steward's OWN
#: context small — the list is read into an agent's prompt on every resume, and
#: each entry carries free-text prose. ``skipped_numbers`` alongside it is
#: deliberately unbounded (see ``_steward_page``).
_MAX_RECENT_SKIPS = 20


# ── shared plumbing ─────────────────────────────────────────────────────────


def _steward_conflict(handler):
    """Map ``StewardStoreError`` onto 409 for EVERY steward route.

    A decorator rather than a try/except per handler: the store raises this for
    invariant violations that are ordinary user conditions (duplicate name, second
    editing item), and letting one escape would surface a legitimate refusal as a
    500 — which the frontend renders as "something broke" instead of the store's
    own message, and which a steward agent would retry forever.
    """
    @wraps(handler)
    async def _wrapped(request: web.Request) -> web.Response:
        try:
            return await handler(request)
        except steward_store.StewardStoreError as exc:
            return web.json_response({"error": str(exc), "code": "steward_conflict"}, status=409)

    return _wrapped


def _agent_gate(method: str, path: str, handler):
    """Refuse an internal-secret caller on every steward route but the two in
    ``_AGENT_REACHABLE``.

    Deny-by-default, and applied to the whole table rather than to the routes that
    look dangerous today: the middleware admits the entire ``/steward/`` segment to
    anything holding the internal secret, so without this an agent could pause or
    RETIRE another steward — and any route added under that segment later becomes
    agent-reachable with no edit anywhere. Refusing at the handler is the pattern
    ``api_skills_discover_install`` already uses for the same reason, and it is the
    ONLY place a method can be distinguished, which ``PUT``/``DELETE /steward`` need.

    A cookie-authenticated browser request never carries ``internal_auth``, so the
    dashboard is unaffected.
    """
    reachable = (method, path) in _AGENT_REACHABLE

    @wraps(handler)
    async def _wrapped(request: web.Request) -> web.Response:
        if not reachable and request.get("internal_auth"):
            return web.json_response(
                {"error": f"{method} {path} is not reachable by an agent",
                 "code": "agent_route_denied"},
                status=403,
            )
        return await handler(request)

    return _wrapped


def _caller_slot_keys(request: web.Request) -> tuple[str, ...]:
    """The slot-key forms ``X-Session-Key`` could be carrying, most specific first.

    A dashboard session key is ``dashboard:<slot key>`` and a steward's slot key is
    what its record stores, so the post-colon remainder is the form that matches;
    the unsplit value is kept too, for a caller that already sends the bare key. A
    key from any other surface (``slack:``, ``cron:``, ``subagent:``) simply matches
    no steward and is answered "not a steward session".

    Stripped, because a trailing space would miss the match and be reported as "not
    a steward" — inconsistent normalization in an identity comparison (CWE-178).
    """
    raw = request.headers.get("X-Session-Key", "").strip()
    if not raw:
        return ()
    forms = [raw]
    if ":" in raw:
        forms.append(raw.split(":", 1)[1].strip())
    return tuple(dict.fromkeys(form for form in forms if form))


def _steward_for_slot(slot_keys: tuple[str, ...]) -> tuple[provider.RepoKey, dict[str, Any]] | None:
    """The steward whose ``slot_key`` is this session, searched across connected repos.

    Blocking (one directory walk plus a JSON read per steward), so callers hand it to
    ``asyncio.to_thread``. The search is repo-wide because a session key carries no
    repo: ``slot_key`` is the only field the header and the record share. First
    match in connected-repo order wins, which is deterministic — steward ids are
    ``c_<8 hex>`` from ``secrets``, so two live stewards sharing one is not a case
    worth a tie-break.

    Retired stewards are INCLUDED. Identifying one and then refusing it with the
    route's own ``steward_retired`` says what actually happened; reporting "this
    session is not a steward" to a steward that plainly is reads as a bug to whoever is
    looking at the transcript afterwards.

    The residual this leaves: a slot key is the only evidence of steward identity, so a
    session a human deliberately names after a steward's slot key resolves to that
    steward. It grants no privilege that human does not already hold — they can read and
    write the same ledger from the Stewards page — but closing it needs the runtime to
    mark a slot as app-owned when it creates one, which is
    ``steward_runtime``/``state``'s to record, not something this lookup can derive.
    """
    for entry in store.list_connected_repos():
        owner = str(entry.get("owner") or "")
        repo = str(entry.get("repo") or "")
        if not owner or not repo:
            continue
        key = provider.key_from_parts(owner, repo, entry.get("provider"), entry.get("host"))
        for steward in steward_store.list_stewards(
            owner, repo, routes._scope(key), include_retired=True
        ):
            if str(steward.get("slot_key") or "") in slot_keys:
                return key, steward
    return None


def _identity_mismatch(
    key: provider.RepoKey, steward: dict[str, Any], supplied: dict[str, str]
) -> web.Response | None:
    """403 when a request named an owner, repo or steward that is not the caller's own.

    A mismatch is REFUSED rather than overwritten with the session's identity. Both
    are safe, but silently rewriting turns a cross-steward write attempt into a
    successful-looking write against a different item than the caller asked for —
    which is indistinguishable from a bug in the steward's own bookkeeping. Absent
    fields are not a mismatch: the MCP tools send nothing at all.
    """
    own = {"owner": key.owner, "repo": key.repo, "id": str(steward.get("id") or "")}
    for field, mine in own.items():
        theirs = supplied.get(field) or ""
        if theirs and theirs != mine:
            return web.json_response(
                {"error": (f"this session's steward is "
                           f"{own['owner']}/{own['repo']}:{own['id']} — "
                           f"{field!r} cannot name another"),
                 "code": "steward_identity_mismatch"},
                status=403,
            )
    return None


async def _session_identity(
    request: web.Request, supplied: dict[str, str]
) -> tuple[provider.RepoKey, dict[str, Any], web.Response | None]:
    """Resolve WHICH steward is calling from its authenticated session key.

    The agent-side counterpart of ``_query_preamble``/``_body_preamble``, and it
    ends with the same connected-repo gate so an agent cannot reach a repo the user
    has disconnected. ``supplied`` is whatever the caller put in its query or body:
    it is only ever COMPARED (see :func:`_identity_mismatch`), never used as the
    source of identity.
    """
    slot_keys = _caller_slot_keys(request)
    if not slot_keys:
        return provider.RepoKey(), {}, web.json_response(
            {"error": "missing X-Session-Key — a steward is identified by its session",
             "code": "missing_session"},
            status=403,
        )
    found = await asyncio.to_thread(partial(_steward_for_slot, slot_keys))
    if found is None:
        return provider.RepoKey(), {}, web.json_response(
            {"error": "this session is not an Issue Radar steward, so it has no ledger",
             "code": "not_a_steward_session"},
            status=403,
        )
    key, steward = found
    mismatch = _identity_mismatch(key, steward, supplied)
    if mismatch is not None:
        return key, steward, mismatch
    if not await asyncio.to_thread(routes._connected, key):
        return key, steward, web.json_response(
            {"error": f"{key.slug} is not connected — call /connect first",
             "code": "repo_not_connected"},
            status=404,
        )
    return key, steward, None


async def _query_preamble(
    request: web.Request,
) -> tuple[provider.RepoKey, web.Response | None]:
    """``?owner=``/``?repo=`` + the connected-repo gate, for the GET routes.

    No write gate — see the module docstring's write-permission decision.
    """
    key = routes._key_from_request(request)
    if not key.owner or not key.repo:
        return key, web.json_response(
            {"error": "missing ?owner= and ?repo=", "code": "missing_repo"}, status=400
        )
    # Synchronous config read, so off the loop — the same call every other route in
    # this app makes through asyncio.to_thread.
    if not await asyncio.to_thread(routes._connected, key):
        return key, web.json_response(
            {"error": f"{key.slug} is not connected — call /connect first",
             "code": "repo_not_connected"},
            status=404,
        )
    return key, None


def _holds_non_finite_number(value: Any) -> bool:
    """Whether *value* carries ``Infinity``, ``-Infinity`` or ``NaN`` anywhere.

    Python's ``json`` decodes those three literals by default, and it also produces
    them from a plain-looking one: ``1e309`` overflows to ``inf`` SILENTLY on the way
    in. So a body can carry a float that no field on these records can accept
    (``int(inf)`` raises ``OverflowError``, ``int(nan)`` raises ``ValueError``) and
    that no encoder can write back — ``json.dumps`` emits a bare ``Infinity``, which
    is not JSON, so storing one would leave a record the dashboard's ``JSON.parse``
    refuses to read.

    Refused WHOLE, and here rather than per field, for two reasons. The value is
    unusable for every field, so a 400 that names the body is a better answer than a
    200 that silently ignored part of the patch. And this is the one place every
    steward-route body passes through — both legs, the cookie caller's and the agent's
    — so a route added later cannot be the one that forgot. The store's own coercion
    stays as the second layer, for the values that arrive from a file or from the
    forge rather than from a request.

    Walked ITERATIVELY. A recursive walk would turn a deeply nested body into a
    ``RecursionError`` — a 500 — on the way to rejecting it.
    """
    stack: list[Any] = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, float) and not math.isfinite(item):
            return True
        if isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return False


async def _json_object(request: web.Request) -> tuple[dict, web.Response | None]:
    """The request's JSON object, or the 400 to return instead.

    Split out of :func:`_body_preamble` so the agent write path can read a body
    without the owner/repo gate it does not use — one implementation, so the two
    paths cannot drift on which malformed payload gets which refusal.
    """
    try:
        raw = await request.json()
    except Exception:
        return {}, web.json_response(
            {"error": "request body must be JSON", "code": "invalid_json"}, status=400
        )
    if not isinstance(raw, dict):
        return {}, web.json_response(
            {"error": "request body must be a JSON object", "code": "invalid_json"}, status=400
        )
    if _holds_non_finite_number(raw):
        return {}, web.json_response(
            {
                "error": "request body must not contain Infinity, -Infinity or NaN "
                         "(a numeric literal too large to represent decodes to Infinity)",
                "code": "non_finite_number",
            },
            status=400,
        )
    return raw, None


async def _body_preamble(
    request: web.Request,
) -> tuple[dict, provider.RepoKey, web.Response | None]:
    """JSON body + owner/repo + the connected-repo gate, for the mutating routes.

    Deliberately NOT ``routes._pr_action_preamble``: that one also demands
    ``_repo_can_write``, which these local-state writes intentionally do not
    require (module docstring). Everything else — the malformed-JSON 400, the
    non-object 400, the not-connected 404 — is the same, in the same order, so a
    caller cannot tell the two preambles apart except by the gate that differs.
    """
    raw, early = await _json_object(request)
    if early is not None:
        return {}, provider.RepoKey(), early
    key = routes._key_from_body(raw)
    if not key.owner or not key.repo:
        return raw, key, web.json_response(
            {"error": "missing 'owner'/'repo'", "code": "missing_repo"}, status=400
        )
    if not await asyncio.to_thread(routes._connected, key):
        return raw, key, web.json_response(
            {"error": f"{key.slug} is not connected — call /connect first",
             "code": "repo_not_connected"},
            status=404,
        )
    return raw, key, None


async def _require_steward(
    key: provider.RepoKey, steward_id: str, *, must_be_live: bool
) -> tuple[dict, web.Response | None]:
    """Load a steward, or the response to return instead.

    An unknown steward is **404**, not the 409 that ``update_steward``'s own
    ``StewardStoreError`` would produce: a record that does not exist is not a
    conflicting write, and a 409 tells a steward agent to retry something that can
    never succeed. The residual race (the steward is retired between this read and
    the write) still surfaces as the store's 409, which is the correct answer for
    a write that lost.

    ``must_be_live`` refuses a RETIRED steward. Retiring stops the steward and releases
    its slot, so a work-item write afterwards would either vanish (nothing will ever
    pick it up) or resurrect a steward whose name is still attached to public claim
    comments. A rename or a re-retire is still allowed — those only touch the
    archived record.
    """
    if not steward_id:
        return {}, web.json_response(
            {"error": "missing 'id'", "code": "missing_steward_id"}, status=400
        )
    # A MALFORMED id is a bad request, distinct from both "unknown" (404) and the
    # store's "conflict" (409). Checked here as well as in the store because the
    # store can only raise StewardStoreError, which this app maps to 409 — and 409
    # tells a steward agent to retry an id that can never work. The store's own gate
    # is the security boundary (it stops a path escaping the steward directory); this
    # one exists to answer with the right status.
    if not steward_store.is_steward_id(steward_id):
        return {}, web.json_response(
            {"error": f"invalid steward id {steward_id!r}", "code": "invalid_steward_id"},
            status=400,
        )
    steward = await routes._st(key, steward_store.read_steward, key.owner, key.repo, steward_id)
    if steward is None:
        return {}, web.json_response(
            {"error": f"unknown steward {steward_id!r}", "code": "steward_not_found"}, status=404
        )
    if must_be_live and steward.get("retired_at"):
        return steward, web.json_response(
            {"error": f"steward {steward.get('name') or steward_id!r} is retired",
             "code": "steward_retired"},
            status=409,
        )
    return steward, None


def _steward_flags(steward: dict, open_items: list[dict]) -> dict[str, bool]:
    """The two per-steward booleans the chip counts sum.

    Exactly the definitions the Stewards page filters on:
      ``working``   — the NEWEST open item is in a non-parked phase, i.e. the steward
                      itself is the actor right now. Newest, not any: a steward with
                      one item parked on CI and one being implemented is working,
                      and ``list_work_items`` already returns newest-progress-first.
      ``paused``    — switched off but not retired.

    There is no "needs you" flag, because a steward never holds an issue for a human:
    the one that needs a decision or an investigation is labelled and handed back to
    the issue tracker, so a person's queue is the tracker's own filter, not a
    per-steward boolean this app would have to keep true while the steward idles.

    These are NOT mutually exclusive and the counts they feed are NOT a partition:
    a paused steward with an in-flight item is counted in both. That is correct for
    chip filters, where each chip is an independent predicate rather than a slice
    of a pie — the numbers are deliberately allowed to sum past the steward count.
    """
    return {
        "working": bool(open_items) and open_items[0].get("phase") not in PARKED_PHASES,
        "paused": steward.get("enabled") is False and not steward.get("retired_at"),
    }


def _steward_status(flags: dict[str, bool]) -> str:
    """One status for the steward's status DOT.

    A dot can only be one colour, so unlike the counts this must pick, and the
    order is by what the user has to do about it: a paused steward is doing nothing
    regardless of what it holds, work in flight needs nothing, and idle is the
    absence of both.
    """
    if flags["paused"]:
        return "paused"
    if flags["working"]:
        return "working"
    return "idle"


def _stewards_page(owner: str, repo: str, root: Any) -> dict[str, Any]:
    """Everything ``GET /stewards`` answers, computed in ONE off-loop call.

    Not N separate ``_st`` round-trips: the counts need every steward's open work
    items, which is a directory walk plus a JSON read per item, so a hop per steward
    turns one page load into 2×N event-loop hand-offs for data that is already
    being read on the same thread.
    """
    stewards = steward_store.list_stewards(owner, repo, root)
    counts = {"on_duty": len(stewards), "working": 0, "paused": 0}
    for steward in stewards:
        open_items = steward_store.list_work_items(
            owner, repo, str(steward.get("id") or ""), root, open_only=True
        )
        flags = _steward_flags(steward, open_items)
        for name, value in flags.items():
            if value:
                counts[name] += 1
        # Additive per-steward field, derived from the same flags as the counts. It is
        # here so the phase taxonomy stays in one language: without it the frontend
        # has to re-encode PARKED_PHASES in TypeScript and the two drift the first
        # time a phase is added.
        steward["status"] = _steward_status(flags)
    return {
        "stewards": stewards,
        "settings": steward_store.read_settings(owner, repo, root),
        "counts": counts,
    }


def _steward_page(owner: str, repo: str, steward_id: str, limit: int, root: Any) -> dict[str, Any]:
    """Everything ``GET /steward`` answers, in ONE off-loop call (see ``_stewards_page``).

    ``settings`` is part of it because this response is a resuming steward's whole
    briefing: the claim TTL is the number its protocol negotiates with, and a steward
    that cannot read it has to guess at the one thing that decides whether its claim
    is still valid.

    The two skip fields are shaped by who reads them and are deliberately NOT the
    same list twice:

      * ``skipped_numbers`` is COMPLETE and unbounded. A steward tests membership
        against it before it starts investigating, and a truncated list answers
        "not skipped" for an issue that is — which is the exact re-investigation
        this index exists to prevent. Ints are ~8 bytes each; a repo would need
        tens of thousands of passes before this is worth a second round trip.
      * ``recent_skips`` carries the PROSE, which is unbounded per entry, so it is
        capped. It answers a different question — what kind of work this fleet has
        been declining lately — and the whole index is on the steward page for anyone
        who needs more.
    """
    skips = steward_store.read_skips(owner, repo, root)
    return {
        "steward": steward_store.read_steward(owner, repo, steward_id, root),
        "items": steward_store.list_work_items(owner, repo, steward_id, root),
        "events": steward_store.read_events(owner, repo, root, steward_id=steward_id, limit=limit),
        "settings": steward_store.read_settings(owner, repo, root),
        "skipped_numbers": sorted(row["number"] for row in skips.values()),
        "recent_skips": [
            {"number": row["number"], "reason": row["reason"], "scope": row["scope"]}
            for row in steward_store.recent_skips(owner, repo, root, limit=_MAX_RECENT_SKIPS)
        ],
        "counts": {"open": steward_store.open_slot_count(owner, repo, steward_id, root)},
    }


def _bounded_limit(raw: str, default: int, ceiling: int) -> int:
    """A positive ``?limit=`` clamped to ``ceiling``; anything unparseable is the
    default. A bad limit is not worth a 400 on a read route — the ceiling is what
    protects the loop, and it applies either way."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, ceiling))


def _drop_issue_detail_cache(owner: str, repo: str, number: int, root: Any) -> None:
    """Invalidate one issue's cached detail + timeline after a comment lands.

    ``store`` has ``drop_pr_detail_cache`` but no issue equivalent yet, and adding
    one is another module's change, so this is that same one-line unlink through
    the store's own public path helper (OSError suppressed for the same reason:
    failing to invalidate a cache must not fail the write that succeeded).

    It matters more here than on the PR side. The steward's claim protocol READS the
    timeline back to confirm its own check-in comment; served a pre-comment cache
    it would conclude the claim never posted and post a second one.
    """
    with contextlib.suppress(OSError):
        store.issue_detail_cache_path(owner, repo, int(number), root).unlink(missing_ok=True)


# ── stewards (list / create / names) ────────────────────────────────────────


async def _handle_stewards_list(request: web.Request) -> web.Response:
    """GET /stewards?owner&repo — the Stewards page's whole payload: the repo's
    non-retired stewards (each with a derived ``status``), the repo-wide protocol
    settings, and the four chip counts."""
    key, early = await _query_preamble(request)
    if early is not None:
        return early
    page = await asyncio.to_thread(
        partial(_stewards_page, key.owner, key.repo, routes._scope(key))
    )
    return web.json_response({**routes._identity(key), **page})


async def _handle_steward_create(request: web.Request) -> web.Response:
    """POST /stewards {"owner","repo","name", ...steward fields} -> {"steward"}.

    The store enforces name uniqueness (including retired stewards' names) and drops
    unknown fields, so this route validates only that a name was sent — a
    duplicate comes back as the store's own 409 message, which names the taken
    name rather than a generic conflict.
    """
    body, key, early = await _body_preamble(request)
    if early is not None:
        return early
    if not routes._str_field(body, "name"):
        return web.json_response(
            {"error": "'name' is required", "code": "name_required"}, status=400
        )
    steward = await routes._st(key, steward_store.create_steward, key.owner, key.repo, body)
    routes._audit("steward_create", f"{key.slug}:{steward['id']}", "ok")
    return web.json_response({"steward": steward})


async def _handle_steward_names(request: web.Request) -> web.Response:
    """GET /stewards/names?owner&repo[&limit] -> {"suggestions"} — unused galaxy
    names for the create dialog's chips. Suggestions only: the name field is free
    text, so uniqueness is enforced on create, not here."""
    key, early = await _query_preamble(request)
    if early is not None:
        return early
    limit = _bounded_limit(request.query.get("limit") or "", 6, _MAX_SUGGESTIONS)
    suggestions = await routes._st(
        key, steward_store.suggest_names, key.owner, key.repo, limit=limit
    )
    return web.json_response({"suggestions": suggestions})


# ── one steward (read / update / retire) ────────────────────────────────────


async def _handle_steward_read(request: web.Request) -> web.Response:
    """GET /steward -> {owner,repo,provider,host,"steward","items","events","settings","counts"} —
    one steward's page: its record, all its work items (newest progress first), its
    slice of the event ledger, the repo's protocol settings, and its slot accounting.

    TWO callers with TWO identity sources (module docstring, "WHO A STEWARD IS"):

      * the dashboard authenticates with a cookie and passes ``?owner&repo&id``;
      * a steward agent authenticates with the internal secret and passes NOTHING —
        owner, repo and steward id come from its session key. This is the route the
        ``issue_radar_steward_read`` tool calls, and the reason that tool takes no
        arguments at all.

    The identity fields are ECHOED at the top level because the write leg's caller
    needs them and must not invent them: ``issue_radar_steward_record`` reads them out
    of this response and puts them in its PUT body, so a same-numbered issue in
    another repo can never be the item that gets overwritten.
    """
    if request.get("internal_auth"):
        key, steward, early = await _session_identity(
            request,
            {
                "owner": (request.query.get("owner") or "").strip(),
                "repo": (request.query.get("repo") or "").strip(),
                "id": (request.query.get("id") or "").strip(),
            },
        )
        if early is not None:
            return early
        steward_id = str(steward.get("id") or "")
    else:
        key, early = await _query_preamble(request)
        if early is not None:
            return early
        steward_id = (request.query.get("id") or "").strip()
        # Read routes accept a retired steward: its record, work log and ledger are kept
        # deliberately so the page still opens after retirement.
        _steward, missing = await _require_steward(key, steward_id, must_be_live=False)
        if missing is not None:
            return missing
    limit = _bounded_limit(request.query.get("limit") or "", _DEFAULT_EVENTS, _MAX_EVENTS)
    page = await asyncio.to_thread(
        partial(_steward_page, key.owner, key.repo, steward_id, limit, routes._scope(key))
    )
    return web.json_response({**routes._identity(key), **page})


def _auto_approve_armed(steward: dict[str, Any]) -> bool:
    """Whether this RECORD is what earns the steward an auto-approved unattended turn.

    Deliberately the same predicate ``steward_runtime.sync_trust`` grants on, read off
    the record rather than restated, so the grant and the revocation below cannot
    drift apart: whatever stops being true here is a grant that has to go. That is
    why it is ``unattended`` AND ``is_live`` and not ``unattended`` alone — turning
    unattended off, disabling the steward and pausing it through a patch all withdraw
    the same grant, and a check written against one field would miss the other two.
    """
    return bool(steward.get("unattended")) and steward_runtime.is_live(steward)


async def _handle_steward_update(request: web.Request) -> web.Response:
    """PUT /steward {"owner","repo","id", ...patch} -> {"steward"}.

    Merges a validated patch. A rename re-checks uniqueness in the store (409) and
    leaves ``avatar_seed`` alone, so the steward keeps its face. Allowed on a retired
    steward: correcting an archived record touches nothing live.

    A patch that withdraws auto-approval (``unattended`` true -> false, or an
    ``enabled``/``paused_reason`` patch that stops the steward) REVOKES before it
    answers, for the reason :func:`_revoke_execution` gives: persisting the flag
    reaches neither the ``SafetyOverride`` grant nor the loop, so an already-armed
    nudge firing before the watchdog's next sweep would take one whole auto-approved
    turn under a setting the human had already switched off.
    """
    body, key, early = await _body_preamble(request)
    if early is not None:
        return early
    steward_id = routes._str_field(body, "id")
    before, missing = await _require_steward(key, steward_id, must_be_live=False)
    if missing is not None:
        return missing
    # Sampled from the pre-update record, because the patch is not the transition:
    # ``unattended: false`` on a steward that was already attended must not revoke
    # (there is nothing to revoke and the log line would claim a stop that never
    # happened), and a patch that omits the field must leave a live grant alone.
    was_armed = _auto_approve_armed(before)
    steward = await routes._st(
        key, steward_store.update_steward, key.owner, key.repo, steward_id, body
    )
    if was_armed and not _auto_approve_armed(steward):
        withdrawn = "unattended off" if not steward.get("unattended") else "not live"
        await _revoke_execution(request, steward, withdrawn)
    return web.json_response({"steward": steward})


async def _handle_steward_retire(request: web.Request) -> web.Response:
    """DELETE /steward {"owner","repo","id"} -> {"steward"} — RETIRE, not delete.

    The record, its name reservation and its work log all survive: the name still
    appears in check-in comments the steward left on the forge, so reusing it would
    make an old comment look like a live claim. Idempotent — retiring a retired
    steward re-stamps it rather than 409ing, so a double-click is not an error.
    """
    body, key, early = await _body_preamble(request)
    if early is not None:
        return early
    steward_id = routes._str_field(body, "id")
    _steward, missing = await _require_steward(key, steward_id, must_be_live=False)
    if missing is not None:
        return missing
    steward = await routes._st(key, steward_store.retire_steward, key.owner, key.repo, steward_id)
    await _revoke_execution(request, steward, "retired")
    routes._audit("steward_retire", f"{key.slug}:{steward_id}", "ok")
    return web.json_response({"steward": steward})


async def _revoke_execution(
    request: web.Request, steward: dict[str, Any], reason: str
) -> None:
    """Un-arm a steward the human just stopped, BEFORE the route answers.

    Writing the record is not stopping the steward. Its autonudge loop is a live timer
    in another service and its slot still carries ``_trust``, and nothing in
    ``enabled``/``paused_reason``/``retired_at``/``unattended`` reaches either one —
    the watchdog does, on the app's poll interval. So a route that returned after the
    store write left a window in which an idle timer fires and the steward takes one
    more auto-approved, unattended turn after a human pressed stop. Revoking here
    closes it; :func:`steward_runtime.revoke_steward_execution` documents the two grants
    and stays the watchdog's backstop as well.

    Never raises. The durable state is already written and correct, so a failure to
    reach in-memory state must not turn a successful pause into a 500 — and the
    watchdog re-revokes on its next cycle.
    """
    state = request.app.get("state")
    if state is None:
        return
    try:
        await steward_runtime.revoke_steward_execution(state, steward, reason)
    except Exception:
        logger.warning(
            "steward %s: revoking execution after %s failed",
            steward.get("id"),
            reason,
            exc_info=True,
        )


# ── work items (the stewards' own write path) ───────────────────────────────


async def _handle_steward_work(request: web.Request) -> web.Response:
    """PUT /steward/work {"owner","repo","steward_id","number", ...patch, "event",
    "event_kind"} -> {"item","event"}.

    THE route a steward writes its progress through, and the one the MCP write tool
    targets. It upserts the work item AND appends one ledger line in a single
    call, which is the whole point: a phase cannot change without a logged reason,
    because there is no route that changes one without the other.

    ORDER MATTERS and is: validate the log line -> write the item -> index a skip
    -> append the line. Validating the kind and text FIRST means the store's own
    refusals, including the second-editing-item 409, all happen before anything is
    appended. Appending first would be worse: a store refusal would leave the
    ledger asserting a change that never happened, and a lie in an append-only log
    cannot be taken back.

    ORDER IS NOT ENOUGH, though, and the request is ALL-OR-NOTHING: three durable
    writes to three files cannot be made atomic by any permutation, so a later write
    that fails rolls the earlier ones back before the error goes out. That is one
    transaction under one lock, and it lives in ``steward_store.commit_work_progress``
    — the store owns the file layout and the locks, and a rollback whose target
    another writer can move while it is held is a lost update rather than a
    rollback. This route contributes the two things only a request knows: the
    fields to patch, and the prose a pass is recorded with.

    THE SKIP INVARIANT. A patch that sets ``phase`` to ``skipped`` indexes the pass
    repo-wide in the same transaction, so it is not possible to skip an issue
    without indexing it. Nothing in the app writes a phase except through this
    route, and the route cannot write one without handing the store a reason.

    ``skip_scope`` is OPTIONAL and defaults to ``other``. Requiring it would break
    every existing caller of this route for a field that is only a filter label.

    Identity follows the same two-caller rule as ``GET /steward``: an agent's
    ``owner``/``repo``/``steward_id`` come from its session, and a body that names a
    different steward is refused rather than honoured. Without that, everything the
    read leg does to keep a steward inside its own ledger would be undone one route
    later — the write is where the damage would be.
    """
    if request.get("internal_auth"):
        body, early = await _json_object(request)
        if early is not None:
            return early
        key, steward, early = await _session_identity(
            request,
            {
                "owner": routes._str_field(body, "owner"),
                "repo": routes._str_field(body, "repo"),
                "id": routes._str_field(body, "steward_id"),
            },
        )
        if early is not None:
            return early
        steward_id = str(steward.get("id") or "")
    else:
        body, key, early = await _body_preamble(request)
        if early is not None:
            return early
        steward_id = routes._str_field(body, "steward_id")

    # Reusing the PR field parser rather than copying its bound: the bound is the
    # point (the number becomes a FILENAME), and a second copy is how one of them
    # ships without it. Its out-of-range text says "pull-request number", which is
    # cosmetically wrong here and only reachable past 1e9.
    number, number_error = routes._pr_number_field(body)
    if number_error is not None:
        return number_error

    event_text, too_long = routes._pr_body_field(body, "event")
    if too_long is not None:
        return too_long
    if not event_text:
        return web.json_response(
            {"error": "'event' is required — a work-item write must say why",
             "code": "event_required"},
            status=400,
        )
    event_kind = routes._str_field(body, "event_kind")
    if event_kind not in steward_store.EVENT_KINDS:
        return web.json_response(
            {"error": f"'event_kind' must be one of {', '.join(steward_store.EVENT_KINDS)}",
             "code": "invalid_event_kind"},
            status=400,
        )

    _steward, missing = await _require_steward(key, steward_id, must_be_live=True)
    if missing is not None:
        return missing

    patch = {field: body[field] for field in _WORK_PATCH_FIELDS if field in body}
    # The route derives the pass's PROSE (only it has the request body); the store
    # owns the coupling — a non-`None` reason is what makes the transaction index
    # one, in the same call and under the same lock as the item and the line.
    skip_reason: str | None = None
    if str(patch.get("phase") or "") == "skipped":
        skip_reason = _skip_reason(body, event_text)
    committed = await routes._st(
        key,
        steward_store.commit_work_progress,
        key.owner,
        key.repo,
        steward_id,
        number,
        patch,
        event_kind,
        event_text,
        skip_reason=skip_reason,
        skip_scope=routes._str_field(body, "skip_scope"),
    )
    return web.json_response(committed)


def _skip_reason(body: dict[str, Any], event_text: str) -> str:
    """The prose the shared index stores for a pass.

    Prefers the explanation the steward wrote as an explanation — ``reason``, then the
    work item's own ``why`` — and falls back to the progress line, which is
    mandatory on any phase write and so is always present. The fallback is what
    makes the index never hold an entry with an empty reason: an indexed number
    with no ``reason`` tells the next steward to skip without telling it why, which is
    the one shape of this record that is worse than not having it.
    """
    for field in ("reason", "why"):
        text = routes._str_field(body, field)
        if text:
            return text
    return event_text


async def _handle_steward_pause(request: web.Request) -> web.Response:
    """POST /steward/pause {"owner","repo","id","paused", "reason"?} -> {"steward"}.

    ``paused`` is the request's own verb rather than a raw ``enabled`` patch, so
    the caller cannot half-express the state: pausing stores the reason, resuming
    CLEARS it. A stale reason on a running steward is worse than none — the page
    would show a live steward explaining why it is stopped.

    Pausing also REVOKES execution before answering (see :func:`_revoke_execution`);
    resuming does not re-arm here, because the watchdog relaunches a live steward on
    its next cycle and doing it twice would arm two loops for one slot.
    """
    body, key, early = await _body_preamble(request)
    if early is not None:
        return early
    paused = body.get("paused")
    if not isinstance(paused, bool):
        return web.json_response(
            {"error": "'paused' must be a boolean", "code": "invalid_paused"}, status=400
        )
    steward_id = routes._str_field(body, "id")
    _steward, missing = await _require_steward(key, steward_id, must_be_live=True)
    if missing is not None:
        return missing
    steward = await routes._st(
        key,
        steward_store.set_steward_paused,
        key.owner,
        key.repo,
        steward_id,
        paused,
        routes._str_field(body, "reason"),
    )
    if paused:
        await _revoke_execution(request, steward, "paused")
    routes._audit("steward_pause", f"{key.slug}:{steward_id}:{'on' if paused else 'off'}", "ok")
    return web.json_response({"steward": steward})


# ── the steward fabric (pipeline view) ──────────────────────────────────────


def _fabric_page(owner: str, repo: str, root: Any) -> dict[str, Any]:
    """The ``items`` half of ``GET /steward/fabric``, computed in ONE off-loop call.

    The provider gate is NOT here — it is the route's, because a non-GitHub repo
    still answers 200 with an empty list and this helper is only reached once the
    repo is known to be steward-bearing. Kept parallel to ``_stewards_page`` /
    ``_steward_page``: one off-loop hop that reads every steward's items and the ledger,
    rather than a hop per steward.
    """
    return {
        "schema": steward_store.FABRIC_SCHEMA,
        "phases": list(steward_store.SPINE_PHASES),
        "items": steward_store.fold_fabric(owner, repo, root),
    }


async def _handle_steward_fabric(request: web.Request) -> web.Response:
    """GET /steward/fabric?owner&repo -> {schema, owner, repo, provider, host,
    generated_at, phases[], items[]} — the pipeline view's whole payload.

    Cookie-authenticated browser only, gated on the repo being CONNECTED, exactly
    like ``GET /stewards``: no write gate (it is a read) and no agent reachability (it
    is not in ``_AGENT_REACHABLE``, so ``_agent_gate`` refuses an internal-secret
    caller).

    Non-GitHub providers answer ``items: []`` at HTTP 200, not an error: stewards are a
    GitHub-only feature today, so a GitLab repo simply has no stewards to fold, and the
    frontend renders the same designed empty state it renders for a GitHub repo that
    never ran one. A repo with no stewards answers the same way, from the fold itself.
    """
    key, early = await _query_preamble(request)
    if early is not None:
        return early
    if key.is_github:
        page = await asyncio.to_thread(
            partial(_fabric_page, key.owner, key.repo, routes._scope(key))
        )
    else:
        page = {"schema": steward_store.FABRIC_SCHEMA, "phases": list(steward_store.SPINE_PHASES), "items": []}
    return web.json_response(
        {**routes._identity(key), "generated_at": store._now_iso(), **page}
    )


# ── repo-wide protocol settings ─────────────────────────────────────────────


async def _handle_stewards_settings_get(request: web.Request) -> web.Response:
    """GET /stewards/settings?owner&repo -> {"settings"} — the repo-wide claim
    protocol (TTL, the needs-a-human label, commit trailer), defaults filled in on
    read. Repo-wide and not per-steward: two stewards negotiating with different TTLs is
    how a short-TTL steward steals a long-TTL steward's live work, and two stewards labelling
    the same condition differently gives the person answering two queues to watch."""
    key, early = await _query_preamble(request)
    if early is not None:
        return early
    settings = await routes._st(key, steward_store.read_settings, key.owner, key.repo)
    return web.json_response({"settings": settings})


async def _handle_stewards_settings_put(request: web.Request) -> web.Response:
    """PUT /stewards/settings {"owner","repo","settings":{...}} -> {"settings"}.

    The ``{"settings": {...}}`` envelope matches the app's existing ``PUT /settings``
    so the two configuration surfaces do not need different client code.

    No ``revision`` precondition, unlike that route. There it is mandatory because
    the PUT replaces the WHOLE document, so a stale client would erase a field it
    never read. ``write_settings`` MERGES per field under the settings lock, so a
    partial patch cannot discard a key it did not send and there is nothing for an
    optimistic-concurrency check to protect.
    """
    body, key, early = await _body_preamble(request)
    if early is not None:
        return early
    patch = body.get("settings")
    if not isinstance(patch, dict):
        return web.json_response(
            {"error": "'settings' must be an object", "code": "invalid_settings"}, status=400
        )
    settings = await routes._st(key, steward_store.write_settings, key.owner, key.repo, patch)
    return web.json_response({"settings": settings})


# ── the one forge write ─────────────────────────────────────────────────────


async def _handle_issue_comment(request: web.Request) -> web.Response:
    """POST /issue/comment {"owner","repo","number","body"} -> {"comment_id"}.

    Mirrors ``routes._handle_pull_comment``, including its permission gate: the
    shared ``_pr_action_preamble`` (JSON -> owner/repo -> connected ->
    ``_repo_can_write``, which fails closed) and the shared error taxonomy
    (403 for a provider refusal, 502 for anything else upstream). A steward posting a
    check-in comment gets no weaker gate than a human clicking Comment.

    ``add_issue_comment``, not ``add_pr_comment``: this route exists precisely
    because the steward's claim ledger lives on ISSUES, and on GitLab issues and merge
    requests are separate collections with independent numbering — the PR function
    would comment on an unrelated merge request that happens to share the number.

    Returns the comment's ``id`` because the claim protocol needs it: the steward
    stores it as ``claim_comment_id`` and EDITS that same comment on later
    check-ins rather than posting a new one.
    """
    body, key, early = await routes._pr_action_preamble(request, "issue_comment")
    if early is not None:
        return early

    number, number_error = routes._pr_number_field(body)
    if number_error is not None:
        return number_error
    text, too_long = routes._pr_body_field(body)
    if too_long is not None:
        return too_long
    if not text:
        return web.json_response(
            {"error": "'body' is required", "code": "body_required"}, status=400
        )

    target = f"{key.slug}#{number}"
    client = provider.client_for(key)
    try:
        result = await asyncio.to_thread(
            partial(
                client.add_issue_comment, key.owner, key.repo, number, text,
                **provider.call_kwargs(key),
            )
        )
    except routes.GhCliError as exc:
        return routes._pr_action_error("issue_comment", target, exc)

    await asyncio.to_thread(
        partial(_drop_issue_detail_cache, key.owner, key.repo, number, routes._scope(key))
    )
    routes._audit("issue_comment", target, "ok")
    return web.json_response({
        **routes._identity(key),
        "number": number,
        "comment_id": result.get("id"),
        "url": result.get("url"),
    })


# ── registration ────────────────────────────────────────────────────────────


def register_steward_routes(app: web.Application) -> None:
    """Register the steward routes. Called from ``routes.register_routes``.

    Three wrappers, outermost first. ``routes._require_enabled`` is not optional
    and not inherited from anywhere: routes are registered ONCE at gateway startup
    and Issue Radar is ``defaultEnabled: false``, so an unwrapped handler stays
    callable while the app is switched off. ``_agent_gate`` then refuses an
    internal-secret caller on every route but the two an agent's MCP tools need.
    ``_steward_conflict`` is innermost so a store invariant surfaces as 409 rather
    than 500.
    """
    def _add(method: str, path: str, handler) -> None:
        app.router.add_route(
            method,
            f"{_BASE}{path}",
            routes._require_enabled(_agent_gate(method, path, _steward_conflict(handler))),
        )

    _add("GET", "/stewards", _handle_stewards_list)
    _add("POST", "/stewards", _handle_steward_create)
    _add("GET", "/stewards/names", _handle_steward_names)
    _add("GET", "/stewards/settings", _handle_stewards_settings_get)
    _add("PUT", "/stewards/settings", _handle_stewards_settings_put)
    _add("GET", "/steward", _handle_steward_read)
    _add("GET", "/steward/fabric", _handle_steward_fabric)
    _add("PUT", "/steward", _handle_steward_update)
    _add("DELETE", "/steward", _handle_steward_retire)
    _add("PUT", "/steward/work", _handle_steward_work)
    _add("POST", "/steward/pause", _handle_steward_pause)
    _add("POST", "/issue/comment", _handle_issue_comment)
