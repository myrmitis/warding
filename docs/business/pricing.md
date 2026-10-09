# Warding — offers and pricing

The offers, their prices, the label each carries on the site today, the rail it
sells on, what is delivered on day one, and the refund term. This file is the
only source the site's `/pricing` page may disagree with by mistake, so the
Revenue role checks the two against each other every week. The owner approves
every price and every term in writing before it appears on the site; the prices
below are the plan's, recorded here so the labels can be checked.

Labels: **Available now** (deliverable exists today), **Pre-order** (Stripe
only, with a delivery date and a full-refund term), **Waitlist (free)** (nothing
is sold; the list measures demand). The design-partner pilot is Available now
but sold by conversation and is not listed on `/pricing` until one signed LOI
exists.

## Offers

| # | Offer | Price | Label on the site today | Rail | Delivered on day one | Refund term | Opens |
|---|---|---|---|---|---|---|---|
| 1 | Free (Apache-2.0) | $0, forever | Available now | — | Everything in the tree: harness docking (chat runs the one harness you choose; spawned subagents can be routed to another installed one), cron with the template gallery, the task runner, subagents, memory, lessons and skills, ten channels (five with approve buttons, one typed, four chat-only), the full security floor, the dashboard, Agent Worlds, 21 apps, 18 themes, 12 languages. Nothing in the tree is ever gated. | — | Day 1 |
| 2 | Late Desk Setup | $199, one-time | Available now, once the Stripe Payment Link exists (owner action). Scope: a Mac mini or Linux box; kiro-cli or Claude Code; chat plus dashboard cron; one channel with buttons. Sold to Claude Code users only while kill criterion K1 is not tripped. | Stripe Payment Link | A 60-minute session on the customer's machine: install as a service, dock the agent, connect one channel with approvals, write the first policy profile together, run one scheduled job. Scope in writing. Runbook: `docs/business/setup-runbook.md` (Revenue creates it). | Full refund if the named outcome is not reached. | Week 2 (founder-hours product; needs nothing built) |
| 3 | Founding Supporter | $96 per year, price locked while active; $8 per month also offered | Waitlist until both deliverables ship in the product; then Available now | Polar (license key, private repo access, Discord role) | Day one, once live: a numbered seal badge in the dashboard and on the opt-in `/supporters` wall; the private repo with The Vault Agent World scene and the Charter Paper plus Warding Night theme pack; a Discord role; a roadmap vote. Future paid features are added to the key as "in development", never sold. Art drawn from scratch by a named artist with a written provenance list. | Polar's standard terms; the owner confirms in writing with Polar that this tier is not a pre-order before checkout opens. | Week 6, after the art and `license activate` land |
| 4 | Design-Partner Pilot | $1,500 for 60 days, up to 10 seats, credited against year one of Team | Available now, by conversation; not listed on `/pricing` until a signed LOI exists | Stripe Invoicing | A weekly session. Preconditions, in writing, before an invoice: the bypass script, an exportable verified audit chain, the fail-open and fail-closed scope statement, the lsof-clean default build, three recorded Claude Code nights. Co-built: central policy authoring with signed push over the admission seam; audit-log forwarding to a SIEM or OTel with a chain-verification report. Packet: `docs/business/pilot-packet.md` (Revenue creates it). | Named deliverable and date; full refund if missed. No "3 slots" scarcity. | Week 7 or later, after gates G1–G6 and the nights |
| 5 | Team | $24 per user per month annual, $29 monthly, minimum 3 | Waitlist (free) | Polar, later | Nothing today. The fleet companion: signed policy distribution, plugin and skill allowlist with a kill switch, audit-log forwarding, dashboard SSO, drift and posture reports. Built with pilots. | — | Waitlist day 1; product after two pilots |
| 6 | Hosted late desk | target $49–99 per month, bring your own agent subscription | Waitlist (free), with a three-question willingness-to-pay survey | — | Nothing today. Not built until 50 or more signups at a willingness to pay of $49 or more, and RSS under load is measured (idle is 452 MB, measured; the 10 GB figure was never measured). | — | Waitlist day 1 |
| 7 | Desk Care | $29 per month | Waitlist until five Setups are done | Stripe subscription | Monthly update, health check, backup check, email support. | Cancel any time; the current month is not refunded. | Week 9 or later |
| 8 | Tips | any amount | Available now, once the GitHub Sponsors profile exists (owner action) | GitHub Sponsors (0% from a personal account) | Goodwill only. Not on Polar (Polar prohibits sponsorship). | None. | Day 1 |

## Rails and what each may carry

| Rail | Carries | Does not carry | Why |
|---|---|---|---|
| Polar | Founding Supporter (software and bounded digital goods); Team later | Human services, sponsorship, pre-orders, paid waitlists | Polar is merchant of record and its acceptable-use policy prohibits those; a supporter tier whose future features are labelled "in development" needs Polar's written confirmation that it is not a pre-order |
| Stripe (Payment Links, Invoicing, subscriptions) | Late Desk Setup, Design-Partner Pilot, Desk Care, any explicit pre-order | — | The founder is merchant of record and files the tax; Stripe allows services and pre-orders |
| GitHub Sponsors | Tips | Anything that delivers a license or a good | 0% fee from a personal account; cannot deliver licenses |

## Honesty guardrails

- Every paid item carries exactly one of Available now, Pre-order, Waitlist.
  A pre-order exists only on Stripe, with a delivery date and a full-refund term
  in the same sentence.
- No money is taken for anything that does not work yet: not Founding Supporter
  before both deliverables are in the product, not Team, not the hosted desk,
  not Desk Care before five Setups are done.
- No countdown timers, no "only 3 left", no fake scarcity. A real operational
  limit may be stated with its reason ("we onboard pilots by hand, one at a
  time").
- No testimonials, customer logos, "trusted by", star counts or user counts
  without written permission or live data; no star count under 1,000 anywhere.
- Warding never resells or marks up model tokens and never takes provider keys;
  "no run cap from us" always carries "your model plan's limits and your
  vendor's terms for unattended use apply and may change" in the same sentence.
- Human services (Setup, pilots, Desk Care) sell on Stripe, never on Polar.
  Sponsorship goes to GitHub Sponsors, never to Polar.
- Waitlists never appear on a Product Hunt page (Product Hunt excludes
  waitlisted products).
- The pilot is never listed on `/pricing` before a signed LOI, and never with a
  slot count.
- Setup for Claude Code users is withdrawn (Setup stays kiro-cli-only) if kill
  criterion K1 trips; the label changes the same day.
- The agents propose price and label changes in writing; the owner changes them.
  An agent never invoices, refunds, quotes, or sends a payment link.

## What `/pricing` shows as of 2026-09-26

Nothing paid. The site is being rebuilt; no Stripe link, Polar product, or
GitHub Sponsors profile exists yet (see [owner-actions.md](owner-actions.md)).
When the page ships it shows: Free (Available now); Late Desk Setup (Available
now, once the link exists); Founding Supporter (Waitlist); Team (Waitlist);
Hosted late desk (Waitlist, with the survey); Desk Care (Waitlist); Tips
(Available now, once the profile exists). The pilot is not on the page.
