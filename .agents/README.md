# Warding agent overlay

Contributor and agent-OS skills for **this checkout**. They are not
packaged. A skill that any shipped feature, tool, or packaged doc
references must live in `src/junction/builtin_skills/`. Top-level
`skills/` is checkout-only and reaches no installed user.

Product overlay: [`../JUNCTION.md`](../JUNCTION.md). Envelope:
[`../WORKING_BRIEF.md`](../WORKING_BRIEF.md).

| Skill | Use when |
|---|---|
| [product-identity](skills/product-identity/SKILL.md) | Naming the product, CLI, tagline, the NO-SAY list, or identifiers that stay. |
| [acp-runtimes](skills/acp-runtimes/SKILL.md) | Touching the ACP runtime registry or `agent.acp_backend`. |
| [model-router](skills/model-router/SKILL.md) | Built-in loopback catalog; health/status; no forwarding. |
| [security-keystone](skills/security-keystone/SKILL.md) | Sensitive paths, governance, computer use, harness identity. |
| [integration-owner](skills/integration-owner/SKILL.md) | Verifying the bootstrap cut; authority envelope. |
| [marketing-site](skills/marketing-site/SKILL.md) | `site/` (Astro) copy, the paper-and-seal / night rules, preview deploy. |
| [dashboard-i18n](skills/dashboard-i18n/SKILL.md) | User-facing dashboard strings; `{{productName}}`. |
| [agent-os](skills/agent-os/SKILL.md) | Scout / implement / review loop; never merge. |
