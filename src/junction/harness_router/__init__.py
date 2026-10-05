"""Subscription-aware harness router.

Warding docks several coding-agent harnesses (Claude Code, Codex, Cursor,
Grok, OpenCode, …), each reached through a plan or account the operator
already pays for. This package decides which one takes each unit of work:
it matches the task kind to each harness's strengths, spends flat-rate
subscription quota before metered API spend, spreads load by each lane's
remaining window, and rests a lane that just hit a usage limit.

It chooses a harness; it does not forward provider traffic. The chosen
harness runs with its own login, as ``agent.acp_backend`` would.

Modules: ``kinds`` (task-kind enum, stdlib-only), ``profiles`` (per-harness
defaults), ``lanes`` (``routing.json``), ``limits`` (failure classes and
cooldowns), ``ledger`` (usage record), ``router`` (scoring), ``service``
(``HarnessRouter``, the facade every surface uses). The package init imports
nothing, so the validator can read ``kinds`` without loading the ACP stack.

Spec: docs/system-specs/modules/harness-router.md.
"""
