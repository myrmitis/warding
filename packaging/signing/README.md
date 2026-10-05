# Signing Infrastructure

This directory contains the macOS code signing and notarization scaffolding for
the Junction desktop app. Signing is the standard Developer ID flow: `codesign`
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
  First, watch the next real signing run: the unsigned-DMG S3 round trip, the
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
canonical JSON artifact manifest with an asymmetric AWS KMS key and publishes the
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
objects or channel feeds while the installer trust root and signing-enabled
publisher role remain trusted. The publisher role holds `kms:Sign`, so its
compromise can produce a valid manifest and is explicitly out of scope; the
signature does not create a separate trust boundary from that role.

### Repository bootstrap state

The repository intentionally carries `UNCONFIGURED` in both
`cli-manifest-public.pem` and the two `CLI_MANIFEST_*` constants in `cli.sh`.
This is fail-closed: the installer exits before network I/O, and a trusted
publisher configuration with only one of the role/key settings fails before any
upload. Forks with neither setting still skip publication.

No private key should be generated, exported, committed, pasted into CI, or
handled by an agent. Operational enablement is a human/infrastructure step:

1. Create a non-exportable asymmetric KMS key in `us-west-2` with key usage
   `SIGN_VERIFY` and key spec `RSA_3072` or `RSA_4096`.
2. Grant the existing CLI publication role only `kms:GetPublicKey` and
   `kms:Sign` on that one key. Keep the existing OIDC subject/environment
   restriction; do not grant decrypt or broad `kms:*` access.
3. Retrieve the **public** key with `kms:GetPublicKey`, convert its
   SubjectPublicKeyInfo DER bytes to PEM, and replace
   `packaging/signing/cli-manifest-public.pem`.
4. Run
   `python3 packaging/signing/cli-manifest.py key-info --public-key packaging/signing/cli-manifest-public.pem`.
   Copy the returned public `key_id` and `public_key_pem_base64` values into the
   matching constants in `cli.sh`. Commit the public-key pin normally.
5. Set the protected `prod` environment variable
   `CLI_MANIFEST_SIGNING_KEY_ARN` to the key ARN. The workflow compares KMS
   `GetPublicKey` output byte-for-byte with the committed key before every sign,
   and verifies the returned signature locally before publishing.
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
the already-published digest. Do not replace the KMS key in place: schema v1 pins
one key. For rotation, first ship an installer revision that trusts both old and
new public keys, then switch the publisher, and retire the old key only after the
overlap window.
