# myrmitis/warding — documentation hub

This is the stable index for this owner-controlled repository. Existing source documents and GitHub issues remain authoritative. A source receipt is not a deployment or customer-acceptance record.

| Topic | Canonical reference |
| --- | --- |
| README.md | [README.md](../README.md) |
| PRODUCT.md | [PRODUCT.md](../PRODUCT.md) |
| WORKING_BRIEF.md | [WORKING_BRIEF.md](../WORKING_BRIEF.md) |
| ARCHITECTURE.md | [ARCHITECTURE.md](../ARCHITECTURE.md) |
| ROADMAP.md | [ROADMAP.md](../ROADMAP.md) |
| CHANGELOG.md | [CHANGELOG.md](../CHANGELOG.md) |
| Existing documentation | [Browse docs](./) |
| Open work | [Issues](https://github.com/myrmitis/warding/issues), [pull requests](https://github.com/myrmitis/warding/pulls) |
| Change and release evidence | [Commits](https://github.com/myrmitis/warding/commits), [Actions](https://github.com/myrmitis/warding/actions), [releases](https://github.com/myrmitis/warding/releases) |
| Source receipts | [docs/updates](updates/README.md) |
| Portfolio-wide index | [Portfolio hub](https://github.com/laqaer/portfolio-ops/tree/main/docs/hub) |
| Config write locks: registries PUT ([#65](https://github.com/myrmitis/warding/issues/65), PR [#71](https://github.com/myrmitis/warding/pull/71); review record in [#70](https://github.com/myrmitis/warding/pull/70)) | Rule: [two config locks](system-specs/modules/config.md#two-config-locks). Verification: the concurrent-writer tests in `test/test_e2e_smoke.py`. Revision: the merge commit of PR #71. This is a source fix, not a release. An installed gateway changes only after its own update. |
| Managed-agent PID identity ([#30](https://github.com/myrmitis/warding/issues/30), PR [#77](https://github.com/myrmitis/warding/pull/77); review record in [#72](https://github.com/myrmitis/warding/pull/72)) | Rule: [managed-agent identity](system-specs/modules/session.md#managed-agent-identity). Verification: `test_boot_sweep_keeps_only_records_of_agent_launchers` in `test/test_e2e_smoke.py`, and the macOS acceptance run recorded on PR #77. Revision: the merge commit of PR #77. This is a source fix, not a release. An installed gateway changes only after its own update. |
| Shell favicon route ([#78](https://github.com/myrmitis/warding/issues/78), PR [#80](https://github.com/myrmitis/warding/pull/80); review record in [#79](https://github.com/myrmitis/warding/pull/79)) | Rule: [root files of the build](system-specs/features/dashboard-token-auth.md#root-files-of-the-build). Verification: `test_shell_declared_favicon_is_the_built_svg` in `test/test_e2e_smoke.py`. Revision: the merge commit of PR #80, `f61dab4`, whose main CI run 42425225028 passed. This is a source fix, not a release. An installed gateway changes only after its own update. Installed acceptance (root, 2026-11-07): root updated the installed gateway to `f61dab4`, which runs as PID 23157 from 23:58:39Z. At 23:59:31Z, readiness returned 200, and the dashboard and all 217 assets matched their installed bytes. `/favicon.svg` returned `200 image/svg+xml` with the installed file's bytes, and unauthenticated data returned 403. No visual-browser or signed-in-provider check ran. Evidence: the PR #80 description and main CI run 42425225028. Root keeps the local receipts `work/warding78-install-receipt.json` and `work/warding78-http-receipt.json` in its Codex workspace. |
| Routing cooldown requests ([#86](https://github.com/myrmitis/warding/issues/86)) | Contract: [routing surface](system-specs/modules/harness-router.md). Verification: `test_routing_cooldown_clear_validates_before_writing` drives the gateway over HTTP. The issue links the integration record. |
| Canonical path forms ([#96](https://github.com/myrmitis/warding/issues/96), also closes [#75](https://github.com/myrmitis/warding/issues/75); earlier unsaved work in [#85](https://github.com/myrmitis/warding/issues/85)) | Rule: [canonical path forms](system-specs/modules/security.md#xpia-hardening-securitypy--hookspy) and [path matcher](system-specs/modules/governance.md). Verification: `test/test_canonical_paths.py` (emulated Windows spellings, deny-only governance matching, the nested-argument walker, a symlinked anchor, and the PreToolUse gate on a nested keystone path). This is a source change, not a release. Native Windows gateway acceptance is NOT RUN. An installed gateway changes only after its own update. |

For each material change, update the affected canonical document and link the issue, PR, revision and verification. Distinguish implemented, merged, deployed, verified and released. Follow the [shared documentation standard](https://github.com/laqaer/agent-config/blob/main/docs/documentation-hub.md).
