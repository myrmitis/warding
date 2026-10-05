---
name: marketing-site
description: "Warding marketing site under site/ (Astro). Use when changing hero, tagline, copy, motif, or deploy. Paper and the Ward Seal by day, the night office by night; no emoji; every claim true or labelled in development. Vercel on getjunction.dev until the owner moves the domain; no GitHub Pages."
---

# Marketing site

Code: `site/` (Astro; not `website/`, which is the dashboard SPA). Identity:
[`../../../PRODUCT.md`](../../../PRODUCT.md). Voice, visual system and the
NO-SAY list: [`../../../JUNCTION.md`](../../../JUNCTION.md). Preview:
[ADR 0005](../../../docs/adr/0005-preview-not-production.md).

## Rules

- Name: Warding. Tagline: The lamp stays on. The rules stay shut. Hero
  headline until three recorded nights exist: One agent, all night, on your
  own box. CLI `warding`; slug `laqaer/junction`.
- Never a Kiro or other company's mark in an image asset.
- Two registers, one system: paper (bg `#F3EEE3`, ink `#1A1814`, seal
  `#B3301A`) for what you read; night (bg `#0B0E14`, warm white `#ECE8E1`,
  lamp `#FFB547`) for what runs. The Ward Seal is the only mark: no gradient,
  no glow, no rotation, no photo behind it. Ward bars (three short vermillion
  rules) are the only divider. Fraunces display, IBM Plex Sans body, IBM Plex
  Mono code, self-hosted (no Google Fonts).
- Lucide icons only; no emoji anywhere, including quoted bot copy.
- Every claim true today or labelled in development. Every screenshot and
  GIF frame carries its harness and date; the Agent Worlds hero is the real
  renderer fed a scripted timeline and says so in the frame. No star or user
  counts, logo walls or testimonials.
- The compatibility matrix and the channel matrix are copied from the
  README, never widened: Claude Code verified for chat only, overnight
  unverified on every harness, five chat apps with buttons, WhatsApp typed,
  four chat-only.
- Prerendered static HTML on every page; a visible pause control on every
  looping surface; reduced motion draws once.
- Deploy: Vercel project from `site/`, production host
  https://getjunction.dev until the owner buys the Warding domain. No GitHub
  Pages workflow (Astro's absolute asset paths break under a sub-path). The
  `site.yml` workflow is a test-and-build gate only.
