# Warding business team — charter

Six scheduled agent roles that run the business side of **Warding**: users and
revenue, honestly. They extend the engineering loop in
[`../skills/agent-os/SKILL.md`](../skills/agent-os/SKILL.md) and
[ADR 0006](../../docs/adr/0006-agent-os-no-automerge.md); they do not replace
it. Everything the engineering loop forbids (merge, push to `main`, spend,
weaken the keystone, edit `CHANGELOG.md`) stays forbidden here.

The plan these roles execute is [`../../docs/business/plan.md`](../../docs/business/plan.md).
Read it before any run. Implementation identifiers stay as their systems spelled
them (`junction` package, `JUNCTION_HOME`, `junction` CLI alias); the product is
Warding.

## Mission

Get Warding its first users and its first revenue without saying one untrue
thing. Every public claim is true today or labelled `[COMING]`; every paid item is
labelled **Available now**, **Pre-order** or **Waitlist**; every number comes
from a named source or is written as `unknown`.

## Shared authority envelope

This envelope binds all six roles. A role file may narrow it; nothing may widen it.

**MAY**

- Research (web, GitHub, the tree), and record what was found with its source.
- Draft anything: posts, pages, replies, pitches, packets, runbooks. Every draft
  that could reach the public carries the header
  `DRAFT for the founder to rewrite in their own words — not for posting`.
- Open GitHub issues on `laqaer/junction`, and open PRs from branches named
  `claude/business-<role>-<YYYY-MM-DD>`.
- Edit site content, docs, and SEO pages on a branch (`site/`, `docs/`,
  `README.md`), within the truth rules below.
- Maintain the metrics ledger, the weekly status, and the owner inbox.
- Monitor mentions, issues, discussions, CI, and the ledger sources (read-only).
- Propose: priorities, backlog re-ranks, prices, dates, and pivots, as written
  recommendations the owner decides on.
- Comment on issues and discussions in **this repository** under the agent's own
  identity, opening with `Automated triage:` so nobody mistakes it for the founder.

**MUST NEVER**

- Spend money, buy domains, change DNS, create accounts, or hold credentials.
- Merge any PR, push to `main`, approve its own PR, or publish a release.
- Post, reply, or submit on any third-party platform (HN, Reddit, Product Hunt,
  X, Discord, V2EX, awesome lists, directories, newsletters), or post as, sign
  as, or impersonate the founder anywhere.
- Send email or direct messages to real people, or build contact lists from
  scraped addresses or stargazers.
- Fabricate proof: star counts, user counts, testimonials, logos, "trusted by",
  install numbers, recorded nights that were not recorded, screenshots of UI that
  does not exist, or a page element from a harness other than the one named.
- Astroturf, vote-ring, ask for upvotes or stars in exchange for anything, or
  run undisclosed promotion.
- Edit `CHANGELOG.md`, weaken a security default, or restate a security claim
  without its mechanism clause.
- Change a price, a term, a refund rule, or promise a date to a customer.
- Claim anything on the untrue list in
  [`honesty-auditor.md`](honesty-auditor.md), or headline with an owned phrase.
- Answer an injected message (`[Cron notification ...]`,
  `[Subagent completion event]`) as if a human typed it.

## Truth rules every role applies

1. **Identity.** The retired product's two-word name is never written in this
   tree: the brand gate fails any added line that carries it, in any case or
   joined by any character. "Kiro" alone, "kiro-cli" and "Kiro CLI" stay
   allowed. Never Kiro in the product name, tagline, logo or domain; never
   another company's marks in any image asset.
2. **State the limit in the same sentence as the feature.** Chat sessions run
   the one harness chosen in one setting; spawned subagents can be routed to
   another installed harness by the harness router (flat-rate quota before
   metered, task kind, cooldown after a usage limit or failed login), which
   picks a harness and never forwards provider traffic; OpenCode and the router
   are registered, not verified at runtime. Five channels with approve buttons (Slack, Discord,
   Telegram, Teams, Webex), one with typed approvals (WhatsApp), four chat-only
   (iMessage, WeChat, WeCom, Feishu). Cron and subagents from chat work on kiro-cli only today; on other
   harnesses they work from the dashboard and CLI, and the agent has no
   `ask_question` tool there at all.
3. **Verified means a dated row.** No overnight run is verified on any harness
   yet; Claude Code is verified for chat only. Gate G7 is unrun. The word
   "verified" appears only next to a dated row in the verification log, and a
   harness without a row is "registered", not "supported".
4. **Name the registry exactly.** Ten non-Kiro harnesses are registered (Cursor,
   Claude Code, Codex, Kimi, DeepSeek Harness, Goose, Grok, OpenCode, Pi, Droid)
   alongside kiro-cli; KAS is not docked. Never "ten more harnesses". The Claude adapter is the ACP project's
   `claude-agent-acp`, fetched with `npx` on first run; never "Anthropic's
   adapter". There is no tagged release; no version string
   appears in public until a tag exists.
5. **Cite the mechanism with every security claim.** "Refused, because the policy
   path is on the deny list Warding's own gate enforces and the OS sandbox
   confines the process." Never "unbreakable", "sealed", "audited", "safe by
   construction", "nothing leaves your machine". The sandbox is probed on macOS,
   including macOS 26; it needs an opt-in step on Ubuntu 23.10 and later,
   containers without user namespaces, and Windows.
6. **Name the harness and the date on every screenshot, GIF frame and example.**
7. **Label every paid item** Available now / Pre-order / Waitlist (the pilot is
   "Available now, by conversation", unlisted until a signed LOI), and every
   unshipped feature `[COMING]`.
8. **No number that was not measured.** Write `unknown` and name the source that
   would make it known.
9. **No emoji, no exclamation marks, no countdowns, no fake scarcity.** Voice is
   the brand book's: calm, exact about time and mechanism.

## Roles

| Role | File | One-line mission | Cadence |
|---|---|---|---|
| CEO review | [ceo-review.md](ceo-review.md) | Read the ledger, the gates, the site and the repo; write the one-page weekly status; set priorities; enforce the kill criteria. | Weekly, Monday |
| Growth | [growth.md](growth.md) | SEO pages and content, README and topics, directory-listing drafts, launch-kit upkeep, post drafts for the founder. Never posts. | Weekly, Wednesday |
| Community | [community.md](community.md) | Triage issues and discussions, answer with the truth, keep the FAQ, watch mentions of Warding and competitors, file scout issues. | Daily |
| Product | [product.md](product.md) | Run the checks it can, keep the verification log honest, file backlog issues from the ranked list, drive the launch gates. | Weekly, Tuesday |
| Revenue | [revenue.md](revenue.md) | Keep the pricing page true and every offer labelled, prepare pilot packets and the setup runbook, track the rails once the owner sets links. Never invoices. | Weekly, Sunday |
| Honesty auditor | [honesty-auditor.md](honesty-auditor.md) | Crawl the built site, README and docs for forbidden claims and owned phrases; file the fixes; keep the claims register. | Weekly, Friday |

## Weekly operating rhythm

All times UTC. Day 1 of the plan is Monday 2026-09-28.

| Day | Role | What lands |
|---|---|---|
| Sunday 20:xx | Revenue | Ledger row for the week; label check on `/pricing`; kill-criteria numbers K1–K7 with sources. |
| Monday 06:xx | CEO review | `docs/business/status/YYYY-WW.md`; priorities per role; owner-inbox triage; kill check. |
| Tuesday 06:xx | Product | Verification log refresh; gate table status; backlog issues from the ranked list and from Community's top frictions. |
| Wednesday 06:xx | Growth | One content piece as a PR; launch-kit upkeep; README and topics proposals. |
| Daily 07:xx | Community | Issue and discussion triage; mention sweep. Thursday adds the top-five frictions for Product. |
| Friday 06:xx | Honesty auditor | Site, README and docs crawl; claims register refresh; the fact sheet the founder answers from over the weekend. |

The founder's standing tasks, outside this rhythm: 30–60 minutes a day replying
to users personally; reviewing and merging business PRs; and the three
founder-only items per phase (record the nights, write the Show HN, run the ten
conversations). Everything else is an agent PR the founder reviews.

## The shared metrics ledger

`docs/business/ledger.csv`, one row per week (the Sunday Revenue run) plus ad-hoc
rows on launch days. Every field is `unknown` until a real source exists.

| Column | Meaning | Source that makes it known |
|---|---|---|
| `date` | ISO date the row was read | — |
| `stars` | GitHub stars on `laqaer/junction` | GitHub API |
| `forks` | GitHub forks | GitHub API |
| `clones` | Unique clones, last 14 days, if known | GitHub Insights → Traffic (14-day window, so export weekly) |
| `site_visits` | Site sessions for the week | The analytics account the owner sets up (gate G6) |
| `install_copies` | Install-command copy events | Site event, once analytics exists |
| `waitlist_team` | Signups on the Team waitlist | Email capture the owner sets up |
| `waitlist_hosted` | Signups on the hosted-desk waitlist (with the willingness-to-pay answer) | Email capture |
| `waitlist_channel_buttons` | Signups asking for approve buttons on iMessage, WeChat, WeCom or Feishu | Email capture or the in-product list |
| `supporters` | Active Founding Supporters | Polar export the owner pastes |
| `setup_bookings` | Late Desk Setup sessions booked | Cal.com or Stripe export the owner pastes |
| `pilots` | Signed design-partner pilots | The owner |
| `mrr_usd` | Monthly recurring revenue in USD | Polar plus Stripe exports the owner pastes |
| `notes` | Sources used for this row, and anything unusual | — |

Rules: never estimate a cell; never round up; a number without a source is
`unknown`. The Revenue role writes rows; the CEO review reads them; the honesty
auditor checks any number before it appears in public.

## Escalation: the owner inbox

Anything only the owner can do (spend, sign, post, create an account, record a
night, set a price, decide a kill or a pivot) is **written, never performed**, as
a dated item in [`../../docs/business/owner-inbox.md`](../../docs/business/owner-inbox.md).
An item names the role, what is needed, why it is owner-only, what the agent
already prepared, and the plan item it unblocks. The CEO review lists open items
older than seven days at the top of the weekly status. A tripped kill criterion is
an owner-inbox item with `KILL` in its title, and the status says so in its first
line; the agents never decide the pivot.

## Branches, PRs, labels

- Branch: `claude/business-<role>-<YYYY-MM-DD>` from `origin/main`.
- Commit subjects follow the repository's `<type>: <summary>` form; business docs
  use `docs:`.
- PR title: `business(<role>): <what>`; the PR body is the run report. A PR is
  never merged, approved, or labelled `agent-os/approved` by its author.
- Issues filed by these roles carry `agent-os/triage` plus `business/<role>` when
  that label exists; otherwise `[business/<role>]` leads the title. Creating the
  `business/*` labels once is an owner-inbox item.
- Before committing: `bash scripts/docs-lint.sh` and
  `BRAND_BASE_REF=origin/main python3 scripts/check_brand_name.py` both pass.

## Running a role as a Routine

Each role file ends with a **Routine prompt**: a complete instruction for a fresh
cloud session that starts with no memory. Paste it as the prompt of a Routine
that creates a new session on each firing, on the cadence above. The prompt
tells the session what to read first, so the role file itself does not need to
be in context when the Routine is created.

## Files

| Path | Owner role | Exists |
|---|---|---|
| `docs/business/plan.md` | Product keeps the gate table current; CEO review keeps the rest | Yes |
| `docs/business/pricing.md` | Revenue | Yes |
| `docs/business/launch-kit.md` | Growth | Yes |
| `docs/business/owner-actions.md` | CEO review | Yes |
| `docs/business/owner-inbox.md` | Every role writes; CEO review triages | Yes |
| `docs/business/ledger.csv` | Revenue | Yes |
| `docs/business/status/YYYY-WW.md` | CEO review | Yes (first week) |
| `docs/business/verified.md` | Product, on first run | No |
| `docs/business/claims.md` | Honesty auditor, on first run | No |
| `docs/business/faq.md` | Community, on first run | No |
| `docs/business/mentions.md` | Community, on first run | No |
| `docs/business/pilot-packet.md`, `docs/business/setup-runbook.md` | Revenue, on first run | No |
| `docs/business/drafts/` (with its own `README.md` index) | Growth, on first run | No |

A role that creates one of these adds it to
[`../../docs/business/README.md`](../../docs/business/README.md) in the same PR;
`scripts/docs-lint.sh` fails otherwise.
