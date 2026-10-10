# Signing Infrastructure

This directory contains the macOS code signing and notarization scaffolding for
the Warding desktop app. Signing is the standard Developer ID flow: `codesign`
on the macOS runner, with the identity imported from a `.p12` secret into a
temporary keychain. `docs/build/signing-runbook.md` documents the whole chain,
the secrets it reads, and credential rotation.

## What is committed, and what is not

The entitlements, the scripts, and the signing order logic are committed. The
signing identity is not: it lives only in the `APPLE_DEVELOPER_ID_P12_BASE64` and
`APPLE_DEVELOPER_ID_P12_PASSWORD` secrets of the `prod` environment. A fork or
any repository without them skips signing entirely (the workflow produces
unsigned builds that work but trigger macOS Gatekeeper warnings). The team ID and
the bundle identifier are not secrets either way: they are embedded in every
signed `.app` a user downloads.

## Files

- `Entitlements.entitlements` — macOS entitlements for the Electron app.
  JIT + disable-library-validation are required for V8/Node.js + native addons.
- `signing-plan.py` — derives the inside-out signing order from the actual
  bundle: every nested Mach-O (the embedded Python backend included), then every
  nested code bundle, deepest first, each marked with whether it takes the
  entitlements.
- `sign.sh` — Developer ID signs a `.app` in place by following that plan, with
  the hardened runtime and a secure timestamp, then verifies the result
  (`codesign --verify --deep --strict` and a Developer ID Application authority).
- `sign-dmg.sh` — Developer ID signs the shipping DMG in place and fails closed
  unless the result carries a Developer ID Application authority.
- `build-dmg.sh` — replaces the unsigned app inside electron-builder's branded
  DMG layout template with the signed/stapled app, then shrinks and recompresses
  the image before the DMG signing and notarization stages.

  The mounted-volume phase races Spotlight and XProtect, which start reading
  the freshly-copied app and can hold the volume against ejection ("Resource
  busy") — the same transient class electron-builder retries on. The script
  layers its defenses: `-nobrowse` keeps the volume out of Finder, and the
  eject gets bounded retries with a synced force fallback. hdiutil calls run without `-quiet`, because
  that flag suppresses stderr too and previously reduced failures of this
  script to bare exit codes.

  The branded background is a **volume-bound alias recorded inside `.DS_Store`**,
  which is why the image is reused rather than rebuilt from a folder: recreating
  it drops the layout. The script fingerprints the template's `.DS_Store` before
  the swap and requires the final image to carry the same bytes, which is
  stronger than checking the files exist — a broken alias leaves every file in
  place. It still cannot prove Finder *resolves* the alias, since that also
  depends on the volume identity the alias binds to, and nothing on a CI runner
  re-renders the window.

  **So two things are worth doing rather than assuming green CI covers them.**
  First, watch the next real signing run: the unsigned-DMG round trip through the signing bucket, the
  sector-resize arithmetic and the app swap all execute for the first time
  there, not in PR CI. Second, know the fallback — if the alias ever stops
  surviving, run `dmgbuild` against the **stapled** app inside the notarize job.
  That writes a fresh, correct `.DS_Store` and removes the template round trip,
  the resize arithmetic and the survival question in one move; the only reason
  it is not the default is that it re-derives the layout on every release
  instead of preserving the one the build already produced.

## Prerequisites

Signing needs a Developer ID Application certificate for the project's Apple
Developer team, exported with its private key as a `.p12`. Creating, storing and
rotating it is covered in `docs/build/signing-runbook.md`.

To sign locally, import the identity into your keychain and run
`SIGNING_IDENTITY="Developer ID Application: <Name> (<TEAMID>)" bash packaging/signing/sign.sh <App.app>`.

## CLI artifact manifests (separate trust domain)

The wheel installer does **not** reuse the Apple signing identity. `publish-cli.yml` signs a
canonical JSON artifact manifest with an RSA release key and publishes the
same signed JSON at both:

- `cli/<channel>/<version>/cli-manifest.json` (immutable, used by `--version`)
- `feed/<channel>/latest-cli.json` (mutable channel pointer)

The legacy `channel`, `version`, `wheel_url`, `sha256`, `python_requires`, and
`pub_date` fields remain top-level for older installers. Schema v1 adds
`schema`, `algorithm`, `key_id`, and `signature`. The signature is RSA
PKCS#1 v1.5 with SHA-256 over canonical JSON containing every field except
`signature`. `cli.sh` reconstructs those exact bytes, verifies them with the
offline public key embedded in the installer, validates the authenticated URL,
channel, version, and digest, and only then downloads the wheel. The SHA-256
check remains a second fail-closed check over the downloaded bytes. There is no
`SHA256SUMS` or unsigned-feed fallback in the strict installer.

Threat model: this protects against unauthorized mutation of distribution
objects or channel feeds while the installer trust root and the release key
remain trusted. The key is the `CLI_MANIFEST_SIGNING_KEY` secret of the
protected `prod` environment, so anyone able to run a workflow in that
environment can sign a valid manifest, or read the key out of it; that is
explicitly out of scope, and the signature creates no trust boundary separate
from the environment. Its protection rules (deployment branch and tag policy,
optionally required reviewers) are what guard releases.

### Enabling the release key

Until step 4 lands, `cli.sh` and `cli-manifest-public.pem` pin a public key
whose private half this project does not hold, so every signed install fails
closed and a publish fails at its signing step. A trusted publisher
configuration with only one of the R2 credentials and the signing key fails
before any upload. Forks with neither setting still skip publication.

The private key is generated on a maintainer's own machine and leaves it only
into the secret store: never committed, never pasted into chat, an issue or a
workflow file, and never handled by an agent.

1. Generate the key where only you can read it:
   `openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out cli-manifest-signing-key.pem`.
   The helper refuses anything under 3072 bits and an RSA-PSS key. Leave the
   PEM unencrypted: nothing in CI can supply a passphrase.
2. Store the whole unencrypted PEM as the `CLI_MANIFEST_SIGNING_KEY` secret of
   the `prod` environment, for example
   `gh secret set CLI_MANIFEST_SIGNING_KEY --env prod < cli-manifest-signing-key.pem`.
   Keep one offline backup, then delete the working copy.
3. Write the **public** half over the committed one:
   `openssl pkey -in cli-manifest-signing-key.pem -pubout -out packaging/signing/cli-manifest-public.pem`.
4. Run
   `python3 packaging/signing/cli-manifest.py key-info --public-key packaging/signing/cli-manifest-public.pem`.
   Copy the returned public `key_id` and `public_key_pem_base64` values into the
   matching constants in `cli.sh`. Commit the public-key pin normally. No
   installer has shipped yet, so this first pin replaces the old key outright.
5. Set the R2 credentials and variables listed in
   `docs/build/signing-runbook.md`. Before every signature the workflow derives
   the public half of the secret key and compares it byte-for-byte with the
   committed key, and it verifies its own signature before publishing.
6. Run `test/test_cli_manifest_signature.py`, then dispatch a publish and verify
   the immutable manifest is present. Publish the strict `cli.sh` only after a
   signed channel feed exists. Because the added fields are backward-compatible,
   the signed feed may safely go live before the strict installer. This ordering
   is enforced mechanically: `publish-installer.yml` refuses to publish while
   `cli.sh` still pins `CLI_MANIFEST_KEY_ID="UNCONFIGURED"`, and — once a key
   is pinned — refuses unless every LIVE channel feed verifies against that
   key (`cli-manifest.py verify`, the same checks the installer runs), so
   neither the pin commit nor any later merge can replace the live installer
   with one that refuses the feeds it is pointed at.

Pinned versions released before enablement have no immutable signed manifest and
therefore fail closed under the new installer unless an authorized backfill signs
the already-published digest. Once an installer has shipped, do not replace the
key in place: schema v1 pins one key. For rotation, first ship an installer
revision that trusts both old and new public keys, then switch the secret, and
retire the old key only after the overlap window. If the key is exposed, rotate
the same way but shorten the window to what the installed base allows.
