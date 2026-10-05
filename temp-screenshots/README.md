# temp-screenshots/

This directory holds **PR review evidence**: screenshots and GIFs captured
while preparing a pull request, not product assets. Nothing here ships in a
package, a wheel, or the desktop app.

## Why these are committed rather than attached

The `user-attachments` mechanism (drag-and-drop upload in the GitHub web UI)
renders fine in a PR description, but nothing in an automated PR workflow, CI
or CLI, can produce an attachment that way. Committing the file and linking it
with a commit-SHA-pinned URL is reachable from a script:

```
https://github.com/<owner>/<repo>/raw/<sha>/temp-screenshots/<feature>/<name>.png
```

Committing also makes the image part of the change, so anything that reviews
the PR from the repository can open it: a reviewer browsing the files, or a
local reviewer reading the checkout. An attachment cannot offer that because it
is not a file in the repository. The images remain the durable record for human
reviewers.

## Naming

`temp-screenshots/<feature>/<name>.png` (or `.gif`, `.mp4`), one subdirectory
per feature or PR.

Reference it from the PR body with the commit SHA pinned, and **re-pin the SHA
after every amend or rebase**: the pinned URL only resolves the commit it
names, so an amended commit's old URL breaks.

## Lifecycle

`.github/workflows/cleanup-temp-screenshots.yml` prunes files older than the
retention window (14 days) weekly, opening a PR because `main` is protected.
Committed blobs stay reachable in git history by design even after the tip is
pruned, so an already-published PR description's pinned URL keeps resolving:
pruning the tip never breaks a past PR's images.

**Authors should not delete their own files before merge, and reviewers
should not ask them to.** The scheduled cleanup job is the only thing that
removes files here.

## See also

No application code imports these files, but the path itself is referenced by
three shipped skills under `src/junction/`, which are what tell an author or
agent to write here in the first place:

- `builtin_skills/junction-dev/prepare-pr/SKILL.md` — read before a PR body
  is written (directs agents to read `.github/PULL_REQUEST_TEMPLATE.md`).
- `apps/builtins/dev_fleet/skills/pod-e2e/SKILL.md` — the operational recipe:
  copy the media in, amend into the PR's single commit, force-push, then verify
  the body update landed.
