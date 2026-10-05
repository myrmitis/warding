# rich fixture

Fully-populated `$JUNCTION_HOME`: everything `minimal` ships **plus**
three extra chat sessions, a folder grouping two of them, and an
archived session slice. Mirrors a heavily-used real user home without
any personal data. Useful as the demo fixture for UX screenshots and
as the e2e target for dashboard tests that need folder tree / History
panel / archive retention paths to be non-empty.

Running `junction gateway --seed rich` against a fresh `$JUNCTION_HOME`
lands you on a dashboard where:

- **Sessions** panel shows 3 active slots: pinned **Welcome to Junction**
  + the two demo sessions grouped under the **Demos** folder.
- **History** panel (expanded) shows the closed **Research notes**
  session — 12 msg, old mtime so the cutoff alone would have dropped
  it as a slot but it remains visible in History.
- **Memory** tab populated (workspace + workspace-extra).
- **Crons** tab shows 1 active + 1 paused job.

## Layout

```
rich/
├── fixture.yaml
├── README.md
├── config.json
├── crons.json
├── hooks.json
├── folders.json        # 1 folder ("Demos") grouping coder-demo + triage-demo
├── sessions/
│   ├── dashboard_starter.jsonl        # pinned, default agent, 4 msg (from minimal)
│   ├── dashboard_coder-demo.jsonl     # pinned, junction agent, folder=demos, 8 msg
│   ├── dashboard_triage-demo.jsonl    # default agent, folder=demos, 6 msg
│   ├── dashboard_research-notes.jsonl # closed, default agent, 12 msg (History)
│   └── archive/
│       └── research-notes__20251220-090000.jsonl  # archive slice
├── workspace/          # default workspace (from minimal)
│   └── memory/
│       ├── preferences.md
│       ├── projects.md
│       ├── semantic.md
│       └── history/
│           └── 2026-01-15.md
└── workspace-extra/    # second workspace (from minimal)
    └── memory/
        ├── preferences.md
        └── semantic.md
```

## What's intentionally NOT included

Same omissions as `minimal`: `memory.db` and `memory_index.db` are
bootstrapped empty at first gateway start. Slack state is an orthogonal
feature surface; the fixture focuses on core dashboard content.
