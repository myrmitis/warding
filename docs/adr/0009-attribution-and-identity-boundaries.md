# ADR 0009 — Preserve attribution and functional identity boundaries

- Status: proposed for human review
- Date: 2026-10-14
- Refines: [ADR 0001](0001-product-identity.md) and
  [ADR 0008](0008-product-rename-warding.md)
- Scope: [identity audit #31](https://github.com/myrmitis/warding/issues/31)

## Evidence and attribution

Warding retains derived code. For example, its `harness_router/limits.py`
and the corresponding predecessor file have the same blob
`4b0e4e94f73e62d391bb70063a086767b76e3278` in the inspected revisions.
A clean initial git history is not evidence of independent authorship.

The inspected predecessor is
[revision ee3131d](https://github.com/laqaer/junction/tree/ee3131d8c44b40a78814f087fef625f61d0b6cf9).
Its [NOTICE](https://github.com/laqaer/junction/blob/ee3131d8c44b40a78814f087fef625f61d0b6cf9/NOTICE)
has blob `717c326fc5cdf4028d793dfe6066d5324b96e8a8`.
Both repositories carry the same Apache-2.0 LICENSE blob,
`261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64`.

[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0), sections
4(c) and 4(d), preserves applicable source notices and original-work NOTICE
attribution in distributed derivatives. Section 6 permits customary origin
descriptions and NOTICE reproduction. There is no evidence here that the
original attribution no longer pertains to the retained work.

Preserve the original attribution block verbatim in root `NOTICE`, alongside
the predecessor's Warding modification statement. The explanatory wrapper
names Warding and distinguishes attribution from product identity or endorsement.
The brand gate permits only the exact original product-name line in root
`NOTICE`. The company-name gate permits only the two exact company-attribution
lines in that file. Neither gate exempts the whole file, another path, or
extra prose on an attribution line. A regression test pins the full block.

This is a conservative preservation decision, not an exhaustive provenance
audit or a legal opinion clearing every distribution. Removing applicable
attribution requires substantiated provenance analysis or legal advice; a
branding preference alone does not supply that evidence. This ADR refines
the identity prohibition without changing Warding's public branding.

## Scrub exceptions and security controls

Retire only exceptions that match no findings under the existing scrub
script's actual scope and matching semantics. The inspected allowlist has
56 entries: nine active and 47 inactive. The nine active expressions remain
unchanged; retaining an active exception does not establish that it is the
narrowest possible form. The marker families remain enabled.

Keep `.midway` sensitive-path blocking in backend security and frontend
`safePath`, legacy authentication-store protections, and the internal-host
deployment scanner. These identifiers name security targets, not product
branding. Removing an unused lint exception does not remove its associated
runtime protection. The private employee-alias list is absent in this
checkout, so alias coverage is not verified by the public scan.

## Harness policy and operator configuration

The established Warding default is `agent.acp_backend=auto`, represented by
`ACP_BACKEND_AUTO`. Invalid persisted backend values normalize to `auto`.
The runtime registry selects an installed runtime in its existing order,
with optional kiro-cli last. Reconcile assistant rules, review rules and
the parity gate with that implementation. Preserve positive harness identity,
explicit capability membership and all existing sandbox boundaries.

Routing and chat selection are separate. Disabling a `kiro` lane in
`routing.json` excludes it from routed work; chat auto-selection does not
consult that setting or verify an active subscription. To exclude Kiro from
chat, the operator can explicitly pin an installed, authenticated runtime.
This change does not inspect or alter the operator's private configuration,
claim a successful live harness run, or choose a replacement provider.

## Decisions reserved to the owner

A global ban on Kiro, a new automatic runtime order, or coupling chat selection
to router eligibility would change product behavior. None is implied by a
cancelled subscription or needed for these corrections. Those changes require
an explicit product decision and their own compatibility validation.

The candidate is reversible and follows the feature-branch/PR workflow.
Acceptance and merging remain human actions under
[ADR 0006](0006-agent-os-no-automerge.md); neither auto-merge nor production
deployment is authorized by this record.
