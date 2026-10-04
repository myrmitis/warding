"""Contract tests for Windows Authenticode signing with a code-signing certificate.

Windows signing is unlike the macOS path in one structural way, and every
property below follows from it: **signing happens INSIDE the build**. The NSIS
installer is a self-extracting archive -- the app executable is signed, then
compressed into the installer payload, then the installer and its generated
uninstaller are signed -- so signing afterwards would mean unpacking and
rebuilding that structure by hand. electron-builder's own signtool integration
signs at each of those points when ``WIN_CSC_LINK`` carries a certificate.

That makes the Windows build job hold a production signing identity, which the
macOS build legs deliberately do not. It is also why Windows has its own
reusable workflow: ``build-desktop.yml`` is pinned credential-free by
``test_workflow_permissions.py``, and putting the signing leg back in it would
put the certificate within reach of the mac and Linux legs too.

The properties that keep this safe, none of which fails at PR time if broken:

* **The build job mints no OIDC token.** The certificate arrives from secrets,
  so the job needs ``contents: read`` and nothing else. The caller side is
  pinned in ``test_workflow_permissions.py``; asserted here from the callee.
* **The prod environment is requested on publishing paths.** The certificate
  is a ``prod`` environment secret, and that environment's deployment policy
  admits only main and ``v*`` tags. Without it a release build cannot read the
  certificate and ships unsigned. It must NOT be requested on the any-ref
  dispatch probe, whose refs the prod branch policy rejects.
* **The certificate and its password are gated on one flag.** The build either
  receives the whole identity or none of it. With none, electron-builder finds
  no certificate and builds unsigned, which is the documented fork and probe
  behaviour. A certificate without its password is refused before the build.
* **The client and the publish lane expect the same publisher.** The build
  config names no ``publisherName``, so electron-builder writes the signing
  certificate's own subject CN into ``app-update.yml``, and the publish lane
  checks the installer's signer against ``WINDOWS_SIGNING_SUBJECT_CN``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
BUILD_WORKFLOW = WORKFLOWS / "build-windows.yml"
ELECTRON_PACKAGE_JSON = ROOT / "website" / "electron" / "package.json"

# The secrets and variable the Windows signing chain reads. Named once so a
# rename has to be a deliberate, visible edit here and in
# docs/build/signing-runbook.md, which documents all three for operators.
CERT_SECRET = "WINDOWS_SIGNING_CERT_P12_BASE64"
CERT_PASSWORD_SECRET = "WINDOWS_SIGNING_CERT_PASSWORD"
SUBJECT_CN_VARIABLE = "WINDOWS_SIGNING_SUBJECT_CN"

# electron-builder's native Windows signing inputs, and the secret each carries.
SIGNING_ENV = {
    "WIN_CSC_LINK": CERT_SECRET,
    "WIN_CSC_KEY_PASSWORD": CERT_PASSWORD_SECRET,
}

# Callers that build Windows, and whether they publish (and so must request the
# prod environment, where the certificate lives).
PUBLISHING_CALLERS = ("nightly.yml", "release.yml")


def _workflow(name: str = "build-windows.yml") -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _build_job() -> dict:
    return _workflow()["jobs"]["build-windows"]


def _step(name_fragment: str) -> dict:
    for step in _build_job()["steps"]:
        if name_fragment in step.get("name", ""):
            return step
    raise AssertionError(
        f"no step whose name contains {name_fragment!r} in build-windows.yml; "
        "steps are: " + ", ".join(repr(s.get("name", "")) for s in _build_job()["steps"])
    )


def _win_config() -> dict:
    config = json.loads(ELECTRON_PACKAGE_JSON.read_text(encoding="utf-8"))
    return config["build"]["win"]


def test_the_build_job_mints_no_oidc_token() -> None:
    # Signing reads a certificate from secrets, so nothing in this job needs to
    # assume a cloud role. An id-token grant here would only let a build that
    # runs third-party packaging tooling present the prod environment's
    # identity to the distribution role the publish lanes assume.
    permissions = _build_job()["permissions"]
    assert "id-token" not in permissions, "build-windows needs no OIDC token to sign"
    assert permissions == {"contents": "read"}


def test_the_build_job_assumes_no_cloud_role() -> None:
    # The whole signing identity is the certificate. A credential step here
    # would be a second identity nothing consumes.
    for step in _build_job()["steps"]:
        uses = str(step.get("uses", ""))
        assert "configure-aws-credentials" not in uses, (
            f"step {step.get('name', uses)!r} configures cloud credentials; "
            "Windows signing uses the certificate secret alone"
        )


def test_publishing_callers_request_the_prod_environment() -> None:
    """Without this, release builds cannot read the certificate at all.

    The certificate is a prod environment secret. Release runs are
    tag-triggered, so without the environment the secret is simply absent,
    HAS_WINDOWS_SIGNING stays empty and the release ships an unsigned installer
    that the publish lane then refuses -- while nightly keeps working.
    """
    for caller in PUBLISHING_CALLERS:
        job = _workflow(caller)["jobs"]["build-windows"]
        assert job["with"]["use_prod_environment"] is True, (
            f"{caller} must pass use_prod_environment: true, or its build cannot "
            "read the prod-scoped signing certificate"
        )


def test_the_environment_is_conditional_so_the_any_ref_probe_survives() -> None:
    """The prod environment must be requestable, not unconditional.

    The prod environment's deployment branch policy allows only main and v*
    tags. A job-level `environment: prod` would therefore fail the any-ref
    workflow_dispatch packaging probe at job start on a feature branch --
    defeating the one mechanism for validating a packaging change before merge.
    """
    environment = _build_job()["environment"]
    assert "inputs.use_prod_environment" in environment, (
        f"environment {environment!r} must derive from the use_prod_environment "
        "input. Note it cannot test github.event_name: inside a called reusable "
        "workflow the github context reflects the CALLER's event, so event_name "
        "is never 'workflow_call' and the environment would never be applied."
    )


def test_the_soft_fail_input_is_declared_on_every_trigger() -> None:
    """A job-level expression reading an input must find it on BOTH triggers.

    `continue-on-error` is evaluated before any job starts. When it reads an
    input a trigger does not declare, the value is empty, the key is not a
    boolean, and GitHub rejects the whole workflow at startup: the run ends in
    seconds with ZERO jobs and no log. That is how the dispatch probe path died
    silently once already in build-desktop.yml.
    """
    text = BUILD_WORKFLOW.read_text(encoding="utf-8")
    referenced = set(re.findall(r"inputs\.([A-Za-z_][A-Za-z0-9_]*)", text))
    assert referenced, "build-windows.yml no longer references any inputs"

    # PyYAML resolves the bare key `on` to the boolean True (YAML 1.1), so the
    # trigger block is not reachable under the string "on".
    workflow = _workflow()
    triggers = workflow[True] if True in workflow else workflow["on"]
    for trigger in ("workflow_call", "workflow_dispatch"):
        declared = set((triggers[trigger] or {}).get("inputs", {}))
        missing = referenced - declared
        assert not missing, (
            f"{trigger} does not declare input(s) {sorted(missing)} that a "
            "job-level key reads. GitHub rejects the workflow at startup on "
            "that trigger and the run produces zero jobs."
        )


def test_continue_on_error_is_boolean_safe() -> None:
    """continue-on-error must coerce to a boolean even for an absent input."""
    expr = str(_build_job()["continue-on-error"])
    assert "== true" in expr or "fromJSON" in expr, (
        f"continue-on-error expression {expr!r} yields the input's raw value; an "
        "absent input then makes it non-boolean and GitHub rejects the workflow "
        "at startup. Compare explicitly (`== true`) or coerce with fromJSON."
    )


def test_electron_builder_signs_natively_without_a_custom_hook() -> None:
    # A `sign` hook replaces electron-builder's own signtool call. With the
    # certificate delivered through WIN_CSC_LINK there is nothing for a hook to
    # add, and a hook that skipped on a missing input would turn a
    # misconfigured release into a silently unsigned one.
    signtool = _win_config()["signtoolOptions"]
    assert "sign" not in signtool, (
        f"win.signtoolOptions.sign is set to {signtool['sign']!r}; the certificate "
        "flow signs through electron-builder's own signtool integration"
    )


def test_only_one_hash_algorithm_is_signed() -> None:
    # electron-builder's signtool default is ["sha1", "sha256"]: a SHA-1 primary
    # signature with a legacy countersignature and the SHA-256 one nested
    # beneath it. SHA-1 Authenticode is deprecated, the primary signature would
    # then not carry the RFC3161 timestamp the publish lane's guard is written
    # for, and every file would make two timestamp-server round trips.
    algorithms = _win_config()["signtoolOptions"].get("signingHashAlgorithms")
    assert algorithms == ["sha256"], (
        "signingHashAlgorithms must be pinned to exactly ['sha256']; found "
        f"{algorithms!r}. Leaving it unset restores electron-builder's "
        "sha1+sha256 default and signs every artifact twice."
    )


def test_local_certificate_discovery_stays_disabled() -> None:
    # The only certificate this build may sign with is the one WIN_CSC_LINK
    # carries; nothing on the runner is allowed to stand in for it.
    env = _step("Build desktop app")["env"]
    assert env["CSC_IDENTITY_AUTO_DISCOVERY"] == "false"


def test_the_signing_inputs_carry_the_certificate_secrets() -> None:
    # electron-builder reads exactly these two names. A typo on either side
    # builds a working installer with no signature and says nothing about it.
    env = _step("Build desktop app")["env"]
    for name, secret in SIGNING_ENV.items():
        assert name in env, f"the build step no longer sets {name}"
        assert f"secrets.{secret}" in str(
            env[name]
        ), f"{name} must carry secrets.{secret}; found {env[name]!r}"


def test_the_signing_inputs_are_gated_on_the_signing_flag() -> None:
    """The certificate and its password reach the build as ONE unit, or not at all.

    Set unconditionally, a repository-level copy of the secret would reach the
    any-ref dispatch probe and hand the production identity to an unmerged
    feature branch. Gated on HAS_WINDOWS_SIGNING, which also requires the prod
    environment, the probe and every fork build unsigned.
    """
    env = _step("Build desktop app")["env"]
    for name in SIGNING_ENV:
        assert "env.HAS_WINDOWS_SIGNING" in str(env[name]), (
            f"{name} is set without the HAS_WINDOWS_SIGNING gate, so the signing "
            "identity can reach a run that is meant to build unsigned."
        )


def test_signing_gate_is_hoisted_into_job_env() -> None:
    # `secrets.*` is not available in a step-level `if`, so the gate has to be a
    # job-level env flag. Same pattern as sign-and-notarize.yml.
    gate = _build_job()["env"]["HAS_WINDOWS_SIGNING"]
    assert f"secrets.{CERT_SECRET}" in gate


def test_the_signing_gate_also_requires_the_prod_environment() -> None:
    """Signing needs the secret AND the environment, so the gate needs both.

    Gating on the secret alone means that the moment a repository-level copy of
    the certificate exists, the any-ref dispatch probe signs an unmerged feature
    branch with the production identity. A probe is supposed to build unsigned.
    """
    gate = _build_job()["env"]["HAS_WINDOWS_SIGNING"]
    assert "use_prod_environment" in gate, (
        f"HAS_WINDOWS_SIGNING ({gate!r}) must also require use_prod_environment, "
        "or the any-ref packaging probe can sign with the production certificate."
    )
    assert "\n" not in gate, (
        "keep the gate on one line: a folded block scalar preserves newlines for "
        "more-indented continuation lines, which corrupts the expression"
    )


def test_a_partial_signing_configuration_is_refused_before_the_build() -> None:
    """A certificate without its password must fail fast, and by name.

    Let through, it fails deep inside signtool with an opaque PFX error after
    the whole app has been built. The guard runs only when signing is gated on,
    so a fork or a probe (no certificate at all) still builds unsigned.
    """
    guard = _step("Refuse partial Windows signing configuration")
    assert "HAS_WINDOWS_SIGNING" in guard["if"]
    assert f"secrets.{CERT_PASSWORD_SECRET}" in str(guard["env"])
    assert "::error::" in guard["run"] and "exit 1" in guard["run"]

    names = [s.get("name", "") for s in _build_job()["steps"]]
    guard_i = next(i for i, n in enumerate(names) if "Refuse partial Windows signing" in n)
    assert guard_i < names.index(
        "Build desktop app"
    ), "the configuration guard must run before the build it protects"


def _publish_job() -> dict:
    return _workflow("publish-windows.yml")["jobs"]["publish-windows"]


def _publish_step(name_fragment: str) -> dict:
    for step in _publish_job()["steps"]:
        if name_fragment in step.get("name", ""):
            return step
    raise AssertionError(f"publish-windows.yml has no step named like {name_fragment!r}")


def test_the_publish_lane_expects_the_publisher_the_client_verifies() -> None:
    # NsisUpdater verifies the downloaded installer's Authenticode publisher
    # fail-closed against the publisherName in the installed app's
    # app-update.yml. If the publish lane accepts a different CN than the client
    # demands, the lane happily publishes bytes that every client then refuses,
    # and the mutable latest.yml means it refuses them all at once.
    #
    # Both ends read the signing certificate. With no publisherName in the
    # config, electron-builder's WindowsSignToolManager.computedPublisherName
    # falls back to the certificate's subject CN, PublishManager copies that
    # into app-update.yml, and the publish lane compares the signer against the
    # repository variable that names the same certificate.
    #
    # A certificate rotation that changes the CN lists both names in
    # signtoolOptions.publisherName for a bridge release; that edit belongs
    # here too (docs/build/signing-runbook.md has the order).
    expected = _publish_job()["env"]["EXPECT_SUBJECT_CN"]
    assert (
        expected == f"${{{{ vars.{SUBJECT_CN_VARIABLE} }}}}"
    ), f"EXPECT_SUBJECT_CN must come from vars.{SUBJECT_CN_VARIABLE}; found {expected!r}"
    win = _win_config()
    # electron-builder 26's WindowsConfiguration is `additionalProperties: false`
    # and carries no publisherName: a win-level key fails schema validation and
    # with it every desktop build on every platform.
    assert "publisherName" not in win
    assert "publisherName" not in win["signtoolOptions"], (
        "a pinned publisherName stops electron-builder reading the CN from the "
        "certificate, so the client would expect a name the publish lane does not"
    )
    # verifyUpdateCodeSignature defaults to on (isForceCodeSigningVerification is
    # `!== false`); setting it false would drop publisherName from app-update.yml
    # and disable the check the publish guard is paired with.
    assert win.get("verifyUpdateCodeSignature") is not False


def test_the_verify_step_refuses_an_unset_expected_publisher() -> None:
    # An unset variable must refuse the publish, exactly as an unsigned
    # installer does, and say which variable to set rather than reporting a
    # confusing CN mismatch against the empty string.
    run = _publish_step("Verify the Authenticode signature")["run"]
    assert '[ -z "${EXPECT_SUBJECT_CN}" ]' in run
    assert SUBJECT_CN_VARIABLE in run
    unset_check = run.index('[ -z "${EXPECT_SUBJECT_CN}" ]')
    verifier = run.index("scripts/verify_windows_installer.py")
    assert unset_check < verifier, "the unset check must run before the verifier"
    assert "exit 1" in run[unset_check:verifier]


def test_the_published_basename_matches_the_clients_manual_download_url() -> None:
    # manualDownloadUrl() is the escape hatch a user follows when an in-app
    # update fails, so a basename drift turns the one recovery path into a 404.
    basename = _publish_job()["env"]["PUBLISHED_BASENAME"]
    auto_update = (ROOT / "website" / "electron" / "auto-update.js").read_text(encoding="utf-8")
    assert f'"{basename}.exe"' in auto_update, (
        f"publish-windows.yml publishes {basename}.exe but auto-update.js does not "
        "build that filename; the manual download link would 404."
    )


def test_windows_has_exactly_one_channel_file() -> None:
    # electron-updater's Provider.getChannelFilePrefix() appends an arch suffix
    # for linux only and returns "" for win32, so NsisUpdater requests bare
    # `latest.yml` for EVERY arch. A `latest-<arch>.yml` would be written and
    # never read, and the arm64 client would silently fetch the x64 feed. A
    # second Windows arch therefore means a second entry inside this same file.
    resolve = _publish_step("Resolve published names")["run"]
    assert "FEED_FILE=latest.yml" in resolve
    assert (
        "latest-arm64.yml" not in resolve
    ), "a per-arch Windows feed file is never requested by any client"

    # And there is no `arch` input to request one with. Absence is the guarantee:
    # a validated parameter can still be handed a value this lane does not build,
    # while a parameter that does not exist cannot. publish-linux.yml keeps its
    # `arch` because its callers pass two; both callers here pass none.
    workflow = _workflow("publish-windows.yml")
    triggers = workflow[True] if True in workflow else workflow["on"]
    assert "arch" not in triggers["workflow_call"]["inputs"], (
        "an arch input invites a value this lane cannot publish; a second arch "
        "has to edit this workflow anyway to share the single latest.yml"
    )
    for name in ("nightly.yml", "release.yml"):
        job = next(
            j
            for j in _workflow(name)["jobs"].values()
            if str(j.get("uses", "")).endswith("publish-windows.yml")
        )
        assert "arch" not in job["with"], f"{name} still passes a removed input"


def test_no_reusable_workflow_caller_uses_an_unsupported_key() -> None:
    """`continue-on-error` on a reusable-workflow call breaks the WHOLE workflow.

    GitHub's supported-keyword list for a job that calls a reusable workflow is
    exhaustive -- name, uses, with, secrets, strategy, needs, if, concurrency,
    permissions -- so an unsupported key fails workflow validation and the run
    starts NO jobs at all.

    This is a tripwire rather than hygiene. `continue-on-error` is exactly what a
    reader reaches for on discovering that a hard Windows publish failure makes
    the insider run unsuccessful, which blocks release_promotion.py from
    promoting that commit (it requires `conclusion == "success"`). The tempting
    one-line fix silently costs the entire release workflow, so the constraint is
    pinned here with the reason attached. Recovery for that coupling is
    operational: re-run the failed job and the run concludes success.
    """
    supported = {
        "name",
        "uses",
        "with",
        "secrets",
        "strategy",
        "needs",
        "if",
        "concurrency",
        "permissions",
    }
    for name in ("nightly.yml", "release.yml"):
        for job_name, job in _workflow(name)["jobs"].items():
            if "uses" not in job:
                continue
            unsupported = set(job) - supported
            assert not unsupported, (
                f"{name}:{job_name} calls a reusable workflow with "
                f"{sorted(unsupported)}, which GitHub rejects at workflow "
                "validation -- the run would start no jobs"
            )


def test_the_updater_offers_exactly_the_channels_that_publish_windows() -> None:
    # A Windows client resolving a channel with no lane fetches a feed that was
    # never written: every check 404s and the manual-download link is dead. The
    # channels the client knows and the channels that actually publish Windows
    # have to move together, in both directions.
    #
    # Expressed against KNOWN_CHANNELS rather than a Windows-specific set:
    # publish-windows.yml is wired into every channel, so a separate set would
    # be a declaration claiming a restriction that does not exist. If a channel
    # ever loses its Windows lane, this fails -- and the fix is to reintroduce
    # the restriction and report `disabled: "channel"`, not to delete the
    # assertion.
    auto_update = (ROOT / "website" / "electron" / "auto-update.js").read_text(encoding="utf-8")
    match = re.search(r"KNOWN_CHANNELS = new Set\(\[([^\]]*)\]\)", auto_update)
    assert match, "auto-update.js no longer declares KNOWN_CHANNELS"
    client_channels = set(re.findall(r'"([^"]+)"', match.group(1)))
    assert "channelHasLane(channel)" in auto_update or "channelHasLane(currentChannel())" in (
        auto_update
    ), "channelHasLane must stay the single place a channel is checked for a lane"

    nightly = next(
        job
        for job in _workflow("nightly.yml")["jobs"].values()
        if str(job.get("uses", "")).endswith("publish-windows.yml")
    )
    assert nightly["with"]["channel"] == "nightly"

    release = next(
        job
        for job in _workflow("release.yml")["jobs"].values()
        if str(job.get("uses", "")).endswith("publish-windows.yml")
    )
    # Both of release.yml's channels publish, and stable must reach the lane
    # through PROMOTION rather than a fresh build: it republishes the bundle
    # resolve-promotion verified, so the caller has to gate on that job and pass
    # promote plus the base version the manifest is checked against.
    assert "channel == 'insider'" in release["if"]
    assert "channel == 'stable'" in release["if"]
    assert "needs.resolve-promotion.result == 'success'" in release["if"]
    assert "resolve-promotion" in release["needs"]
    assert "channel == 'stable'" in release["with"]["promote"]
    assert release["with"]["promotion_base_version"], "stable promotion needs a base version"
    # The stable installer comes from the verified handoff artifact, never from a
    # fresh build-windows upload.
    assert "Junction-notarized-stable-" in release["with"]["installer_artifact"]

    published = {nightly["with"]["channel"]} | {"insider", "stable"}
    assert client_channels == published, (
        f"the client knows channels {sorted(client_channels)} but the workflows "
        f"publish Windows on {sorted(published)}; a channel on only one side "
        "either offers a dead updater or hides a lane that exists"
    )


def test_the_artifact_probe_retries_a_blip_but_still_fails_closed() -> None:
    """Both halves matter, and they pull against each other.

    Failing closed is correct: an unknown is not an absence, and treating a failed
    listing as "nothing to publish" would silently skip a release. But this job
    hard-failing makes the whole insider run unsuccessful, and
    release_promotion.py then refuses to promote that commit at all -- so a single
    Actions-API blip during an insider run would cost stable promotion of the mac,
    Linux and CLI artifacts that same run already published.

    Retrying absorbs the blip without weakening the guarantee: a sustained failure
    still stops the lane. Dropping either half is a regression, so both are pinned
    here.
    """
    probe = _publish_step("Probe for the installer artifact")["run"]
    assert "for attempt in" in probe, "a transient listing failure must be retried"
    assert "sleep" in probe, "retries need to back off, not hammer the API"
    assert "::error::" in probe and "exit 1" in probe, (
        "a sustained listing failure must still fail closed rather than be "
        "laundered into nothing-to-publish"
    )
    # The absence branch must stay reachable: a build that genuinely produced no
    # installer is a clean skip, which is what keeps a Windows-only failure from
    # blocking the other platforms' lanes.
    assert "present=" in probe and "::notice::" in probe


def test_the_signature_is_verified_before_the_bytes_become_immutable() -> None:
    # The versioned key is written with --if-none-match, so an unsigned or
    # wrongly-signed installer that reaches S3 burns that version string. The
    # guard is only a guard if it runs first.
    names = [step.get("name", "") for step in _publish_job()["steps"]]
    verify = next(i for i, name in enumerate(names) if "Authenticode" in name)
    publish = next(i for i, name in enumerate(names) if "Publish installer" in name)
    attest = next(i for i, name in enumerate(names) if "Attest installer" in name)
    assert verify < attest < publish, (
        f"expected verify({verify}) < attest({attest}) < publish({publish}); an "
        "un-verified or un-attested installer must never reach an immutable key."
    )


def test_publishing_callers_consume_the_artifact_the_build_uploads() -> None:
    # A typo here is silent: publish-windows.yml probes for the artifact and
    # skips cleanly when it is absent, so a mismatched name reads as "the build
    # produced nothing" and Windows quietly stops publishing.
    upload_name = _step("Upload desktop artifact")["with"]["name"]
    for caller in PUBLISHING_CALLERS:
        jobs = _workflow(caller)["jobs"]
        publish_jobs = [
            job for job in jobs.values() if str(job.get("uses", "")).endswith("publish-windows.yml")
        ]
        assert publish_jobs, f"{caller} does not call publish-windows.yml"
        for job in publish_jobs:
            consumed = job["with"]["installer_artifact"]
            if "${{" not in consumed:
                assert consumed == upload_name, (
                    f"{caller} consumes {consumed!r} but "
                    f"build-windows.yml uploads {upload_name!r}"
                )
                continue
            # release.yml selects between the verified stable handoff and this
            # run's fresh build. Only the fresh-build branch is checkable
            # against build-windows.yml, and it is the branch a typo hides in --
            # the promotion branch is generated from the version and would fail
            # loudly at download time instead of skipping.
            assert (
                f"|| '{upload_name}'" in consumed
            ), f"{caller}'s fresh-build branch does not name {upload_name!r}: {consumed!r}"
            assert "Junction-notarized-stable-" in consumed, (
                f"{caller}'s promotion branch must consume the verified handoff "
                f"artifact, not a fresh build: {consumed!r}"
            )


def test_the_pairing_guard_runs_before_the_upload_and_fails_hard() -> None:
    """An orphaned installer must never be uploaded.

    The guard exists so an .exe with no .blockmap beside it fails the build
    BEFORE the artifact is produced: the publish lane then takes its
    documented build-produced-nothing skip path instead of hard-failing an
    insider run, which would block stable promotion of the mac, Linux and CLI
    artifacts (the coupling soft_fail exists to prevent). Nothing else fails
    at PR time if the step is deleted or reordered, so it is pinned here like
    the other load-bearing properties of this workflow.
    """
    guard = _step("installer/blockmap")
    run = guard["run"]
    assert "exit 1" in run, "the guard must fail the job, not merely annotate"
    assert "::error::" in run, "the failure must annotate the run"
    assert "GITHUB_STEP_SUMMARY" in run, (
        "soft_fail keeps the run green, so the reason must reach the run "
        "summary page rather than living only in the job log"
    )
    names = [s.get("name", "") for s in _build_job()["steps"]]
    guard_i = next(i for i, n in enumerate(names) if "installer/blockmap" in n)
    upload_i = names.index("Upload desktop artifact")
    build_i = names.index("Build desktop app")
    assert build_i < guard_i < upload_i, (
        f"expected build({build_i}) < guard({guard_i}) < upload({upload_i}): "
        "the guard must inspect the built dist and refuse the upload"
    )


def test_artifact_paths_contain_no_yaml_comments() -> None:
    """`path:` is a block scalar, where a '#' line is a glob, not a comment.

    Every line of a `|` block is literal text, so a comment written inside
    `path:` silently becomes a pattern that matches nothing. upload-artifact
    only errors when NO pattern matches, so the mistake stays invisible while
    quietly widening the set of things that must keep matching.
    """
    upload = _step("Upload desktop artifact")
    offenders = [
        line.strip() for line in upload["with"]["path"].splitlines() if line.strip().startswith("#")
    ]
    assert not offenders, (
        f"comment lines inside `path:` are treated as glob patterns: {offenders}. "
        "Move them above the step."
    )


def test_promotion_verifies_the_whole_bundle_before_reading_the_installer() -> None:
    # A stable publish republishes bytes recorded at insider time, so the
    # candidate's integrity is the thing to establish first. Verifying only the
    # installer would accept a bundle whose OTHER files were swapped, and this
    # lane is one of the readers that would then trust it.
    verify = _publish_step("Verify immutable promotion bundle")
    assert "inputs.promote" in verify["if"]
    assert "scripts/release_promotion.py verify" in verify["run"]
    assert '--expected-source-sha "${GITHUB_SHA}"' in verify["run"]
    assert '--expected-base-version "${PROMOTION_BASE_VERSION}"' in verify["run"]

    names = [step.get("name", "") for step in _publish_job()["steps"]]
    assert names.index("Verify immutable promotion bundle") < names.index(
        "Locate the installer and its blockmap"
    )


def test_a_promoted_candidate_without_an_installer_skips_but_a_fresh_build_fails() -> None:
    # These two halves pull against each other and neither may be dropped.
    #
    # SKIP: the Windows promotion role is optional, so a candidate recorded from
    # a run whose Windows build failed carries no installer. Failing there would
    # let one platform's build problem block the stable release of every other
    # platform -- exactly what optionality buys back.
    #
    # FAIL: in fresh-build mode the artifact was probed and found, so a missing
    # .exe inside it means the artifact's shape changed. Skipping there would
    # silently stop publishing Windows with a green run.
    run = _publish_step("Locate the installer and its blockmap")["run"]
    # The caller-fed promote flag reaches the script through env:, never
    # interpolated into it. `${{ }}` expanded inside a run: block is a shell
    # injection surface (Semgrep run-shell-injection), and this step is the one
    # place in the lane that has to branch on a caller input.
    locate = _publish_step("Locate the installer and its blockmap")
    assert locate["env"]["PROMOTE"] == "${{ inputs.promote }}"
    assert "${{" not in run, f"run: block interpolates a workflow expression: {run!r}"
    assert 'if [ "${#FOUND[@]}" -eq 0 ] && [ "${PROMOTE}" = "true" ]' in run
    assert "staged=" in run and "::notice::" in run
    assert 'if [ "${#FOUND[@]}" -ne 1 ]' in run
    assert "::error::expected exactly one .exe" in run
    # The blockmap requirement holds in BOTH modes: an installer published
    # without it degrades every client to a full download, silently.
    assert '[ ! -f "${SRC}.blockmap" ]' in run


def test_promotion_reverifies_provenance_instead_of_minting_a_second_attestation() -> None:
    # Attesting republished bytes would testify only that stable's own run held
    # the file, which is equally true of tampered bytes. The original attestation
    # from the insider publish is the one that means something.
    attest = _publish_step("Attest installer provenance")
    reverify = _publish_step("Verify promoted installer provenance")
    assert "!inputs.promote" in attest["if"], "a promoted republish must not re-attest"
    assert "inputs.promote" in reverify["if"] and "!inputs.promote" not in reverify["if"]
    assert "gh attestation verify" in reverify["run"]
    # Pinned to THIS workflow: any attestation signed by a different workflow is
    # not the one this lane produced when the bytes were first published.
    assert "--signer-workflow" in reverify["run"]
    assert "publish-windows.yml" in reverify["run"]


def test_every_publishing_step_is_gated_on_staged_bytes_not_on_the_probe() -> None:
    # The probe answers "did this run upload the artifact", which in promote mode
    # is always yes -- resolve-promotion uploaded the bundle. Only the locate step
    # knows whether an INSTALLER came out of it, so everything that touches the
    # bucket or the feed has to hang off that, or a candidate without a Windows
    # installer would publish a feed pointing at bytes that were never staged.
    publishing = (
        "Verify the Authenticode signature",
        "Attest installer provenance",
        "Verify promoted installer provenance",
        "Publish installer to distribution bucket",
        "Write update feed",
        "Update latest installer alias",
    )
    for name in publishing:
        condition = _publish_step(name)["if"]
        assert "steps.locate.outputs.staged" in condition, f"{name} is not gated on staged bytes"
        assert "steps.probe.outputs.present" not in condition, (
            f"{name} still gates on the probe, which cannot see whether the "
            "promoted bundle carried an installer"
        )
