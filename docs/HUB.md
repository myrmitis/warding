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

For each material change, update the affected canonical document and link the issue, PR, revision and verification. Distinguish implemented, merged, deployed, verified and released. Follow the [shared documentation standard](https://github.com/laqaer/agent-config/blob/main/docs/documentation-hub.md).
