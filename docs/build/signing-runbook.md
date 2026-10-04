# Desktop Signing and Notarization Runbook

Operational reference for Junction's desktop code signing: the macOS chain
(Developer ID codesigning, Apple notarization and stapling), the Windows
Authenticode certificate, the secrets and variables each one reads, and rotation
of every credential involved.

The macOS pipeline lives in `.github/workflows/sign-and-notarize.yml`, a reusable
workflow called by `nightly.yml` (channel `nightly`) and `release.yml` (channels
`insider` and `stable`). The scripts it drives are in `packaging/signing/`.
Windows signs inside `.github/workflows/build-windows.yml` and is verified again by
`.github/workflows/publish-windows.yml`. Release mechanics as a whole live in
[release.md](release.md); desktop packaging in [desktop-app.md](desktop-app.md).

## Secrets and variables

With **no** signing inputs at all, every lane skips cleanly and the build produces
the same unsigned artifacts, under the same names, that a fork produces; nothing
fails for want of a credential. A **partial** configuration fails closed on
purpose, with an error naming what is missing, rather than shipping something
half-signed:

- a Developer ID identity without `AWS_SIGNING_ROLE_ARN` fails the macOS `sign` job,
  because the unsigned app was never staged for `notarize` to read;
- a Windows certificate without its password fails the Windows build;
- with `AWS_SIGNING_ROLE_ARN` set, the Windows publish lane refuses to publish an
  unsigned installer, one signed under a different CN, or any installer at all
  while `WINDOWS_SIGNING_SUBJECT_CN` is unset.

Store the secrets as **`prod` environment secrets**, not repository secrets: every
job that reads them runs in `prod`, and the environment's ref policy (below) is what
keeps a production identity away from unmerged code.

| Name | Kind | Read by | Purpose |
|---|---|---|---|
| `APPLE_DEVELOPER_ID_P12_BASE64` | secret | `sign-and-notarize.yml` | Base64 of a `.p12` exporting the **Developer ID Application** certificate and its private key. Its presence is the macOS signing gate (`HAS_SIGNING_IDENTITY`). |
| `APPLE_DEVELOPER_ID_P12_PASSWORD` | secret | `sign-and-notarize.yml` | The export password of that `.p12`. |
| `AWS_SIGNING_ROLE_ARN` | secret | `sign-and-notarize.yml`, the publish lanes | OIDC role that stages unsigned artifacts, reads the notary credential, and writes the distribution bucket. |
| `AWS_SIGNING_BUCKET` | secret | `sign-and-notarize.yml` | The private staging bucket (`pre-signed/`, `notarized/`). |
| `junction/signing/apple-notary` | AWS Secrets Manager | `sign-and-notarize.yml` | The Apple notary credential (see [The notary credential](#the-notary-credential)). |
| `WINDOWS_SIGNING_CERT_P12_BASE64` | secret | `build-windows.yml` | Base64 of the Authenticode code-signing `.pfx`/`.p12`. Its presence (together with the `prod` environment) is the Windows signing gate (`HAS_WINDOWS_SIGNING`). Only a certificate whose private key may legitimately be exported fits here; see [Key custody](#key-custody-a-pfx-cannot-hold-a-public-certificate). |
| `WINDOWS_SIGNING_CERT_PASSWORD` | secret | `build-windows.yml` | Its password. Setting the certificate without it fails the build with a named error rather than deep inside signtool. |
| `WINDOWS_SIGNING_SUBJECT_CN` | repository variable | `publish-windows.yml` | The subject CN of that certificate, exactly as it appears in the certificate, commas included. The publish lane refuses any installer whose signer carries a different CN, and refuses to publish at all while it is unset. |

To produce a base64 value for a secret: `base64 -i DeveloperID.p12 | pbcopy` on
macOS, or `base64 -w0 cert.pfx` on Linux. Never commit the certificate or paste its
password anywhere but the secret store.

## macOS chain overview

The three jobs are chained so that un-notarized bytes have no path to
distribution.

```
build-desktop  ->  unsigned .app inside an electron-builder *-mac.zip
  |
sign      (ubuntu)  flatten artifacts, attest wheel/sdist/AppImage provenance,
                    upload unsigned artifacts to pre-signed/<channel>/<version>/,
                    hand the mac zip and DMG keys to notarize
  |
notarize  (macOS)   import the Developer ID identity into a temporary keychain,
                    codesign the app inside-out (packaging/signing/sign.sh),
                    notarytool submit --wait, stapler staple, spctl gate,
                    build a DMG from the STAPLED app, codesign the DMG
                    (packaging/signing/sign-dmg.sh), notarize + staple + gate the
                    DMG, attest it, attach the gated artifact to the run, and
                    delete the keychain in an always() step
  |
publish   (ubuntu)  copy the gated artifact to the public distribution bucket,
                    then write feed/<channel>/latest-mac.yml
```

Key properties, each load-bearing:

- **Signing is gated on the identity secret.** With no
  `APPLE_DEVELOPER_ID_P12_BASE64` the `sign` job still flattens, attests and
  stages, but its handoff outputs stay empty, so `notarize` and `publish` skip. An
  identity configured without `AWS_SIGNING_ROLE_ARN` fails the `sign` job, because
  the unsigned bytes were never staged for `notarize` to read.
- **The unsigned-zip key handoff is internal** (`sign` job outputs
  `unsigned_zip_key` and `unsigned_dmg_key`, consumed by `notarize`), not plumbed
  through every caller.
- **The signing identity and the Apple credential are confined to the `notarize`
  job.** The `.p12` is decoded to disk only for the length of the import step and
  imported into a keychain under `RUNNER_TEMP` with a random per-run password,
  never the login keychain. The last step of the job deletes that keychain under
  `always()`, so the identity does not outlive a failed run either. The notary
  password is fetched from AWS Secrets Manager, masked, and used inside single
  steps; it is never written to `GITHUB_ENV`, a file, or a log, and the `publish`
  job never touches either credential.
- **The Gatekeeper gate fails closed.** `spctl` must report
  `source=Notarized Developer ID` for the app (`--type execute`) and for the DMG
  (`--type install`), or `notarize` fails and `publish` never runs. On a
  non-Accepted notarization the itemized Apple log is printed.
- **`publish` consumes only the artifact `notarize` attached after the gate**, in
  the same run. `release.yml`'s `github-release` job accepts macOS assets only
  from that same gated artifact, so the unsigned electron-builder zip and DMG are
  inter-job inputs and can never become release assets.
- **The feed is written last**, after both artifacts are publicly downloadable.
  An un-notarized artifact in the update feed would auto-update clients to a
  build Gatekeeper blocks.
- **Versioned distribution keys are never republished with different bytes.** Both
  the zip and the DMG are written with `--if-none-match '*'`; a `PreconditionFailed`
  on a job re-run keeps the existing bytes, which already passed the gate on the
  earlier attempt. The keys are CloudFront-immutable-cached.

`publish` is a separate ubuntu job on purpose: a transient publish failure retries
as a roughly-two-minute job rather than repeating two Apple submissions with
30-minute budgets each, and the expensive macOS runner never burns minutes on S3
uploads. Linux publishing takes no part in this trust chain; the AppImage ships
from `publish-linux.yml`.

## The signing order is derived from the bundle

Apple notarization requires **every** nested Mach-O binary to be Developer ID
signed with the hardened runtime and a secure timestamp. The Junction bundle holds
far more nested code than an Electron shell: the embedded Python backend under
`Contents/Resources` ships an interpreter, every `.so` C-extension and every
vendored `.dylib`, and that set changes whenever a Python dependency changes, the
app is renamed, or Electron is upgraded. So `packaging/signing/signing-plan.py`
derives the order from the actual `.app` at sign time, and `sign.sh` follows it:

1. Every Mach-O file that is not a symlink and not a bundle's main executable,
   deepest path first. Executables (`MH_EXECUTE`: the Python interpreter, ShipIt,
   `chrome_crashpad_handler`) are signed with the entitlements; loadable code
   (dylibs, extensions, `.node` addons) without.
2. Every nested code bundle, deepest first: the Electron helper `.app`s with the
   entitlements, the frameworks without. A code bundle is a directory with a bundle
   suffix whose `Info.plist` names a `CFBundleExecutable` that exists; signing the
   bundle is what signs that executable and binds it to the bundle's resources.
3. The app itself, last, with the entitlements.

Every call is `codesign --force --options runtime --timestamp`, retried on a
transient failure (a timestamp-server blip must not sink a bundle with hundreds of
nested objects). `sign.sh` then runs `codesign --verify --deep --strict` and
requires an `Authority=Developer ID Application` line, so anything the plan missed
fails here rather than as an `Invalid` notarization later.

## Why the DMG carries its own Developer ID signature

`hdiutil`-created DMGs carry an **adhoc** signature. The Apple notary service
Accepts that, but Gatekeeper treats it as no usable signature and shows "app is
damaged" when a user drags the app out of the quarantined mount (the
`syspolicy_check` reading is: app passed, DMG failed). An unsigned DMG also cannot
be stapled at all (`stapler` Error 73), so first-install verification would need
network access.

So the DMG is built **from the already-stapled app**, then signed with the same
identity by `packaging/signing/sign-dmg.sh`, then notarized and stapled itself. The
script fails closed: it runs `codesign --verify --strict` and requires an
`Authority=Developer ID Application` line on the result. The `spctl --type install`
gate in the workflow is exactly the check that catches an adhoc regression.

The DMG signs under the **app's own** bundle identifier (`dev.junction.desktop`),
read from the stapled bundle's `Info.plist` rather than hardcoded, so the image's
signature names the product rather than its filename.

Published **filenames** are pinned to the `Junction` basename on every channel,
even though the nightly bundle is `Junction Nightly.app`. CDN keys and the
latest-DMG permalink (`desktop/<channel>/latest/Junction.dmg`) are a public
contract, so deriving filenames from the bundle name would silently rename keys
and break the permalink. The DMG's **volume** name does follow the bundle.

## Entitlements: two files, one contract

`packaging/signing/Entitlements.entitlements` is the release-lane entitlements
file. `website/electron/build/entitlements.mac.plist` is the electron-builder-lane
twin. **The two signing paths read their OWN file**, so a key present in only one
of them means that lane ships a broken bundle.
`website/electron/test/packaging.test.js` pins both.

Under the hardened runtime an entitlement, not the `Info.plist` usage string, is
what grants a device capability. `com.apple.security.device.audio-input` is what
makes the microphone work for voice input and streaming STT; without it the mic is
refused with **no prompt at all** and no System Settings toggle to fix it. Camera
is deliberately absent, because `permission-handler.js` denies video.

Not every protected resource works that way, so do not generalize the mic rule.
**Local network access has no entitlement** — on macOS 15 it is gated by TCC alone
and declared solely by `NSLocalNetworkUsageDescription` in
`website/electron/package.json`'s `build.mac.extendInfo`, which both lanes inherit
from the same built bundle. Requesting
`com.apple.developer.networking.multicast` to "fix" LAN access breaks signing
unless Apple has provisioned it, and `com.apple.security.network.client` is an
App-Sandbox key this bundle has no use for. `packaging.test.js` asserts both stay
out of both files.

## Provenance is attested only for final bytes

The `sign` job attests the wheel, sdist and AppImage. It deliberately omits the
macOS `.zip` and the build job's DMG, because those are signed downstream and a
pre-notarization attestation would bind a digest that never ships. The shipping
DMG is attested in the `notarize` job **after** stapling, since stapling embeds the
ticket into the file and therefore changes the released bytes.

## OIDC subject alignment and the `prod` environment

All three jobs declare `environment: prod`. Tag-triggered callers (`release.yml`)
present an OIDC subject of `ref:refs/tags/<tag>`, which the signing role does not
trust; the `prod` environment switches the subject to `environment:prod`, which it
does. Nightly runs on `main` present either trusted form.

`prod` is protected by GitHub-side **ref restrictions** rather than required
reviewers, which would stall the unattended scheduled nightly: a deployment
branch/tag policy limits the environment to `main` and `v*` tags, and a repository
ruleset restricts `v*` tag creation, update and deletion to repository admins. An
unmerged commit can therefore only reach this environment if an admin deliberately
tags it, which is the same principal who could merge it. The same policy is what
scopes the Developer ID and Windows signing certificates, which is why they are
`prod` environment secrets.

## The Developer ID certificate

The macOS identity is a **Developer ID Application** certificate issued to the
project's Apple Developer team, exported with its private key as a `.p12`.

- **Create or renew** it in the Apple Developer portal (Certificates, Identifiers
  & Profiles), or in Xcode's Accounts settings, on a Mac whose login keychain then
  holds the private key. Only the team's Account Holder can create Developer ID
  certificates.
- **Export** it from Keychain Access (the certificate together with its private
  key, as `.p12`) with a strong export password, then set
  `APPLE_DEVELOPER_ID_P12_BASE64` and `APPLE_DEVELOPER_ID_P12_PASSWORD` in the
  `prod` environment. Delete the exported file afterwards.
- **Rotation** is additive: a new certificate signs new builds while every
  release signed and timestamped under the old one keeps verifying, so replace the
  two secrets, let the next nightly prove the new identity end to end, and only
  then revoke the old certificate if it is being retired.
- **If the `.p12` or its password is exposed**, revoke the certificate in the
  portal immediately, issue a new one, and replace both secrets. Revocation stops
  new signatures from being trusted; ask Apple Developer support about the effect
  on already-notarized releases before revoking a certificate that signed them.

## The notary credential

The credential is an Apple app-specific password for the team's enrolled Apple
account. Custody rules:

- **CI copy: AWS Secrets Manager**, secret id `junction/signing/apple-notary`,
  fetched by the same OIDC role that stages artifacts. The JSON carries
  `apple_id`, `password` and `team_id`. It is never a GitHub secret and never a
  workflow env literal: a dedicated secret store gives custody, an audit trail, and
  a rotation lifecycle that a repository secret does not.
- **Local copy: the macOS Keychain**, via
  `xcrun notarytool store-credentials "JunctionNotary" ...`. Every local command
  then uses `--keychain-profile "JunctionNotary"`.
- **Never paste the password** into chat, tickets, docs, or a shell command line
  that lands in a shared log. Type it only into the Apple portal, into
  `store-credentials` in your own terminal, or into the Secrets Manager console
  or CLI.
- **If it is ever exposed, revoke it immediately** at `appleid.apple.com`
  (app-specific passwords are individually revocable) and rotate.

### Rotation: manual mint, zero downtime

Apple exposes no API to mint app-specific passwords or App Store Connect API keys,
so the mint step is manual by necessity. Everything around it is automated. Apple
allows up to 25 concurrent app-specific passwords, so rotate generate-first and
revoke-last, and CI never breaks mid-rotation.

The procedure takes a couple of minutes, quarterly or on any exposure:

1. Sign in at `https://appleid.apple.com` with the enrolled account.
2. Sign-In and Security, then App-Specific Passwords, then generate a new one.
   Label it with a version.
3. Put the new value into the Secrets Manager secret yourself (console, or
   `aws secretsmanager put-secret-value` in your own terminal).
4. **Verify before revoking the old one:**
   `xcrun notarytool history --apple-id <account> --team-id <team> --password <new>`
   must return history, or wait for the next green notarization run.
5. Revoke the old password at `appleid.apple.com`.
6. Optionally refresh your local Keychain profile with `store-credentials`.

Rotate immediately, without waiting for the schedule, when the credential has
appeared anywhere outside the Keychain and Secrets Manager, when the owning Apple
account holder departs, or when an automated secret-age finding names it.

An App Store Connect API key is team-scoped rather than person-bound, so it has
the same manual mint but survives a departure. Requesting one is worthwhile
whenever convenient, and not urgent while the password path works.

## Windows Authenticode signing

Windows signs **inside** the build, because the NSIS installer is a
self-extracting archive of already-signed parts: electron-builder signs the app
executable, compresses it into the installer payload, then signs the installer and
its uninstaller. It does so natively through signtool when `WIN_CSC_LINK` carries a
certificate, and `build-windows.yml` sets `WIN_CSC_LINK` and `WIN_CSC_KEY_PASSWORD`
from the two `WINDOWS_SIGNING_CERT_*` secrets only when `HAS_WINDOWS_SIGNING` is
set, which also requires the `prod` environment. The any-ref `workflow_dispatch`
packaging probe therefore always builds unsigned, and so does every fork.

- **Hash and timestamp.** `signtoolOptions.signingHashAlgorithms` pins `sha256`
  alone, and electron-builder countersigns with an RFC3161 timestamp. The
  timestamp is required, not decorative: the certificate is reissued periodically,
  and an untimestamped signature stops verifying when it expires.
- **The publisher is read from the certificate.** The committed build config sets
  no `publisherName`, so electron-builder writes the signing certificate's own
  subject CN into `app-update.yml`, and `NsisUpdater` verifies every downloaded
  update against it fail-closed. The client therefore always expects the identity
  that actually signed its build.
- **The publish lane checks the same CN.** `publish-windows.yml` runs
  `scripts/verify_windows_installer.py` on the exact bytes it is about to make
  immutable and requires the signer's CN to equal `WINDOWS_SIGNING_SUBJECT_CN`,
  plus an RFC3161 countersignature. An unsigned installer, a different signer, or
  an unset variable all refuse the publish.
- **Rotating the certificate** changes the CN only when the subject changes. When
  it does, the order matters, because `NsisUpdater` checks an update against the
  `publisherName` in the *installed* app's `app-update.yml`, never the one the new
  build carries. An install that only knows the old CN refuses every update signed
  by the new certificate, whatever that update lists.
  1. Bridge first. Ship a release still signed by the **old** certificate with
     `signtoolOptions.publisherName` listing both CNs, old and new. Installs that
     update to it now trust either signer. Leave it as the latest release long
     enough for the installed base to take it: an install that skips it can only
     recover by reinstalling from the download page.
  2. Then switch. Replace `WINDOWS_SIGNING_CERT_P12_BASE64` and
     `WINDOWS_SIGNING_CERT_PASSWORD` with the new certificate and set
     `WINDOWS_SIGNING_SUBJECT_CN` to its CN at the same moment, so the publish lane
     expects the signer the build now uses.
  3. Keep both names listed until the old CN no longer matters, then remove
     `publisherName` so the build reads the CN from the certificate again. The
     `test_windows_signing_contract.py` and `build-config-schema.test.js` pins on
     an absent `publisherName` are edited in the bridge change and restored here.

### Key custody: a `.pfx` cannot hold a public certificate

The certificate flow above needs a `.pfx` that carries the private key, and a
**publicly trusted** Authenticode certificate cannot be one. Since 1 June 2023 the
CA/Browser Forum Code Signing Baseline Requirements oblige the issuing CA to ensure
the key is generated and kept on a hardware module (FIPS 140-2 Level 2 or Common
Criteria EAL 4+), so no CA issues a publicly trusted code-signing certificate with
an exportable key. Those requirements also cap validity at 39 months, so the last
certificates issued with software keys before that date have expired. A `.pfx`
secret therefore works only for a certificate whose key may legitimately leave
hardware, such as one from a private CA that the target machines already trust.

A public release has to sign through a cloud HSM or a managed signing service
(Azure Trusted Signing, DigiCert KeyLocker, SSL.com eSigner and similar), which
`build-windows.yml` does not wire yet. The seams for it already exist in
electron-builder and in the workflow:

- **A vendor signing tool** plugs in through `win.signtoolOptions.sign`, a hook
  that electron-builder calls for each file it signs, so the installer, its
  uninstaller and the app executable are all still signed inside the build.
- **Azure Trusted Signing** is `win.azureSignOptions`, which replaces
  `signtoolOptions` rather than extending it.
- **Either one needs an explicit `publisherName`.** With no certificate file there
  is no CN for electron-builder to read, so `app-update.yml` would carry no
  publisher, and `NsisUpdater` skips signature verification entirely when it has
  none. Adopting either path therefore changes the absent-`publisherName` pins and
  the rotation procedure above in the same change.
- **The gate stays the same shape.** The service credentials become `prod`
  environment secrets, `HAS_WINDOWS_SIGNING` keys on their presence instead of the
  `.pfx`, and a build without them stays unsigned. `publish-windows.yml` needs no
  change: it checks the signer CN against `WINDOWS_SIGNING_SUBJECT_CN` whatever
  produced the signature.

## Troubleshooting

**Notarization returns `Invalid`.** Pull the itemized log with
`xcrun notarytool log <submission-id> --keychain-profile JunctionNotary`. Every
listed binary must be Developer ID signed with the hardened runtime and a secure
timestamp. A listed binary means `signing-plan.py` did not reach it: check whether
it sits inside a directory that carries a bundle suffix without being a code
bundle, or behind a symlink, and run the plan against the bundle locally to see
what it lists.

**The import step finds no identity.** The `.p12` must contain the private key as
well as the certificate, and the certificate must be a *Developer ID Application*
one (an *Apple Development* or *Mac App Distribution* certificate is rejected).
Re-export from Keychain Access with the key selected.

**`codesign` fails with `errSecInternalComponent`.** The keychain was locked or its
partition list was not set, so codesign could not use the key without a prompt.
The import step sets both; a custom edit that drops either reproduces this.

**Verify a signed bundle locally.** `codesign --verify --deep --strict App.app`,
then `codesign -dvvv <binary>`, which must show an
`Authority=Developer ID Application: ...` line and a `Timestamp=`. Use `-dvvv`,
not `-dv`, or the Authority lines are omitted.

**Confirm the Gatekeeper end state.**
`spctl --assess --type execute --verbose App.app` must print
`source=Notarized Developer ID` after stapling; the DMG's equivalent is
`--type install`.

**The Windows publish refuses a signed installer.** The error names the CN the
installer carries; compare it with `WINDOWS_SIGNING_SUBJECT_CN` character for
character, including punctuation such as the comma in a legal name.
