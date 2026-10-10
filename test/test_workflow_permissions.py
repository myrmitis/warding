"""Regression tests for least-privilege GitHub workflow permissions."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
# The R2 API token's two halves: the only secrets a bucket-writing lane needs.
R2_SECRETS = {"R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"}


def _lines(name: str) -> list[str]:
    return (WORKFLOWS / name).read_text(encoding="utf-8").splitlines()


def _permission_block(lines: list[str], marker: str) -> dict[str, str] | None:
    """Return the permissions nested directly under an exact YAML marker."""
    start = lines.index(marker)
    marker_indent = len(marker) - len(marker.lstrip())

    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= marker_indent:
            break
        if line.strip() != "permissions:" or indent != marker_indent + 2:
            continue

        permissions: dict[str, str] = {}
        for permission_line in lines[index + 1 :]:
            if not permission_line.strip():
                continue
            permission_indent = len(permission_line) - len(permission_line.lstrip())
            if permission_indent <= indent:
                break
            # Comments are annotation, not grants. Skipping them keeps a
            # documented permissions block readable as a dict; without this the
            # split below raises ValueError and an ordinary assertion failure
            # arrives as an unpackaging crash that names no workflow.
            if permission_line.strip().startswith("#"):
                continue
            key, value = permission_line.strip().split(":", 1)
            permissions[key] = value.strip()
        return permissions

    return None


def _workflow_permissions(name: str) -> dict[str, str]:
    lines = _lines(name)
    start = lines.index("permissions:")
    permissions: dict[str, str] = {}
    for line in lines[start + 1 :]:
        if not line.strip():
            continue
        if not line.startswith("  "):
            break
        # See _permission_block: comments must not be parsed as grants.
        if line.strip().startswith("#"):
            continue
        key, value = line.strip().split(":", 1)
        permissions[key] = value.strip()
    return permissions


#: Job headers for every Linux publish caller. Six lanes = three formats
#: (appimage / deb / rpm) x two arches, each its own job because
#: publish-linux.yml writes one immutable versioned key per invocation.
_PUBLISH_LINUX_JOB_HEADERS = tuple(
    f"  publish-linux-{fmt}-{arch}:"
    for fmt in ("appimage", "deb", "rpm")
    for arch in ("x64", "arm64")
)


class TestNightlyPermissions:
    def test_only_publish_callers_can_mint_oidc_tokens(self) -> None:
        lines = _lines("nightly.yml")

        assert _workflow_permissions("nightly.yml") == {"contents": "read"}
        assert _permission_block(lines, "  version:") is None
        # Build callers inherit the workflow-level contents:read only; the
        # reusable build workflows request nothing more.
        assert _permission_block(lines, "  build-wheel:") is None
        assert _permission_block(lines, "  build-desktop:") is None
        # The Windows build signs during the build with a certificate it reads
        # from secrets, so it mints no OIDC token. The caller grants exactly
        # contents:read: a callee can never exceed its caller, so this is the
        # ceiling that keeps the job holding a signing identity from also
        # minting a provenance identity or writing to the repository.
        assert _permission_block(lines, "  build-windows:") == {
            "contents": "read",
        }
        assert _permission_block(lines, "  publish-cli:") == {
            "contents": "read",
            "id-token": "write",
            "attestations": "write",
        }
        # The Linux desktop lanes publish bucket objects and attest (OIDC)
        # their own SLSA provenance for the exact bytes they upload -- never
        # contents:write. One lane per arch, so BOTH are asserted: a new arch
        # that quietly widened its grant would otherwise slip through.
        for arch_job in _PUBLISH_LINUX_JOB_HEADERS:
            assert _permission_block(lines, arch_job) == {
                "contents": "read",
                "id-token": "write",
                "attestations": "write",
            }
        # The Windows lane publishes bucket objects and attests (OIDC) the
        # exact installer bytes it uploads. It does NOT hold a signing identity --
        # signing already happened in build-windows -- so the grant is the same
        # publish-shaped one the Linux lanes carry, and never contents:write.
        assert _permission_block(lines, "  publish-windows-x64:") == {
            "contents": "read",
            # actions:read is load-bearing, not hygiene: the lane's artifact
            # probe queries the Actions API, a called workflow cannot exceed its
            # caller's grants, and the probe fails closed -- so omitting it here
            # aborts the lane rather than merely narrowing it.
            "actions": "read",
            "id-token": "write",
            "attestations": "write",
        }
        # The Docker lane pushes to ghcr.io with the workflow's own
        # GITHUB_TOKEN: packages:write is required for the push and MUST
        # stay scoped to this caller job (never workflow-level -- a
        # registry-poisoning capability in every job would defeat the
        # least-privilege split). id-token + attestations cover the in-lane
        # SLSA provenance push; never contents:write.
        assert _permission_block(lines, "  publish-docker:") == {
            "contents": "read",
            "packages": "write",
            "id-token": "write",
            "attestations": "write",
        }
        # Caller job for the reusable sign-and-notarize workflow: a
        # workflow_call callee can never exceed the caller job's permissions,
        # so the caller must grant id-token explicitly. attestations:write
        # covers the sign job's wheel/sdist/AppImage provenance and the
        # notarize job's shipping-DMG attestation.
        assert _permission_block(lines, "  sign-and-notarize:") == {
            "id-token": "write",
            "contents": "read",
            "attestations": "write",
        }


class TestReleasePermissions:
    def test_release_jobs_follow_least_privilege_split(self) -> None:
        """The signing and publishing callers hold the bucket credential but
        must not hold contents:write; the GitHub-Release job holds
        contents:write but must not hold the bucket credential. Keeping the
        two capabilities in separate jobs means a compromise of either job
        cannot both rewrite published objects and tamper with the
        repo/release. The Windows build holds a signing certificate and
        neither capability."""
        lines = _lines("release.yml")

        assert _workflow_permissions("release.yml") == {"contents": "read"}
        assert _permission_block(lines, "  version:") is None
        assert _permission_block(lines, "  resolve-promotion:") == {
            "actions": "read",
            "contents": "read",
        }
        assert _permission_block(lines, "  record-promotion:") == {
            "contents": "read",
        }
        assert _permission_block(lines, "  build-wheel:") is None
        assert _permission_block(lines, "  build-desktop:") is None
        # Windows build: certificate from secrets, so contents:read and no
        # OIDC (see nightly).
        assert _permission_block(lines, "  build-windows:") == {
            "contents": "read",
        }
        assert _permission_block(lines, "  publish-cli:") == {
            "contents": "read",
            "id-token": "write",
            "attestations": "write",
        }
        # Linux desktop lanes: bucket upload + in-lane provenance (see nightly
        # note).
        for arch_job in _PUBLISH_LINUX_JOB_HEADERS:
            assert _permission_block(lines, arch_job) == {
                "contents": "read",
                "id-token": "write",
                "attestations": "write",
            }
        # Windows publish lane: same publish-shaped grant as Linux (see nightly).
        assert _permission_block(lines, "  publish-windows-x64:") == {
            "contents": "read",
            # actions:read is load-bearing, not hygiene: the lane's artifact
            # probe queries the Actions API, a called workflow cannot exceed its
            # caller's grants, and the probe fails closed -- so omitting it here
            # aborts the lane rather than merely narrowing it.
            "actions": "read",
            "id-token": "write",
            "attestations": "write",
        }
        # Docker lane: ghcr.io push via GITHUB_TOKEN (packages:write scoped
        # to this job only) + in-lane provenance (see nightly note).
        assert _permission_block(lines, "  publish-docker:") == {
            "contents": "read",
            "packages": "write",
            "id-token": "write",
            "attestations": "write",
        }
        assert _permission_block(lines, "  sign-and-notarize:") == {
            "id-token": "write",
            "contents": "read",
            "attestations": "write",
        }
        assert _permission_block(lines, "  github-release:") == {
            "contents": "write",
        }


class TestReusableWorkflowPermissions:
    def test_build_workflows_are_read_only(self) -> None:
        """The shared build workflows compile source into artifacts; they
        must never hold OIDC or write capabilities.

        build-windows.yml is deliberately NOT in this list: it Authenticode-signs
        during the build (the NSIS installer compresses its own already-signed
        executable, so signing cannot be a downstream job) and therefore holds
        the signing certificate. Keeping it a separate workflow is what lets
        these two stay credential-free -- putting the Windows leg back into
        build-desktop.yml would put the certificate within reach of the mac and
        Linux legs as well. See
        test_build_windows_isolates_the_signing_capability.
        """
        assert _workflow_permissions("build-wheel.yml") == {"contents": "read"}
        assert _workflow_permissions("build-desktop.yml") == {"contents": "read"}

    def test_build_desktop_has_no_windows_leg(self) -> None:
        """The credential-free build workflow must not build Windows.

        This is the structural half of the least-privilege split: if a Windows
        leg reappears here it would need the signing certificate in this
        workflow, which the credential-free guarantee above exists to prevent.
        Pinning the matrix keeps that pressure visible in review instead of
        arriving as a one-line secrets edit.
        """
        # Assert on the resolved matrix, not on the text: the word "windows"
        # legitimately appears in prose, and a substring check would either
        # fire on a comment or be silently defeated by one.
        workflow = yaml.safe_load(
            (WORKFLOWS / "build-desktop.yml").read_text(encoding="utf-8")
        )
        runners = {
            entry["os"]
            for entry in workflow["jobs"]["build-desktop"]["strategy"]["matrix"]["include"]
        }
        assert not any("windows" in runner for runner in runners), (
            f"build-desktop.yml grew a Windows leg (matrix: {sorted(runners)}). "
            "Windows signs during its build with a production certificate; it "
            "belongs in build-windows.yml so this workflow can stay credential-free."
        )

    def test_build_windows_isolates_the_signing_capability(self) -> None:
        """The Windows build needs contents:read and nothing more.

        It signs with a certificate read from secrets, so it mints no OIDC
        token. contents:write in particular must never appear: this job holds a
        production signing identity, which is precisely why it is not allowed to
        also mutate the repository or mint a provenance identity.
        """
        assert _workflow_permissions("build-windows.yml") == {"contents": "read"}
        lines = _lines("build-windows.yml")
        assert _permission_block(lines, "  build-windows:") == {
            "contents": "read",
        }

    def test_sign_and_notarize_declares_exact_capabilities(self) -> None:
        """The shared sign/notarize workflow needs id-token and attestations
        (provenance for the artifacts + shipping DMG) -- and nothing else.
        It reaches its buckets with the R2 key from secrets, not a cloud
        role. contents:write in particular must never appear here
        (least-privilege split: the GitHub-Release job in release.yml is the
        only writer)."""
        assert _workflow_permissions("sign-and-notarize.yml") == {
            "contents": "read",
            "id-token": "write",
            "attestations": "write",
        }

    def test_publish_cli_declares_exact_capabilities(self) -> None:
        assert _workflow_permissions("publish-cli.yml") == {
            "contents": "read",
            "id-token": "write",
            "attestations": "write",
        }

    def test_publish_windows_declares_exact_capabilities(self) -> None:
        """The Windows publish lane uploads to the distribution bucket and
        attests (OIDC) the installer it uploads -- and nothing else.

        It holds no signing identity: build-windows.yml already signed the
        installer, and keeping the two apart means a compromise of the publish
        lane cannot mint a signature. contents:write must never appear."""
        assert _workflow_permissions("publish-windows.yml") == {
            "contents": "read",
            "actions": "read",
            "id-token": "write",
            "attestations": "write",
        }

    def test_the_windows_publish_callers_pass_only_the_r2_credential(self) -> None:
        """`secrets: inherit` hands a reusable workflow EVERY repository secret.

        The Windows lane writes the public installer, feed and `latest/` alias,
        so its blast radius is worth bounding to the one credential it uses: the
        R2 access key and its secret half. The reusable workflow declares those
        explicitly and both callers pass only them; this pins the arrangement so
        a later edit cannot quietly widen it back to the full set."""
        windows = yaml.safe_load(
            (WORKFLOWS / "publish-windows.yml").read_text(encoding="utf-8")
        )
        # PyYAML resolves the bare key `on` to the boolean True (YAML 1.1), so
        # the trigger block is not reachable under the string "on".
        triggers = windows[True] if True in windows else windows["on"]
        declared = triggers["workflow_call"]["secrets"]
        assert set(declared) == R2_SECRETS
        # Not required: an empty value is how a fork without the secrets skips
        # the lane cleanly instead of failing the workflow call.
        assert all(declared[name]["required"] is False for name in R2_SECRETS)

        for name in ("nightly.yml", "release.yml"):
            workflow = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
            job = next(
                j
                for j in workflow["jobs"].values()
                if str(j.get("uses", "")).endswith("publish-windows.yml")
            )
            secrets = job.get("secrets")
            assert secrets != "inherit", (
                f"{name} inherits every repository secret into the Windows publish lane"
            )
            assert set(secrets) == R2_SECRETS, (
                f"{name} passes {sorted(secrets)} to the Windows publish lane, "
                f"which consumes {sorted(R2_SECRETS)} alone"
            )

    def test_publish_docker_declares_exact_capabilities(self) -> None:
        """The Docker lane pushes to ghcr.io (packages:write via
        GITHUB_TOKEN) and attests in-lane SLSA provenance (id-token +
        attestations, pushed to the registry). contents stays read-only;
        no bucket credential reaches this lane at all."""
        assert _workflow_permissions("publish-docker.yml") == {
            "contents": "read",
            "packages": "write",
            "id-token": "write",
            "attestations": "write",
        }


class TestPrReadinessPermissions:
    def test_readiness_has_only_aggregation_and_label_permissions(self) -> None:
        assert _workflow_permissions("pr-readiness.yml") == {
            "actions": "read",
            "checks": "read",
            "contents": "read",
            "issues": "write",
            "pull-requests": "write",
            "statuses": "write",
        }
