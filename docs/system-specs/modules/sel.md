# Security Event Log (SEL) Module

## Overview

Immutable, tamper-evident audit trail for all tool invocations, MCP calls, and dashboard API mutations. Implements transactional event logging.

See also the SEL section in [`security.md`](security.md) for the threat-model view of these events.

Storage: `~/.warding/security_events.jsonl` (append-only JSONL with HMAC-SHA256 chain).

## Event Schema

Each entry records:

| Field | Description |
|-------|-------------|
| `event_id` | Unique 16-char hex identifier |
| `timestamp` | ISO 8601 UTC |
| `event_type` | `tool_invocation`, `api_access`, `config_bounds_clamped`, `governance_decision`, `governance_degraded` |
| `caller_identity` | Session key (e.g. `dashboard:abc`, `cron:xyz`, `subagent:123`). API-access events from mixed-internal endpoints that validate `X-Internal-Caller` (the chat folder writes) carry the internal caller's declared **component name** here — e.g. `warding-dashboard`, or `unknown-internal` for an authenticated internal caller that declared no recognized name (a defined, warned state, not log corruption); `source` stays in the interface vocabulary (`mcp`) for those events |
| `agent` | Agent name (`warding`, custom agent name) |
| `source` | Interface: `slack`, `dashboard`, `cli`, `cron`, `subagent`, `taskrunner`, `mcp`, `background`, `acp` (ACP-transport events, e.g. `tool_interrupted`), `token_auth` / `refresh_tokens` (dashboard auth), `host` (the `_host` sentinel — an in-process host action like app activation / workspace admission), `unknown` (empty/unrecognized session key, which must NOT be mis-tagged `slack`). This is a closed interface vocabulary — component attribution does not extend it; see `caller` below |
| `operation` | Tool name or `METHOD /api/path` |
| `tool_kind` | Tool category (`execute_bash`, `fs_write`, `mcp_core`, `mcp_cron`, etc.) |
| `outcome` | `invoked`, `auto_approved`, `approved`, `rejected`, `denied`, `completed`, `failed`, `clamped`, `degraded` (a governance chokepoint failed OPEN), `one_shot_completed` (a one-shot cron consumed by its own completion — an automated removal, not an operator delete) |
| `resources` | Affected resources summary (redacted, then truncated to 500 chars — see `metadata`) |
| `downstream_service` | MCP server name if applicable (`warding-core`, `warding-cron`, `corp-mcp`) |
| `request_id` | ACP permission request ID |
| `error` | Error message if failed/denied |
| `prev_hash` | HMAC of previous entry (chain link) |
| `entry_hash` | HMAC-SHA256 of this entry |
| `metadata` | Additional context (approval reason, step index, etc.). Free-form string values are **redacted at write time**: the writer applies `security.redact` (credential + exfiltration-URL passes) to string values at any nesting depth before the entry is hashed and persisted, so caller-supplied text (a search query, a document title) never lands a secret on disk. Keys and non-string values pass through; the caller's dict is never mutated (the writer redacts a copy). The same write-time pass covers the free-form top-level strings `operation` / `resources` / `error` (an exception message can quote a command body or URL); identity-shaped fields (`caller_identity`, `agent`, `source`, `downstream_service`, `request_id`) are constrained vocabularies and stay verbatim. Where a `log_*` helper CLIPS a field to 500 chars it redacts first and clips second: clipping first can cut a credential in half, and the surviving prefix matches no full-token grammar, so the writer's pass could not recover it. The HMAC chain signs the redacted bytes |

The `config_bounds_clamped` event (`outcome=clamped`, `source=background`, `operation=config.load`, `caller_identity=config_loader`) is emitted by `config/loader.py`'s `_log_config_clamp_event` when an out-of-range security-bounded knob (`agent.subagent_auto_max` / `agent.max_subagents` / `agent.subagent_max_turns` / `session.pool_size`) is clamped to its API-enforced ceiling at load time, recording `metadata` `{file_value, clamped_to, min, max}`. Best-effort: a SEL failure never makes config loading raise.

## Integrity

- HMAC-SHA256 chain: each entry signs over the previous entry's hash
- HMAC key: `~/.warding/trust/sel_hmac.key` (32 random bytes, `chmod 600`, inside an owner-only `trust/` dir, `chmod 700`). The key deliberately lives OUTSIDE the log's directory: an actor who can rewrite the log dir must not also be able to read the key and re-sign a clean-looking chain that `verify_integrity()` accepts. A legacy key at `~/.warding/sel_hmac.key` is migrated in atomically (`os.replace`) on the next `SecurityEventLog` init — same key bytes, so every existing chain still verifies without re-signing; if BOTH paths exist, the LEGACY key wins and overwrites the destination: `trust/` was not deny-listed before the migration release, so a file already at the destination on a legacy install is untrustworthy (agent-plantable), while the legacy leaf was deny-list-protected all along; a linked `trust` dir or key file is likewise removed (link only, never its target) before use. `sel_hmac_key_path()` reports the RESOLVED path in use, so `session_pid_sig` follows automatically. A read-only config dir that blocks creating `trust/` keeps signing with the legacy file (chain continuity beats relocation). Rollback caveat: downgrading the binary after migration mints a fresh key at the legacy path; on re-upgrade that legacy key wins and replaces the trust-dir key, so chain entries signed BEFORE the downgrade will no longer verify — restore a consistent key from backup around a downgrade if chain continuity matters.
- **Key + log are on the sensitive-path floor:** the `trust` directory (whole-dir entry), the legacy `sel_hmac.key` leaf, and `security_events.jsonl` are in `security._SENSITIVE_HOME_DIRS`, so the audited agent's `fs_read`/file-edit tools (gated by `is_sensitive_path()`) cannot read the key to forge the chain or rewrite the log. The gateway's own writer/reader (`sel.py`, `dashboard/session_health.py`) opens the files directly and bypasses that gate. Residual: the key still lives in the agent's home namespace — a deeper out-of-process signer is future hardening.
- **Read paths pin the segment directory:** the read-side readers (`recent`, `verify_integrity`) open `security_events.d` itself through `_open_segment_dir` before enumerating; a directory that refuses to pin — planted link, non-directory, or vanished — contributes NO segments to any read (fail closed; a missing dir was already "no segments"), instead of being walked by name. Enumeration stays the bounded `_SEGMENT_SCAN_CAP` walk on every platform, but where the pin carries a descriptor it goes through `os.scandir(pin.fd)` — a path swap can neither redirect nor empty the scan (immune to the swap-mid-read-then-restore shape) — and only the identity-pin platform revalidates the directory's identity after the walk, failing closed on a mismatch. Where directory descriptors exist, every per-file open (`_open_segment` with `dir_fd`) also resolves RELATIVE to the pinned descriptor, so a swap after enumeration still cannot redirect a read; Windows has no directory descriptors, so its pin revalidates the directory's `lstat` `(st_dev, st_ino)` identity before each child open instead, with the residual between revalidations bounded by the rotation-time repair (`_ensure_segment_dir` unlinks a linked segment dir at rotation/prune). The per-file funnel (`O_NOFOLLOW`/`O_NONBLOCK`, descriptor `fstat` regular-file check, name↔descriptor identity) is unchanged, and the LIVE log is never pinned: its writer follows an operator's symlink, so its readers must too. Because the swap is itself tampering, `verify_integrity(detailed=True)` reports a THIRD outcome — `history_verifiable=False` with a `reason` — when the directory refused to pin (planted link, not a directory, an actual directory the OS refused to open, or one that vanished between the pin's `lstat` and its open — every pin failure except ABSENCE confirmed at first sight) or was replaced mid-verification, and the CLI (`warding security verify`) and `GET /api/sel/verify` surface it (`Audit history UNVERIFIABLE` / `integrity: "unverifiable"`) instead of reporting intact over the live log alone; the CLI derives its live-log clause from the same pass's counts, so a tampered live log is reported as such rather than "intact". A directory that simply does not exist yet (fresh install) stays verifiable.
- Verification: `verify_integrity()` walks the chain and reports tampered entries
- Append-only: no in-place edits; pruning rewrites with chain rebuild
- **Second protocol anchored on this key — domain-separated:** `session_pid_sig.py`
  authenticates the `session_pid_<pid>.txt` -> session-key mapping consumed by
  strict MCP identity resolvers. It does **not** sign with the raw
  `sel_hmac.key`; it derives a purpose-specific subkey
  (`HMAC(sel_hmac.key, "warding.session_pid.sig.v1")`) so the sidecar MAC and
  the SEL audit chain never share a signing key — a MAC minted under one
  protocol is valueless to the other (no cross-protocol confusion/replay). The
  key file remains a single on-disk trust root; only `SecurityEventLog` ever
  *creates* it. **Recorded acceptance — widened compromise impact:** anchoring
  session identity here means compromise of `sel_hmac.key` no longer only
  permits forging the audit chain — it also permits minting valid
  session-identity sidecars and driving state-mutating MCP tools against
  another session (cross-session state mutation). The likelihood of compromise
  is unchanged (same sensitive-path floor); the *impact* grew, and any future
  hardening of this key (the out-of-process signer above) must
  treat `session_pid_sig` as a dependent of equal weight. See
  `docs/system-specs/modules/session.md` for the sidecar contract.

## Async Writer

`log()` is off the hot path: callers enqueue the event on an unbounded
`queue.Queue` (never blocking) and a single daemon writer thread drains it,
computing the HMAC chain in enqueue order and batching up to `_QUEUE_DRAIN_BATCH`
events into one `open()`+write. The writer starts lazily on first `log()` and
registers an `atexit` flush.

- **Durability**: eventually-durable, not synchronously-durable — a crash/kill
  can lose at most the events still queued. Acceptable for an audit log; the
  hot path (e.g. per-message skill triggering) no longer pays fsync/lock latency.
- **Read-after-write**: `flush()` runs before every read path (`recent`,
  `verify_integrity`, `prune`) and on exit. It waits on a pending-event counter
  (a `threading.Condition`, race-free vs a bare queue-empty check), bounded by
  `_FLUSH_TIMEOUT_SECS` so a wedged writer can't hang a read.
- **Fallback**: if the writer can't be started, `log()` writes synchronously so
  an event is never silently dropped.
- **`sync=True`**: `SecurityEventLog(base_dir=..., sync=True)` writes each event
  inline (no thread) — used by tests that read the raw JSONL immediately after
  logging.

## Retention

Default 365 days. Pruned daily by heartbeat service (`_PRUNE_TICKS`).

## Integration Points

| Surface | What's Logged | Module |
|---------|---------------|--------|
| Slack handler | `tool_call` (invoked/denied), `permission_request` (all outcomes) | `slack/handler.py` |
| Dashboard chat | `tool_call` (invoked), `permission_request` (all outcomes) | `dashboard/chat.py` |
| TaskRunner | Permission requests during decomposition and step execution | `taskrunner.py` |
| Subagent | Permission requests during subagent execution | `subagent.py` |
| Background tasks | Permission requests via `_resolve_permission()` | `llm_helpers.py` |
| MCP core tools | `spawn_run`, `learn_add`, `task_run` calls and outcomes | `mcp_core.py` |
| MCP cron tools | `cron_add`, `cron_remove`, etc. calls and outcomes | `mcp_cron.py` |
| Dashboard API | All POST/PUT/DELETE operations via middleware, plus allowed and denied project-skill trust and app-slot authorization decisions | `dashboard/server.py`, `dashboard/handlers/prompts.py` |
| ACP worker-pool audit | Per-`tool_call` `auto_approved` `tool_invocation` (`source=subagent`), bounded by `_SEL_AUDIT_TIMEOUT_SECONDS` (5.0s) and offloaded off the event loop so a wedged SEL backend never gates dispatch. Two emitters: the knowledge LLMPool via `AcpClient._maybe_audit_tool_call` (gated on the `audit_source` ctor param, offloaded to `subprocess_executor()`); and **code-review-sage's ReviewPool**, which migrated to the shared `AcpRuntime` (no `audit_source`) and re-emits the same per-tool record itself | `acp/client.py`, `apps/builtins/code_review_sage/sage_lib/review_pool.py` |
| Token auth | `internal_auth`, `app_scope_check`, `dashboard_sessions_revoked`, `refresh_token_initial_mint`, `nonce_evicted` (`source=token_auth`) | `dashboard/token_auth.py` |
| Refresh tokens | `refresh_token_use`, `refresh_token_logout`, `access_cookie_revoked` (`source=refresh_tokens`) | `dashboard/handlers/auth_refresh.py` |
| ACP transport | `tool_interrupted` per-turn cancellation audit (`source=acp`) | `acp/client.py` |

## APIs

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/sel/events?limit=N` | Recent security events (max 1000) |
| GET | `/api/sel/verify` | HMAC chain integrity check |

## CLI

```
warding security events [-n 20]   # Show recent events
warding security verify            # Verify HMAC chain integrity
```

## Thread and Process Safety

Singleton pattern. The chain state (`_last_hash`) and the file append are
guarded by `threading.Lock`, held only inside the writer thread (and the
synchronous fallback / `prune`), never by enqueuing callers. Enqueue is
lock-free via the thread-safe `queue.Queue`.

The gateway, the CLI, cron and the MCP stdio processes (`mcp_core.py`,
`mcp_cron.py`, `cron_script.py`) all append to one log. A thread lock does not
cover them, so every append also takes a cross-process lock.

- **Chain lock.** The lock file is `security_events.d/.chain.lock`. The segment
  directory is on the sensitive-path floor, so the audited agent cannot open the
  file to starve the writer. The writer takes the lock through
  `platform_compat.try_acquire_lock_strict` before `_lock`. It holds the lock
  across "re-read the tip if the log moved, chain, append". Rotation runs inside
  the same hold.
- **Lock order.** Chain lock first, then `_lock`, then the rotation lock. No path
  takes them in another order.
- **Hold time.** An append holds the lock for one stat, one tail read and one
  write. Rotation holds it for a bounded directory scan (`_SEGMENT_SCAN_CAP`), a
  rename and a retention sweep. `prune` holds it only for its final swap (see
  below), never for the full-file pass.
- **Bounded wait.** A worker thread polls (sleeping `_CHAIN_LOCK_POLL_SECS`, 0.5
  ms) and gives up after `_CHAIN_LOCK_TIMEOUT_SECS` (10 s). `prune` has its own
  budget, `_CHAIN_LOCK_PRUNE_TIMEOUT_SECS` (60 s), because it runs on the
  maintenance executor and a wait there costs nothing. A thread that runs an event
  loop (an inline `critical=True` audit) polls with the same sub-millisecond
  sleeps for at most `_CHAIN_LOCK_LOOP_BUDGET_SECS` (20 ms). An append holds the
  lock for well under a millisecond, so a collision with another writer clears
  within a few polls. 20 ms is under the 50 ms where a stall becomes visible to a
  person. A lock still busy after the budget is not a collision, so the audit
  fails closed. A busy lock raises `SelChainLockTimeout`, an `OSError`. A critical
  caller denies the action. The background writer drops the batch with a warning.
- **Busy versus broken.** `try_acquire_lock_strict` returns False only for
  contention. Any other lock failure raises `OSError`. Only the errno values in
  `_LOCK_UNSUPPORTED_ERRNOS` (`ENOLCK`, `ENOSYS` under a seccomp filter,
  `EOPNOTSUPP`) mean the filesystem cannot lock. Nobody holds the lock then, so
  waiting cannot help, and the append takes the guarded path below at once, with a
  warning. `try_acquire_lock` keeps its old behaviour for its other callers.
- **Fail closed, not guarded.** Everything else fails the append with the
  original `OSError`: a resource error opening or priming the lock file
  (`_LOCK_FILE_RESOURCE_ERRNOS`: `EMFILE`, `ENFILE`, `ENOMEM`, `ENOSPC`), any other
  lock-call error, and a directory or FIFO planted at `.chain.lock`. Taking the
  guarded path for those would give whoever causes them a switch that turns
  serialization off.
- **Unusable lock file.** A planted link that cannot be removed, or a segment
  directory that cannot be made, takes the guarded path with a warning. It is a
  property of the directory, not of the process. `SelChainLockTimeout` is for
  contention only.
- **Prune.** `prune` does its long work with no append lock:
  - It deletes aged rotated segments without `_lock`. It reads each closed
    segment unlocked and takes `_lock` only around the unlink. An appender that
    holds the chain lock therefore never waits behind a read of several 32 MiB
    files.
  - It streams the live log's survivors to a temp file, then takes the chain
    lock, `_lock` and the rotation lock for a short swap: check that the live log
    is the file it read, copy the bytes appended since, `fsync` the temp file, and
    replace the log. The wait for the rotation lock is bounded by
    `_PRUNE_ROTATION_LOCK_TIMEOUT_SECS` (5 s), because the swap already holds the
    other two locks. On a timeout the sweep is retried on the next run.
  - If another process rotated the log (or renamed it before recreating it)
    meanwhile, the swap is skipped and prune returns without error.
  - If re-reading the chain tip fails after the replace, prune still reports the
    removed count. The tip is marked unknown, so the next append fails closed
    until it can be read.
  - A prune temp file (`.sel_prune_*.tmp`) older than `_PRUNE_ORPHAN_AGE_SECS`
    (1 h) is an orphan from a crashed prune, and the next prune deletes it.
- **Identity guard (kept).** The append still checks the opened file's identity
  and re-chains on a mismatch (`_LiveLogReplaced`, `_APPEND_RETRIES`,
  `SelChainContention`). It covers a writer that does not hold the chain lock:
  an older build during an upgrade, or a foreign replacement of the file.

### Chain tip

`_read_last_hash` returns `""` only for an ABSENT log, or a log with no parseable
record. A failed read of an existing log (permission error, I/O error) raises
`SelTipUnknown`, an `OSError`. The append then fails closed through the same
paths as an unwritable log. It never restarts the chain from genesis. The HMAC
chain format and the key location are unchanged.

If the tip is unreadable at start-up, `_tip_known` stays False. The next append
re-reads the tip under the chain lock and fails closed while it is unreadable.

### Verified behaviour

Two processes appended 500 events each at once to a fresh data home, with a
seeded HMAC key. Before the lock, `verify_integrity` reported 410–462 of about
1000 records off the chain, and some events were dropped with
`SelChainContention`. After the lock, all 1000 records verify.

Tests in `test/test_sel.py`: `TestCrossProcessChain` (concurrent processes,
unreadable tip) and `TestChainLockBehaviour` (busy lock times out, lock error is
not polled, the strict helper, a brief collision on an event-loop thread
succeeds, a held lock fails closed within the loop budget, prune keeps late
appends). `TestPruneAndLockHardening` covers the review fixes: the segment sweep takes no
thread lock while reading, a vanished live log, fail-closed lock errors (`EMFILE`, `EBADF`, a
descriptor-starved open, a planted directory), the bounded rotation-lock wait, the count after
a failed re-anchor, `fsync` before the replace, and orphan cleanup. Not tested: Windows, Linux, rotation under concurrent processes, and
an older build writing at the same time.
