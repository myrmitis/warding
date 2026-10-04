# ADR 0008 — The product is renamed to Warding

- Status: accepted
- Date: 2026-09-26
- Supersedes: the name decision in
  [ADR 0001](0001-product-identity.md). Everything else in 0001 (identifiers
  that stay, the brand gate) still holds.

## Context

The name Junction collided with a paid product in the same niche that ranks
first for the same searches, and the `junction` names on PyPI and npm were
already taken, so the install command the README promised could never be
true. The switching cost was near zero: no release, no published package, no
users to migrate.

The rename also carries a new story. The tree's defensible corner is not
model routing (the catalog lists names and forwards nothing) and not
multi-agent (others have that too). It is one coding agent kept working
overnight on the operator's own machine, reachable from chat, under a policy
the agent cannot read or rewrite. The name had to say that.

Criteria: a real word that verbs; names the mechanism; pronounceable on first
sight; four to seven letters for the CLI; `.dev`, PyPI and npm free; no
same-category product; no Kiro in it.

## Decision

The product is **Warding**. In a lock, the wards are the fixed ridges that
stop every wrong key from turning: the policy file lives on a path the agent
is denied at Warding's own gate and inside the OS sandbox, so the key cannot
rotate. The older sense — warding off harm, a ward under protection — fits
the product whose story is that the lamp stays on.

| Surface | Spelling |
|---|---|
| Prose / dashboard default | Warding |
| Company | Warding Labs |
| Primary CLI | `warding` (`junction._bootstrap:main`) |
| Silent alias | `junction` (same entry point, no warning) |
| Tagline | The lamp stays on. The rules stay shut. |
| Mark | the Ward Seal (`assets/brand/ward-seal*.svg`, `assets/banner.svg`, `website/public/logo.svg`, `website/public/favicon.svg`) |
| Site | https://getjunction.dev until the owner registers the Warding domain, then a path-for-path 301 |
| Electron `productName` | Warding (package name stays `junction-desktop`, `appId` unchanged) |

Availability at decision time: `warding.dev` unregistered, PyPI `warding`
free, npm `warding` free, no product named Warding in AI or developer tools.
`warding.com` is registered by an unrelated party and is accepted.

### Identifiers that stay

Python package `junction`; `JUNCTION_HOME`, `JUNCTION_*` environment
variables; data home `~/.junction` (`JUNCTION_HOME`), which stays on the
sensitive-path deny list; GitHub slug `laqaer/junction`;
Electron package name `junction-desktop` and its `appId`; the `junction`
console script as a silent alias; the file `JUNCTION.md` (kept so links
resolve).

## Alternatives

| Name | Verdict |
|---|---|
| Keeplit | Clean on every check; fits the night story. **The fallback** if the trademark knockout on Warding is unclear. |
| Lampkeep | Clean, eight letters, less distinctive. Second fallback. |
| Lampon | Reads as "lampoon". Rejected. |
| Okayed | Dies lowercased; its bet (chat-only channel approvals) is unbuilt. Rejected. |
| Udal | Not pronounceable on first sight. Rejected. |
| Unpaged | Belongs to a different company. Rejected. |
| Junction | The previous name. Same-category collision, PyPI and npm taken. Superseded. |

## Consequences

- `warding` is the console script and the CLI name in help, usage, banners,
  installers and the README; `junction` keeps working silently.
- `PRODUCT_NAME` is `Warding`; the dashboard renders it through
  `{{productName}}`; the PWA manifest, `<title>`, Electron display name and
  the splash say Warding.
- The README, `PRODUCT.md`, `JUNCTION.md`, `WORKING_BRIEF.md`, `ROADMAP.md`,
  `ARCHITECTURE.md` and `SECURITY.md` carry the new identity and the NO-SAY
  list; the model catalog is never a headline.
- The retired identity appears on no added line (the brand gate enforces
  this); never Kiro in the product name, tagline, logo or domain.
- Raster assets that were generated from the previous mark are stale until
  regenerated from the seal (owner or CI action below).

## Owner actions

1. **Trademark knockout** on "Warding", "Warding Labs" and the phonetic
   neighbours Warden / AI Warden (classes 9 and 42, USPTO and EUIPO; the
   Warden cluster is crowded in this exact field). If unclear, promote
   Keeplit without another round.
2. **Buy the domain** (`warding.dev`; `.run`, `.sh`, `.so` at a registrar
   once checked) and 301 `getjunction.dev` to it path-for-path, then change
   `SITE_URL` in `src/junction/constants.py`.
3. **GitHub org** (`warding` or `warding-dev`) and the repository rename with
   GitHub's redirect from `laqaer/junction`; update the remote list in
   `scripts/get-junction.sh` afterwards.
4. **Handles the same hour:** npm `warding`, PyPI `warding`, X, Reddit,
   Product Hunt, Discord, YouTube. Publish "Warding has no token or coin".
5. **Replace the previous mark's sources under `assets/brand/`** (`mark*.svg`,
   `glyph.svg`, `wordmark.svg`, `lockup-*.svg`, `app-icon*.svg`, `build.py`,
   `raster.mjs`) with the seal set (`ward-seal*.svg`), retire the Overpass
   fonts under `site/public/fonts` and `website/public/fonts` in favour of
   the brand's Fraunces and IBM Plex families, and **regenerate the raster
   brand assets** from `assets/brand/ward-seal-paper.svg`:
   `website/electron/icon.icns`, `icon.ico`, the nightly variants,
   `website/electron/build/icons/*.png`, `website/public/icon-192.png` and
   `icon-512.png`, `src/junction/static/junction-logo.png` and its nightly
   variant, and the installer rasters (`packaging/installer-assets/*.tiff`,
   `*.bmp`, via `packaging/installer-assets/build-assets.mjs`).
6. **Rename the desktop artifact chain in one release-engineering PR** before
   the first desktop release: electron-builder now emits `Warding-*` files,
   while `website/electron/auto-update.js` and the release and publish
   workflows still name `Junction-*` artifacts and `Junction.dmg`.

## Not decided here

The dashboard's Warding Paper and Warding Night themes, the Astro marketing
site's build, and the Supporter deliverables are product work tracked in
[`ROADMAP.md`](../../ROADMAP.md).
