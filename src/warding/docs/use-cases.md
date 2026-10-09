# Use Cases & Workflows

Example workflows that combine Warding's capabilities — cron jobs, subagents,
memory, chat channels, and the task runner — into end-to-end automation.

## Issue Backlog Sweep

Warding works through an issue backlog: it picks up tasks, implements them, runs
tests, opens pull requests, and handles review comments, with you approving the
results rather than driving each step.

```
run docs/task-specs/backlog-sweep.md
```

A typical spec:
1. List open issues in the project's tracker
2. Pick the highest-priority unassigned issue
3. Read the issue description and linked code
4. Implement the change
5. Run the test suite (e.g. `pytest`)
6. Open a pull request targeting the correct branch
7. Move to the next issue

Best paired with `!yolo on` for unattended operation, in a repository whose
branch protection and required reviews you trust.

## Repetitive Refactors

Automate repetitive cleanup across a codebase. Warding reads a config or
feature-flag list, identifies dead code paths, removes them, and opens pull
requests.

## Slack → Issue Intake

Monitor a Slack channel for incoming requests and auto-create issues. Your
coding instance picks them up automatically.

Setup:
1. Set the channel to `observe` mode: `!channel observe`
2. Create a cron job: "Every hour, check #my-channel for new requests and
   create issues for actionable items"
3. Your backlog sweep picks up the new tasks

## Daily Briefings

Schedule morning briefings that summarize what matters:

- "Every weekday at 9am, give me a CI health summary"
- "Every Monday at 8am, list my open pull requests and their review status"
- "Every day at 5pm, summarize today's Slack activity in #my-team"

These run as cron jobs with results posted to your Slack DM.

Use `skip_dates` and `timezone` to skip holidays or vacation days — the next
run automatically covers the gap. See [Cron Jobs](cron-and-scheduling.md#skipping-dates).

## Parallel Research

Fan out research across multiple sources simultaneously:

> "Compare the maintenance activity of these five open-source HTTP client libraries"

Warding spawns subagents — one per library or source — and synthesizes the
results into a single summary.

## Auto-Collect Information

Replace manual information-gathering workflows. Use cron jobs to gather data
from your sources and publish to a dashboard or static site.

## Service Monitoring

- "Every 30 minutes, check my service's health endpoint and alert me if it fails"
- "When I get an alert, pull the last 15 minutes of logs for my service"
- Combine with a custom monitoring skill for issue triage

## Code Review Assistance

Switch to a code-reviewer agent for focused review work:

```
!agent code-reviewer
```

Or set it per-thread in Slack:
```
!ta set code-reviewer
```

The agent reads the pull-request diff, checks for common issues, and posts
review comments.

## Multi-Agent Workflows

Run different agents for different concerns:

| Agent | Purpose | Trigger |
|-------|---------|---------|
| default | General tasks, chat | Always |
| `code-reviewer` | PR review | `!ta set code-reviewer` in review threads |
| `ops-agent` | Incident response | Cron-triggered on alert channels |
| `doc-writer` | Documentation | Per-tab in dashboard |

Each agent has its own system prompt, tools, and skills — scoped via
per-agent MCP configuration.

## Tips

- **Unattended overnight runs**: Use `!yolo on` + task runner for long
  autonomous sessions. Review the PRs in the morning.
- **Workspace isolation**: Use `WARDING_HOME` and `WARDING_PORT` env vars
  to run multiple instances with separate data.
- **Background gateway**: Use a macOS Launch Agent or systemd service to keep
  the gateway running across reboots (see [Getting Started](getting-started.md)).
