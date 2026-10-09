# Task Runner

The task runner executes multi-step autonomous tasks from spec files. It's
useful for complex workflows that need structured execution with progress
tracking.

## Running a Task

### Via Chat

```
run docs/task-specs/2026/03/my-task/spec.md
```

Or ask naturally: "run the task in my-task/spec.md"

### Via Dashboard

Tasks page → enter the spec file path → click ▶ Start.

### Via Slack

```
run <path-to-spec>
run status
run cancel
```

### Via MCP Tool

The `task_run` MCP tool accepts a spec file path or inline content:

```
task_run(spec="path/to/spec.md")
task_run(spec="__inline__: Step 1: do X\nStep 2: do Y")
```

## Spec File Format

Task specs are markdown files with structured steps:

```markdown
# Task: Implement Feature X

## Steps

1. Read the current implementation in `src/module.py`
2. Add the new function `process_data()`
3. Write tests in `test/test_module.py`
4. Run `pytest` and fix any failures
```

## Tool Approval

Approval depends on how the run was launched:

- **Dashboard / chat `run` / Slack `run`** (inside the gateway): tool calls that aren't allow/deny-listed **prompt** interactively.
- **`warding run TASK.md`** (standalone CLI): no interactive channel, so it's **deny-by-default** — a tool runs only if it matches `hooks.auto_approve_tools`; otherwise it's rejected and logged with `reason: headless_no_authorization`. (`TOOL_DENY` / `auto_deny_tools` always wins; the allowlist works with or without a handler.)

To let `warding run` use tools, allowlist them in `~/.warding/config.json`:

```json
{
  "hooks": {
    "auto_approve_tools": ["read", "Reading *", "Running: pytest *", "fs_write"]
  }
}
```

Patterns match the tool title with or without the `Running: `/`Reading ` prefix and support `*` globs. Titles differ by harness: Claude Code, for example, titles a file write `Write <path>` and a shell call with the command itself, so `fs_write` does not match it but `Write *` does. The exact title of every refused call is the `operation` field of its `headless_no_authorization` row in `security_events.jsonl`. Scope it to the tools the task needs — a blanket `*` re-opens the gap. Or run from the dashboard to approve interactively instead.

A refused call fails the step and the run: the agent cannot finish work it was not allowed to do, and nothing in a headless run can grant the permission, so the runner neither retries nor re-plans. The error names the refused titles.

### Where the work happens

`warding run TASK.md` does not work in the spec's folder. Unless `taskrunner.workspace_dir` is set, each spec gets its own folder under the workspace root (`<workspace>/taskrunner_main/<spec name>/`), and the completion summary prints it. Pass `--workspace DIR` to work in a folder of your choosing; a folder that resolves to a credential location is refused. Progress (`TASK_PROGRESS.md`) is still written next to the spec.

## Progress Tracking

The dashboard shows live step progress with status icons:
- ✅ Completed
- 🔄 In progress
- ❌ Failed
- ⏳ Pending

## Multi-Turn Refinement

After a task completes, you can refine the results interactively:
- The agent can ask clarifying questions
- You can provide additional instructions
- The refinement loop has full tool access

## Per-Agent Tasks

Tasks can specify which agent to use, allowing specialized agents for
different types of work.

## Cancellation

Cancel a running task via:
- Dashboard: ■ Cancel button
- Slack: `run cancel`
- API: `POST /api/taskrunner/cancel`
