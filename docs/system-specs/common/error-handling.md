# Error Handling

## Principles

1. Custom exceptions in `acp/client.py` for ACP-specific errors
2. Error strings at CLI boundaries (never expose tracebacks to users)
3. Graceful degradation — partial output returned on timeout

## Exception Hierarchy

```
AcpError (base)
├── AcpTimeoutError      — prompt timed out, has partial_output
├── AcpPermissionNeeded  — tool approval required (phase 3)
└── AcpProcessDied       — kiro-cli exited unexpectedly
```

## Boundaries

| Boundary | Strategy |
|----------|----------|
| ACP → CLI | Catch `AcpError`, print user-friendly message, `sys.exit(1)` |
| JSON-RPC read | Non-JSON lines silently skipped (kiro-cli debug output) |
| Config load | Invalid JSON → log warning, return defaults |
| Process spawn | `shutil.which` check before spawn; clear error if missing |
| Dashboard HTTP request body | A handler reads the body with `read_json_object` and string fields with `require_str`. `request_boundary_middleware` answers `BadRequestError` and body decode errors with a 4xx JSON body that carries a `code`. Any other exception stays a 500 and is logged. See [learn-cron-dashboard](../modules/learn-cron-dashboard.md#request-boundary-malformed-input-is-a-4xx) |
| asyncio loop callback | A Windows Proactor reset repeated by its `connection_lost` close callback is warning-only; task-level connection resets and other exceptions remain ERRORs with crash breadcrumbs |
