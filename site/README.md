# Warding website publishing bundle

This revision publishes a reviewed static export: 37 prerendered HTML pages plus
compiled browser islands, CSS, images, fonts, feeds, legal notices and social
cards. It keeps the verified appearance and interactions byte-identical to the
qualified source tree recorded in `static-manifest.json`.

```bash
npm ci
npm run build
npm test
```

Node >= 22.12. The publishing build uses Node standard-library file and hash
operations. Vitest is the sole installed development tool; all five existing
page suites run over the actual `dist/` that is served. No npm audit scope,
license policy or page assertion is weakened.

`static/` is the reviewed publishing input. `scripts/build-static.mjs` checks its
complete inventory and SHA256 bytes before copying it to `dist/`. It also checks
all preserved authoring inputs against the recorded source revision, refusing
unreviewed source changes, stale exports, extra files, special files or symlinks.

The former Astro/React/MDX authoring files in `src/`, `public/` and
`astro.config.mjs` and `authoring-tsconfig.json` remain as provenance. This publishing build **does not
recompile them**. Editing those files is not enough to change the website: the
build fails until a fresh export is independently reviewed and its manifest is
updated. Static HTML/assets may be revised directly, with a reviewed manifest
change and the complete page/browser gates. No automatic snapshot-blessing
command is provided. This is the maintenance tradeoff of this static revision.

Astro's current dependency graph includes Sharp/libvips and
http-cache-semantics even when image processing is disabled. The publishing
bundle genuinely removes Astro, Sharp, http-cache-semantics, Satori, fflate and
resvg from its dependency graph. Optimized image variants and all social cards
are already stored as static files. Runtime browser JavaScript is retained;
font and compiled-runtime licenses are served in `/THIRD-PARTY-LICENSES.txt`.
Required root NOTICE/LICENSE attribution remains served verbatim.

Public Warding source is available. The reviewed pages link source availability
and beta notes. Release downloads and installation qualification remain pending. Clipboard
permission remains unverified/blocked; the guarded future copy UI describes
manual selection and never retries via another API or claims failed copies
succeeded. Product/backend runtime paths are not qualified by website tests.

## Source-availability correction, 2026-11-01

The publishing bundle was recovered from Vercel deployment `dpl_2hB46QmGS5MzWjTzcoy62ti71p8d`.
Every recovered file matched its uploaded SHA-1 before editing. The recovery inventory remains linked from the task receipt.
Public source and setup documentation are available at https://github.com/myrmitis/warding.
Clean-machine installation, live delegation and overnight reliability remain unqualified.
The publishing build still uses the reviewed static export. It does not recompile Astro authoring inputs.
The served NOTICE follows the canonical repository NOTICE and preserves upstream attribution.

E2E: serve `dist/` with an HTTP server, then run `node scripts/verify-public-source.mjs http://127.0.0.1:PORT`.
Run the same command against the staged deployment and https://warding.dev after promotion.
The check verifies public-source navigation, beta limits, demonstration disclosures and referenced browser assets.

If direct Vercel CLI requests time out, retry with `NODE_OPTIONS=--dns-result-order=ipv4first`.
This setting changes address selection for that command. It does not change system networking or credentials.
Verify complete file bytes against the retained deployment inventory before using recovered source.

The publishing build copies the canonical root NOTICE into `dist/notice.txt` after verifying its authoring-input hash.
The static source omits a duplicate NOTICE. The served attribution remains byte-identical to the canonical file.
