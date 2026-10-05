# Warding — company plan

This is the plan the [business team](../../.agents/business/README.md) executes
and the owner decides on. Day 1 is Monday 2026-09-28. Every paid item is
labelled **Available now**, **Pre-order** or **Waitlist**. Every number under
"Metrics" is a scenario, not a forecast: there have been zero customer
conversations. Implementation identifiers stay as their systems spelled them
(`junction` package, `JUNCTION_HOME`, `junction` CLI alias); the product is
Warding.

## 1. One-pager

**Mission.** Let a coding agent keep working when nobody is watching, on
hardware its owner controls, under rules the agent cannot open, and prove it in
public.

**What we sell.** Nothing in the Apache tree, ever. We sell (1) our time to set
the late desk up on your box, (2) a supporter tier with real digital goods,
(3) design-partner pilots that co-build the fleet layer (central policy push,
audit forwarding, SSO), and later (4) the Team companion that ships that layer,
plus (5) a hosted always-on box only if a waitlist proves it. Offers and labels:
[pricing.md](pricing.md).

**To whom.** Free: the developer with an agent subscription and a spare box.
Paid: the platform or security lead who has to say yes to unattended agents and
needs a packet to forward.

**Why now.** Vendors ship single-vendor routines, channels and remote control.
The local parallel-agent GUIs are free and crowded. The chat-reachable personal
agents are huge, and OpenClaw's security record got them banned at companies.
Three startups in the space died in 2026. The corner left is governance,
approvals and always-on self-hosting across agents, and the engine for it
already exists in this tree.

**Why us.** A mature, heavily tested gateway (dashboard, cron, task
runner, subagents, memory, ten channels, OS sandbox, deny rules, a keystone
policy the agent cannot read or write, an HMAC-chained audit log, POLICY ∩
PROFILE enforced at our own gate, Agent Worlds, 21 apps, 18 themes, 12
languages), plus a registry of ten non-Kiro harnesses (Cursor, Kimi, DeepSeek
Harness, Grok and Droid among them), with kiro-cli optional and last and no
vendor account in the door; a harness router that can send a spawned
subagent to another installed harness (registered, not verified at runtime);
and, in the plan below, the artefacts that
make governance checkable rather than claimed: a rendered charter, a verifiable
audit chain, a public bypass script, a per-OS fail-closed table, dawn-expiring
grants, and a morning report that counts refusals.

**What is true in the tree today.** Claude Code spawns through the ACP
project's `claude-agent-acp` adapter, fetched with `npx` on first run. The
default build contacts no vendor-owned endpoint: beacon silent, update check
skipped, app catalog served from seed and built-ins; the embedding model is still
fetched from a third-party CDN on first use. Claude Code is verified for chat only.

**What is not true yet.** A tagged release, a wheel, a one-line install, a
recorded overnight run on any harness, MCP tools on spec-family harnesses (so
cron and subagents from chat, and `ask_question` at all, work on kiro-cli only),
the model picker on non-Kiro harnesses, dawn-expiring grants, the Morning
Report, `warding charter`, `warding audit verify`, the bypass script, the
Supporter deliverables.

## 2. What is different

1. **No vendor door.** `auto` picks the spec-family CLI you already have;
   kiro-cli is optional and last. First run never asks for a Kiro account.
2. **Ten non-Kiro harnesses in the registry:** Cursor, Kimi, DeepSeek Harness,
   Grok and Droid among them.
3. **The default build contacts no vendor server.**
4. **The proof artefacts** `[COMING]`: `warding charter`, `warding audit
   verify`, the public "break the charter" script with a stated bounty, the
   per-OS fail-closed table, and `/verified`. We publish the test.
5. **Two mechanisms** `[COMING]`: dawn-expiring, session-scoped approval
   grants, and the Morning Report that counts commands refused and secrets
   redacted from the audit log.

Where we have no answer and say so: install polish, Docker, signed installers,
KAS, and MCP tools on non-Kiro harnesses.

Rules for naming other products: never promote in Kiro spaces; never imply
endorsement; Kiro never in the product name, tagline, logo or domain; never
another company's marks in any asset.

## 3. Launch gates

All must be green, with the named evidence, before Show HN.

| Gate | Pass criterion | Owner | Status 2026-09-26 |
|---|---|---|---|
| **G0** | Trademark knockout on "Warding" (plus "Warden / AI Warden" phonetic) clean; domain bought; every handle claimed in one hour; "no token or coin" line published. Fallback Keeplit if unclear. | Founder | Open |
| **G1** | Claude Code works on first message with only `claude` on PATH. | Agent | Green on code (the `npx` adapter fallback); re-verify on a clean Mac |
| **G2** | One-line install under 2 minutes on a clean Mac and a clean Ubuntu 24.04 VPS (`pipx install warding` or `uv tool install warding`, prebuilt `static/dist` in the wheel, no clone, no Vite); `temp-screenshots/` out of the tree. | Agent | Open |
| **G3** | A tagged GitHub Release with notes and SHA-256 checksums. | Agent drafts, founder tags | Open; no release exists |
| **G4** | Default build contacts no vendor-owned host; no vendor publisher labels in the UI; the `lsof` run published on `/verified`. | Agent | Green on code; lsof run open |
| **G5** | Every public claim true; the forbidden-claims test passes on the built site; the old site's false copy gone. | Agent drafts, founder approves | Open; site not built |
| **G6** | Measurement: privacy-friendly site analytics, email capture with a working fallback, GitHub traffic export, opt-in beacon to an owned endpoint or none. | Agent, accounts by founder | Open |
| **G7** | Three recorded, unedited Claude Code nights (cron job, one Telegram-approved push, one refused `~/.ssh` read, checkpoint resume, service restart mid-night, `audit verify` green) on a clean Mac mini and a clean VPS, hourly RSS logged, published as dated rows on `/verified`. | Founder records, agent scripts | Open, unrun: no overnight run is verified on any harness. The kill criterion. |
| **G8** | The hero GIF is cut from those recordings, harness and date in frame, never mocked. | Founder records, agent edits | Open |
| **G9** | `/security#scope` states what is enforced where (keystone at the gate plus sandbox; PreToolUse fail-open for pre-authorised tools; computer-use refusals in band; per-OS sandbox table with the exact install line); SECURITY.md updated (acknowledge in 5 business days, bounty scope with safe harbour); the bypass script in the repo with expected output. | Agent drafts, founder signs | Open |
| **G10** | Founder's HN account can post Show HN; Reddit account age and karma checked; GitHub Discussions plus a Discord or Telegram group open; issue templates; "Known limitations" in README. | Founder | Open; issue templates exist |

## 4. The 90 days, by week

| Week | Dates | Work | Gates |
|---|---|---|---|
| **1** | 09-28 → 10-04 | Founder: G0 (knockout, domain, handles), daily genuine HN comments, stand up Polar and Stripe. Agents: backlog #1 (`warding` console script and rename surfaces), #2 (wheel and one-line install, drop `temp-screenshots/`), #8 (background helpers and model picker off kiro-cli), #9 (sandbox fail-closed UX), start #3 (refusal stamp with SEL line); publish the lsof run; write the G7 night runbook. | G0 G2 G4 G6 |
| **2** | 10-05 → 10-11 | Agents: `warding charter` (#11), `warding audit verify` with export (#12), the bypass script and SECURITY.md rewrite (#13), Astro site v1 with the reserve hero line and every fallback state. Founder: record night 1 on a Mac mini with Claude Code and Telegram. Late Desk Setup goes live on Stripe. | G3 G5 G9 |
| **3** | 10-12 → 10-18 | Founder: nights 2 and 3 (VPS with an AppArmor profile; service restart mid-night). Agents: fix what broke; start #4 (MCP tools to spec-family harnesses); generate the `/verified` table from the logs; #7 (hand-raised sprite pose, local-hour sky, time-based tick, draw-once). Private dogfood with 5–10 developers (founder watches, does not coach). Tag v0.6.0-rc. | G7 G1 |
| **4** | 10-19 → 10-25 | Kill check K1. If green: cut the GIF from the recordings, flip the hero to the verified headline, tag v0.6.0, README rewrite, invite two named outside reviewers to run the bypass script (unpaid, credited). Agents: dawn-expiring grants (#5) behind a flag. Founder: commission the Supporter art; write the Show HN text in own words from the fact sheet. | G3 G8 G10 |
| **5** | 10-26 → 11-01 | **Show HN**, Sunday 11-01 at about 16:00 UTC; founder answers for 8 hours; agents monitor issues and hot-fix; no other channel that day. The title names only a harness with a dated night on `/verified`, so Claude Code and not Codex. Patch release next day. r/ClaudeCode workflow post with the real Mac-mini transcript (founder). | — |
| **6** | 11-02 → 11-08 | awesome-claude-code form, ACP Clients page PR, awesome-agent-orchestrators PR (founder submits, agents draft). r/ClaudeAI four-part post. Newsletter pitches (Console, TLDR, Changelog News, Self-Host Weekly). Ship dawn grants (#5) and Morning Report v1 (#6). Supporter deliverables land in the private repo; `warding license activate` (#14). | — |
| **7** | 11-09 → 11-15 | **Product Hunt**, Saturday 11-14, no waitlists on the page. r/selfhosted lesson post. Founding Supporter opens on Polar. First ten outbound security or platform-lead conversations begin (founder; opt-in contacts). The pilot page goes live only when the first LOI is signed. | — |
| **8** | 11-16 → 11-22 | V2EX, Juejin, Zenn posts (native speaker rewrites; Feishu and WeCom stated as chat-only with a buttons waitlist). YouTube 6–8 minute walkthrough. Codex night and Goose night recorded: two more `/verified` rows. | — |
| **9** | 11-23 → 11-29 | `/registry` matrix generated from CI (#15). `warding switch` with the carried-over list (#10). Desk Care waitlist goes live if 5 Setups are done. Month-one retro published with real numbers. | — |
| **10** | 11-30 → 12-06 | Pilot #1 kickoff if signed (SIEM forwarding is the first Team feature built). Bi-weekly night-log post format begins (agent drafts from the audit log, founder rewrites). Feishu interactive-card approvals started if the channel-buttons waitlist passes 30. | — |
| **11** | 12-07 → 12-13 | Kill check K3 and K4. Second demo (the switch drill or the morning report) as a new GIF. | — |
| **12** | 12-14 → 12-20 | Team companion skeleton (`junction.plugins` entry point; central policy push over the admission trust root) only if a pilot exists. Relaunch on Product Hunt with the version. | — |
| **13** | 12-21 → 12-27 | Day-90 review against sections 5 and 6; decide the next quarter's single channel bet; publish it. | — |

Founder calendar rule: the founder's first 30 days contain exactly three
founder-only items (record the nights, write the Show HN, run the ten
conversations) plus the account actions in [owner-actions.md](owner-actions.md).
Everything else is an agent PR the founder reviews.

## 5. Metrics and targets (scenarios)

| Stage | Metric | Source | Day-30 bad / base / good |
|---|---|---|---|
| Attention | HN points; PH rank; Reddit upvotes | platforms | 20 / 120 / 300 |
| Visit | site sessions by UTM; GitHub views | analytics (G6); GitHub Insights weekly export | 2k / 8k / 20k |
| Intent | install-command copies; Approve-tap on the hero; GitHub clicks | site events | 150 / 600 / 1,500 |
| Stars | GitHub stars (about 1.4 per HN point in 48 h, from the Show HN corpus) | GitHub | 100 / 400 / 1,200 |
| Activation | successful `up` → first agent reply → first channel connected → first scheduled job executed | opt-in beacon (owned); undercounts | 40 / 150 / 400 first replies |
| Retention | weekly-active installs; still active in week 4 | beacon | 15 / 50 / 120 |
| Waitlists | Team; Hosted (with willingness to pay); channel buttons | email capture | 10 / 40 / 120 |
| Revenue (90 days) | Setup × $199; Supporters × $96 (or $8/mo); Pilot × $1,500 | Stripe, Polar | $600 / $1,900 / $4,700 (bad: 2 setups + 2 supporters; base: 4 setups + 8 supporters + 0 pilots; good: 5 setups + 15 supporters + 1 pilot) |
| Quality | install failure rate; median time to first reply; overnight jobs ending in an unreported error; p50 issue response | telemetry, GitHub | under 20% / 10% / 5% install failures; unreported overnight errors under 1 in 5 |

Decision rules: activation under 50% means stop promoting and fix onboarding.
Stars up with actives flat means the demo attracts tourists; move the hero to the
job to be done. Setups selling while nobody asks for governance: see the pivot.
The ledger these are read from is [ledger.csv](ledger.csv); every cell is
`unknown` until its source exists.

## 6. Kill criteria and the pivot

| # | When | Criterion | Consequence |
|---|---|---|---|
| K1 | Day 10 (end of week 2); hard stop day 30 | No Claude Code night completes unattended on a clean Mac mini without intervention. | Launch waits. No Show HN, no Setup sales for Claude Code users (Setup stays kiro-cli-only), the hero keeps the reserve line, the 07:00 section keeps the real cron calendar. |
| K2 | Day 30 | The trademark knockout on "Warding" returns a live conflict, or a competitor ships a rendered policy view plus an overnight digest before Show HN. | Rename to Keeplit before any paid item is listed; differentiation moves to the proof artefacts and dawn grants. |
| K3 | Day 45 | 0 of 10 outbound security or platform leads take a call. | The paid governance layer has no buyer this quarter: the pilot is withdrawn, Team stays a waitlist, money is Setup plus Supporter only. |
| K4 | Day 60 | The Show HN top comment is "reskin / unaudited" and the founder could not answer with the bypass-script results and `/security#scope` already published. | The honesty apparatus shipped too late; no second launch until it is public and two outside reviewers are credited. |
| K5 | Day 60 | Fewer than 30 weekly-active installs and zero inbound security-lead conversations from `/security`. | Both bets have no signal; freeze feature work, run 20 user interviews, re-plan. |
| K6 | Day 90 | Anthropic un-pauses separate metering of unattended ACP use and no second harness has a recorded night. | Re-lead the hero on Codex, Goose or kiro-cli; Claude Code moves to "supported, metered by Anthropic". |
| K7 | Any day | A public thread shows a page element (screenshot, GIF frame, checkmark) from a harness other than the one the page names. | Pull the asset within the hour; publish the correction on `/verified`. |

**The pivot (K1, K3 or K5).** The night narrative stays as the demo; the brand
stays; the ICP flips fully to the security lead who forwards a packet, with the
indie developer as the free tier that produces screenshots. Paid becomes (a) a
Charter Pack (signed policy templates, the bypass script, audit export, the
fail-closed table, and an hour with the founder) at $199, Available now, and
(b) the pilot with the security buyer's five deliverables as written
preconditions. The Show HN title becomes the mechanism: grants that expire at
07:00. If only K6 trips, the pivot is a harness re-ordering, not a brand change.

The agents check these on schedule and write a tripped criterion to the
[owner inbox](owner-inbox.md); the owner decides.

## 7. Ranked product backlog

Rank is first-run impact times revenue impact. Effort S/M/L. "Gate" means it
must ship before Show HN. The Product role files one issue per row; the code
pointers below are where an implementer starts.

| # | Change | Why | Effort | Gate | Where |
|---|---|---|---|---|---|
| 1 | `warding` console script and rename surfaces: primary script, `junction` and older aliases silent; CLI banner; setup wizard headline; README; identity test; both `.agents/skills/*` files. | Brand on first run | S | G0 | `pyproject.toml` `[project.scripts]`, `src/junction/cli.py`, `src/junction/constants.py`, `test/test_user_facing_identity.py`, `website/src/i18n/locales/*.json` |
| 2 | One-line install, PyPI and npm `warding`, tagged release: wheel with prebuilt `static/dist`, `pipx` or `uv tool install`, checksums; installer script downloads the wheel; `temp-screenshots/` out of the tree and history. Fix red CI first. | HN's "easy to try" rule; the primary CTA label depends on it | M | G2 G3 | `pyproject.toml`, `scripts/get-junction.sh`, `minimal_install.sh`, `.github/workflows/`, `README.md` installer prose |
| 3 | The refusal moment in the UI plus the first upgrade card: seal stamp and SEL line with truncated HMAC on every gate deny; dismissible Team-waitlist card through the contributor seam. | Best screenshot; upgrade moment 1 | S | G8 | `src/junction/hooks.py` (`TOOL_DENY`), `src/junction/sel.py`, `src/junction/platform/defaults.py` (`DefaultDashboardContributor`), the chat tool-call renderer in `website/src/` |
| 4 | Pass Warding's MCP servers to spec-family harnesses so cron from chat, `ask_question`, spawn and memory tools work on Claude Code and Codex, within the harness-parity invariants (adapt, never widen the Kiro path). | Without it a Claude Code user gets a worse product than a kiro-cli user gets | M–L | no; label "from dashboard and CLI" until it lands | `src/junction/acp/client.py` (`_claude_session_mcp_servers`), `src/junction/agent.py`, `docs/system-specs/modules/harness-parity.md`, `scripts/check_harness_parity.py` |
| 5 | Dawn-expiring approval grants: a third choice next to Approve and Deny, "Allow `<tool>` until 07:00", session-scoped, stored on the approval record with the chat identity, expiring at the configured hour, never process-wide; make the process-wide trust grant itself deniable by policy. Rendered on the five button channels and the WhatsApp typed ladder. | The one governance feature no competitor has | M | no (`[COMING]`) | `src/junction/messaging/approval.py` (`_grant_session_trust`), `src/junction/hooks.py`, the channel transports' `max_buttons`, `src/junction/whatsapp/turn_renderer.py`, governance `SCOPE_CATALOG` (a data change, not an evaluator edit) |
| 6 | Morning Report: on first dashboard open after an overnight job or at a configured hour: sessions run, PRs and artifacts, approvals asked and answered, commands refused (from the audit log), secrets redacted, wall time; posted to the owner's channel and as a dashboard card; plus the "desk stopped at 00:10: reason" line so a dead night is reported. | Emotional payload; retention loop; upgrade moment 2 | M | no (the real cron calendar until then) | new `src/junction/morning_report.py`; sources `src/junction/cron.py`, `src/junction/sel.py`, `src/junction/messaging/approval.py`; channel transports; `platform/defaults.py` |
| 7 | Agent Worlds for the web and for truth: hand-raised sprite pose for pending approval; local-hour window sky; time-based tick; draw-once path for reduced motion; integer scaling and crop on phones; brand palette remap; agent chat lines; wallpaper export. | The hero and the GIF | S–M | G8 (partly) | `website/src/pages/scenes/OfficeScene.tsx`, `website/src/hooks/sceneCanvas.ts`, `website/src/hooks/useSceneInteraction.tsx`, `website/src/hooks/sceneText.ts` |
| 8 | Non-Kiro dashboard parity: `GET /api/models` returns the docked harness's advertised set or an honest "this harness picks its own model" state instead of 503; background helpers run on the selected harness via `resolve_usable_model` or degrade quietly; regenerate and rewind un-gated or hidden. | Silent failures read as "broken" on the first run | M | G1 (visible degradation) | `src/junction/dashboard/handlers/agents.py`, `src/junction/session.py` (`get_bg_session`), `src/junction/acp/runtime.py`, `chat_regenerate.py`, `chat_rewind.py` |
| 9 | Sandbox fail-closed UX: one-screen explanation with the exact install line on Ubuntu 23.10 and later, containers without user namespaces, and Windows (not macOS 26, where Seatbelt works and is probed); Settings → Security shows the per-OS table; never weaken the default. | Second most common first-run failure; the VPS guide targets it | S | G9 | `src/junction/sandbox.py`, `docs/guides/install.md`, `src/junction/security_posture.py` |
| 10 | `warding switch <runtime>`: validates the runtime is installed, sets `agent.acp_backend`, drains and restarts sessions, runs a smoke prompt, prints the carried-over list (memory rows, crons, skills, channels, policy hash). | The portability proof point; upgrade moment 5 | M | no | `src/junction/cli.py`, `src/junction/config/loader.py` (`_normalize_acp_backend`), `src/junction/planes.py`, `src/junction/snapshot.py` |
| 11 | `warding charter` (CLI and dashboard page): renders `security_policy.json`, `profiles/` and the effective POLICY ∩ PROFILE per tool as numbered articles; exports Markdown and PDF for auditors. | The brand's central artefact; the pilot's sales deck | S–M | G9 | `src/junction/security.py` (`_SENSITIVE_HOME_DIRS`), `src/junction/hooks.py`, `src/junction/security_posture.py`, `docs/system-specs/modules/governance.md` |
| 12 | `warding audit verify`: prints the audit-chain status in one command; `--export json/csv`; SIEM and OTel forwarding is the first Team feature. | Makes "chained log" checkable in ten seconds | S | G9 | `src/junction/sel.py` |
| 13 | SECURITY.md rewrite plus the "break the charter" script: ten reproducible attempts to read, write, `sed`, symlink, `tar` and `python -c open()` the keystone with expected output; scope is the keystone bypass; documented fail-open paths listed as out of scope with issue links; safe-harbour language; one payout per quarter (amount signed by the owner); acknowledge within 5 business days. | Trust block at 0 stars; the answer to "unaudited" | S | G9 | `SECURITY.md`, `test/test_denied_commands_security.py`, `docs/architecture/security-deep-dive.md` |
| 14 | Founding Supporter deliverables plus `warding license activate`: The Vault scene on the 440×300 engine (ships in the product, gated by key), the theme pack, the numbered seal badge from a Polar license key (key plus org id, no secret). | Polar checkout cannot open until they exist | M (2–5 days art) | no | `website/src/pages/scenes/config.tsx`, `docs/system-specs/modules/themes.md`, `platform/discovery.py` (`junction.plugins`) |
| 15 | `/registry` and `/verified` from CI: an e2e job per harness (Claude Code, Codex, Goose first) that seeds memory, fires a cron, round-trips a Telegram approval and logs a refusal; writes a dated matrix with honest "unverified" rows the site renders. | Replaces every "any agent" claim with a table | M–L | no | `docs/ci/harness-parity-gate.md`, `scripts/check_harness_parity.py`, `test/`, `src/junction/context.py` |
| 16 | Approve buttons on Feishu (interactive cards) and WeCom (template cards); typed approvals on iMessage. Planned, not started; the waitlist sets the order. | The Asia channels are chat-only today | M / S | no | `src/junction/feishu/`, `src/junction/wecom/`, `src/junction/imessage/`, `messaging/approval.py` (`TextReplyApprovalDecider`) |
| 17 | Multi-approver sets per channel, per-channel policy profiles, audit-log webhook forwarding (the pilot build). | The product is single-owner; the pilot is unsellable without it | L | no (pilot-funded) | `src/junction/messaging/identity.py`, `messaging/session_trust.py`, `platform/admission.py`, `platform/defaults.py` (`DefaultIdentityProvider`), `sel.py` |
| 18 | RSS under load measured (three sessions plus embeddings plus subagents) on an 8 GB Mac mini and a 4 GB VPS; published on `/security` and in README "Known limitations". Idle is 452 MB, measured; the 10 GB figure was never measured for Warding. | Kills the 10 GB myth or confirms it; gates the hosted question | S | G7 (part of the nights) | `src/junction/cloud/sizes.py` |

Gates: #1, #2, #3, #8, #9, #11, #12, #13 plus the nights before Show HN. #4,
#5, #6, #7 make the brand true. #10, #14, #15, #16, #17, #18 make the revenue
true.

## 8. Owner-only actions and the team

Owner-only actions, dated: [owner-actions.md](owner-actions.md). Items the
agents raise as they go: [owner-inbox.md](owner-inbox.md). The six roles, their
envelope and their Routine prompts:
[`.agents/business/README.md`](../../.agents/business/README.md). Weekly status:
[status/](status/README.md).

Escalation to the owner, always: any spend, any date promised to a customer,
any security report, any public correction, any change to SECURITY.md, pricing
or terms, any request to post, and any kill criterion that trips.
