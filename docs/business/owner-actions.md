# Owner-only actions

The standing checklist of things only the owner can do. The agents prepare,
draft, and remind; they never spend, sign, post, create an account, hold a
credential, or record a night. Dates follow the [plan](plan.md), whose day 1 is
Monday 2026-09-28. Items that come up between these go to the
[owner inbox](owner-inbox.md). The CEO review reads this file every Monday.

Status values: open, done (with the date), or dropped (with the reason).

## Week 1 (09-28 → 10-04): the name, the accounts, the measurement

| Due | Action | Why owner-only | Prepared by the agents | Status |
|---|---|---|---|---|
| 09-30 | **Trademark knockout** on "Warding" and "Warding Labs", classes 9 and 42, USPTO TESS and EUIPO, plus the phonetic cluster "Warden / AI Warden" (aiwarden.com, aiwarden.ai, ai-warden.io, wardengateway.com, agentic-warden exist in the same field). Ideally a 30-minute attorney read. Look at `warding.com` by hand. Decide Warding versus the fallback Keeplit by day 3. | Legal judgement and possible spend | The availability table in the brand book: `.dev`, PyPI and npm read as free on 2026-09-26; Keeplit and Lampkeep checked as fallbacks | open |
| 09-30, the same hour | **Buy `warding.dev`**; `.run` if free once the RDAP rate limit clears; `.sh` and `.so` at a registrar. | Spend | The redirect map is the site spec's route table | open |
| 09-30, the same hour | **Claim the handles**: the repository lives at `myrmitis/warding`; npm `warding`; PyPI `warding`; X; Reddit; Product Hunt; Discord; YouTube. Publish "Warding has no token or coin" the same hour. | Identity and accounts | The "no token" line; the list of surfaces that hardcode the slug (installer script remotes, README) for the engineering loop to update | open |
| 10-02 | **Polar organisation**: confirm in writing with Polar that a supporter tier whose future features are labelled "in development" is not a pre-order, before checkout opens. Create the Founding Supporter product (annual and monthly) but keep it unpublished until both deliverables ship. | Account, money, terms | `pricing.md` rows 3 and 5; the benefit list (license key, private repo, Discord role) | open |
| 10-02 | **Stripe account**: tax registration; a Payment Link for Late Desk Setup ($199, with the written scope and the full-refund term); Invoicing for pilots. | Account, money, tax | `pricing.md` rows 2 and 4; the setup runbook and pilot packet (Revenue creates them) | open |
| 10-02 | **GitHub Sponsors profile** for tips. | Account | — | open |
| 10-02 | **Cal.com** (or equivalent) booking page for Setup sessions and pilot calls, linked from the pricing page once it exists. | Account | The booking-page copy in the setup runbook | open |
| 10-04 | **Analytics** account (Plausible or Umami) and its script domain; **waitlist endpoint** (Formspree, Buttondown, or a Vercel function; or accept the GitHub Discussions fallback); **Google Search Console** and **Bing Webmaster** once the domain resolves. | Accounts, spend | The event names the site spec defines; the UTM scheme | open |
| 10-04 | **Create the `business/*` labels** once on the repository (`business/ceo-review`, `business/growth`, `business/community`, `business/product`, `business/revenue`, `business/honesty-auditor`), alongside the existing `agent-os/*` set. | Repository admin | The label list in the charter | open |
| daily from 09-29 | **HN account**: genuine comments, not about the product, every day; confirm the account is allowed to post Show HN. **Reddit account**: check age and karma against each community's norms. | Identity | The community rules table in the launch kit | open |
| 10-04 | **Approve the prices and labels** in `pricing.md` in writing. | Every price | `pricing.md` | open |

## Week 2 (10-05 → 10-11): the first night, the site

| Due | Action | Why owner-only | Prepared by the agents | Status |
|---|---|---|---|---|
| 10-09 | **Vercel project** for the rebuilt site: root `site/`, Node 22.12 or later, framework Astro; DNS to `warding.dev`; preview protection. | Account, DNS | The site spec's deploy section; `vercel.json` | open |
| 10-11 | **Record night 1** on a clean Mac mini with Claude Code and a real Telegram bot, following the runbook in the verification log: install, dock, connect Telegram, one cron job, one approved push, one refused `~/.ssh` read, checkpoint resume, a service restart mid-night, hourly RSS logged, `audit verify` at 07:00. **Never intervene** during the night. Place the logs under `docs/business/nights/`. | Real hardware; the kill criterion K1 | The runbook (Product); the SEL export and RSS scripts | open |
| 10-11 | **Sign SECURITY.md**: the acknowledgement window (5 business days), the bounty scope with safe harbour, the payout amount and cadence. | Signature; terms; money | The rewrite and the bypass script (backlog #13) | open |
| 10-11 | **Late Desk Setup goes live** on the Stripe link. | Money | The runbook; the pricing page copy | open |

## Week 3–4 (10-12 → 10-25): nights 2 and 3, the release, the art

| Due | Action | Why owner-only | Prepared by the agents | Status |
|---|---|---|---|---|
| 10-18 | **Record nights 2 and 3**: a clean VPS with an AppArmor profile, one with a service restart mid-night. Logs under `docs/business/nights/`. | Real hardware; K1 | The runbook | open |
| 10-18 | **Private dogfood**: 5–10 developers install from scratch on their own machines; the founder watches and does not coach. | Relationships | The install checklist; the friction template (Community) | open |
| 10-18 | **Tag v0.6.0-rc** from the release-notes draft and checksums. | Release publication | The notes and checksums (Product drafts) | open |
| 10-23 | **Kill check K1**: read the three nights; decide. | Decision | The verification rows | open |
| 10-25 | **Tag v0.6.0**; invite two named outside reviewers to run the bypass script (unpaid, credited). | Release; relationships | The notes; the reviewer brief | open |
| 10-25 | **Commission the Supporter art** (The Vault scene; the theme pack) with a named artist under a written assignment; keep the provenance list. | Spend; contract | The scene brief on the 440×300 engine; the theme-pack format | open |
| 10-25 | **Write the Show HN text** in your own words from the fact sheet in the launch kit. | HN forbids generated text | The fact sheet, refreshed by the Honesty auditor on 10-30 | open |
| 10-25 | **Open GitHub Discussions** and a Discord or Telegram group (the Telegram group doubles as a live demo of the channel); add "Known limitations" to the README (agents draft). | Accounts | The README draft | open |

## Week 5–8 (10-26 → 11-22): the launches and the conversations

| Due | Action | Why owner-only | Prepared by the agents | Status |
|---|---|---|---|---|
| 11-01, about 16:00 UTC | **Post Show HN** and answer for eight hours. No other channel that day. | Identity; HN's rules | The fact sheet; the objection answers | open |
| 11-02 → 11-08 | **Post** r/ClaudeCode, then r/ClaudeAI; **submit** to awesome-claude-code (web form), the ACP Clients page (PR from your account), awesome-agent-orchestrators (PR); **send** the newsletter pitches one at a time. | Identity; each venue requires a human | The drafts in `docs/business/drafts/` and the launch kit | open |
| 11-14, 00:01 PT | **Product Hunt launch**; reply all day; a "we're live, tell us what's missing" note to opted-in lists only. No waitlist on the page. | Identity | The gallery, tagline, description, first-comment draft | open |
| 11-09 → 11-22 | **Ten outbound conversations** with security or platform leads: opt-in contacts and companies that publicly banned OpenClaw. Never a scraped list, never a cold email from an agent. | Relationships; K3 | The pilot packet; a prep note per call | open |
| 11-15 | **Open Founding Supporter on Polar** only once both deliverables are in the product and the license activation works. | Money | The deliverables (backlog #14); the label change in `pricing.md` | open |
| 11-22 | **Record the Codex and Goose nights** (two more verification rows). | Real hardware | The runbook | open |
| 11-22 | **Post** V2EX, Juejin and Zenn through a native speaker who rewrites the translation; publish the YouTube walkthrough. | Identity; language | Translation drafts; the walkthrough script | open |

## Later, dated by a condition rather than a week

| When | Action | Why owner-only | Status |
|---|---|---|---|
| The first signed LOI | **Sign the pilot scope** with a named deliverable and date; list the pilot on `/pricing` only then. | Signature; money | open |
| Five Setups done | **Open Desk Care** on a Stripe subscription. | Money | open |
| Signed desktop builds scheduled (not in the 90-day plan) | **Apple Developer Program** ($99 per year) and Windows code signing. Not now. | Spend | open |
| Any day | **Sign** every refund, every price change, every change to terms. **Decide** every kill criterion and the pivot. | Money; decision | standing |
