#!/usr/bin/env python3
"""Build and verify the signed CLI artifact-manifest envelope.

The production workflow signs the canonical payload with an RSA key held as a
secret of the protected release environment. The ``sign`` command takes that
key from an environment variable and hands it to OpenSSL on stdin, refuses a
key whose public half is not the committed trust root, and refuses to assemble
an envelope unless OpenSSL verifies the signature it produced against that
committed key.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SCHEMA = "warding-cli-artifact-manifest-v1"
ALGORITHM = "RSASSA_PKCS1_V1_5_SHA_256"
CHANNELS = ("nightly", "insider", "stable")
SIGNED_FIELDS = {
    "algorithm",
    "channel",
    "key_id",
    "pub_date",
    "python_requires",
    "schema",
    "sha256",
    "version",
    "wheel_url",
}
_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+]{0,127}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_PUB_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_KEY_BITS_RE = re.compile(r"Public-Key:\s*\((\d+)\s+bit\)")
_MAX_PAYLOAD_BYTES = 16 * 1024
_MAX_SIGNATURE_BYTES = 1024


class ManifestError(ValueError):
    """A manifest or trust-root contract violation."""


def _run_openssl(args: list[str], *, stdin: bytes | None = None) -> bytes:
    try:
        proc = subprocess.run(
            ["openssl", *args],
            check=False,
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise ManifestError("openssl is required") from exc
    if proc.returncode != 0:
        raise ManifestError("openssl rejected the CLI manifest public key or signature")
    return proc.stdout


def _public_key_der(public_key: Path) -> bytes:
    if not public_key.is_file():
        raise ManifestError("CLI manifest public key is missing")
    raw = public_key.read_bytes()
    if b"UNCONFIGURED" in raw:
        raise ManifestError("CLI manifest public key is not configured")

    details = _run_openssl(["pkey", "-pubin", "-in", str(public_key), "-text", "-noout"])
    decoded = details.decode("utf-8", errors="replace")
    match = _KEY_BITS_RE.search(decoded)
    if match is None or "Modulus:" not in decoded:
        raise ManifestError("CLI manifest public key must be RSA")
    if int(match.group(1)) < 3072:
        raise ManifestError("CLI manifest RSA public key must be at least 3072 bits")
    return _run_openssl(["pkey", "-pubin", "-in", str(public_key), "-outform", "DER"])


def public_key_id(public_key: Path) -> str:
    return f"sha256:{hashlib.sha256(_public_key_der(public_key)).hexdigest()}"


def _canonical_json(value: dict[str, str]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("ascii")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > _MAX_PAYLOAD_BYTES:
        raise ManifestError("CLI manifest payload is too large")
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError("CLI manifest payload is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ManifestError("CLI manifest payload must be a JSON object")
    return value


def _require_text(payload: dict[str, Any], key: str, *, max_len: int = 2048) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise ManifestError(f"CLI manifest field {key!r} must be non-empty text")
    if any(ord(char) < 0x20 or ord(char) > 0x7E for char in value):
        raise ManifestError(f"CLI manifest field {key!r} must contain printable ASCII only")
    return value


def _validate_signed_payload(payload: dict[str, Any]) -> dict[str, str]:
    if set(payload) != SIGNED_FIELDS:
        raise ManifestError("CLI manifest signed field set does not match schema v1")

    normalized = {key: _require_text(payload, key) for key in SIGNED_FIELDS}
    if normalized["schema"] != SCHEMA:
        raise ManifestError("unsupported CLI manifest schema")
    if normalized["algorithm"] != ALGORITHM:
        raise ManifestError("unsupported CLI manifest signature algorithm")
    if normalized["channel"] not in CHANNELS:
        raise ManifestError("unsupported CLI manifest channel")
    if _VERSION_RE.fullmatch(normalized["version"]) is None:
        raise ManifestError("invalid CLI manifest version")
    if _SHA256_RE.fullmatch(normalized["sha256"]) is None:
        raise ManifestError("invalid CLI manifest SHA-256")
    if _PUB_DATE_RE.fullmatch(normalized["pub_date"]) is None:
        raise ManifestError("invalid CLI manifest publication date")
    if not normalized["key_id"].startswith("sha256:") or not _SHA256_RE.fullmatch(
        normalized["key_id"][len("sha256:") :]
    ):
        raise ManifestError("invalid CLI manifest key id")
    _require_text(payload, "python_requires", max_len=128)

    wheel_name = f"warding-{normalized['version']}-py3-none-any.whl"
    parsed = urlsplit(normalized["wheel_url"])
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.endswith(
            f"/cli/{normalized['channel']}/{normalized['version']}/{wheel_name}"
        )
    ):
        raise ManifestError("CLI manifest wheel URL is not a canonical HTTPS artifact URL")
    return normalized


def _validate_target_binding(
    payload: dict[str, str], *, expected_channel: str, artifact_base: str
) -> None:
    if payload["channel"] != expected_channel:
        raise ManifestError("CLI manifest channel does not match the expected channel")

    normalized_base = artifact_base.rstrip("/")
    parsed_base = urlsplit(normalized_base)
    if (
        parsed_base.scheme != "https"
        or not parsed_base.hostname
        or parsed_base.username is not None
        or parsed_base.password is not None
        or parsed_base.query
        or parsed_base.fragment
    ):
        raise ManifestError("artifact base must be a canonical HTTPS URL")

    version = payload["version"]
    wheel_name = f"warding-{version}-py3-none-any.whl"
    expected_url = (
        f"{normalized_base}/cli/{expected_channel}/{version}/{wheel_name}"
    )
    if payload["wheel_url"] != expected_url:
        raise ManifestError("CLI manifest wheel URL does not match the artifact base")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _payload_command(args: argparse.Namespace) -> None:
    key_id = public_key_id(args.public_key)
    payload = {
        "algorithm": ALGORITHM,
        "channel": args.channel,
        "key_id": key_id,
        "pub_date": args.pub_date,
        "python_requires": args.python_requires,
        "schema": SCHEMA,
        "sha256": args.sha256,
        "version": args.version,
        "wheel_url": args.wheel_url,
    }
    normalized = _validate_signed_payload(payload)
    _atomic_write(args.output, _canonical_json(normalized))


def _assemble_command(args: argparse.Namespace) -> None:
    payload_any = _load_json(args.payload)
    payload = _validate_signed_payload(payload_any)
    canonical = _canonical_json(payload)
    if args.payload.read_bytes() != canonical:
        raise ManifestError("CLI manifest payload is not canonical JSON")
    expected_key_id = public_key_id(args.public_key)
    if payload["key_id"] != expected_key_id:
        raise ManifestError("CLI manifest payload does not name the committed public key")

    signature = args.signature.read_bytes()
    if not signature or len(signature) > _MAX_SIGNATURE_BYTES:
        raise ManifestError("CLI manifest signature has an invalid size")
    _run_openssl(
        [
            "dgst",
            "-sha256",
            "-verify",
            str(args.public_key),
            "-signature",
            str(args.signature),
            str(args.payload),
        ]
    )

    manifest = dict(payload)
    manifest["signature"] = base64.b64encode(signature).decode("ascii")
    rendered = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("ascii")
    _atomic_write(args.output, rendered)


def _verify_command(args: argparse.Namespace) -> None:
    """Verify a SIGNED manifest (e.g. a live channel feed) end to end.

    Mirrors what cli.sh enforces at install time: schema validation, the
    pinned-key fingerprint, the embedded signature over the canonical payload,
    and binding to the requested channel and artifact base. Used by
    publish-installer.yml to prove every live feed is installable by the strict
    installer BEFORE it replaces the live cli.sh.
    """
    manifest_any = _load_json(args.manifest)
    if not isinstance(manifest_any, dict):
        raise ManifestError("CLI manifest must be a JSON object")
    manifest = dict(manifest_any)
    signature_b64 = manifest.pop("signature", None)
    if not isinstance(signature_b64, str) or not signature_b64:
        raise ManifestError("CLI manifest is missing its signature")
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except ValueError as exc:
        raise ManifestError("CLI manifest signature is not valid base64") from exc
    if not signature or len(signature) > _MAX_SIGNATURE_BYTES:
        raise ManifestError("CLI manifest signature has an invalid size")

    payload = _validate_signed_payload(manifest)
    expected_key_id = public_key_id(args.public_key)
    if payload["key_id"] != expected_key_id:
        raise ManifestError("CLI manifest does not name the pinned public key")

    with tempfile.TemporaryDirectory() as scratch:
        payload_path = Path(scratch) / "payload.json"
        signature_path = Path(scratch) / "signature.bin"
        payload_path.write_bytes(_canonical_json(payload))
        signature_path.write_bytes(signature)
        _run_openssl(
            [
                "dgst",
                "-sha256",
                "-verify",
                str(args.public_key),
                "-signature",
                str(signature_path),
                str(payload_path),
            ]
        )
    _validate_target_binding(
        payload,
        expected_channel=args.expected_channel,
        artifact_base=args.artifact_base,
    )
    print(f"verified: {args.manifest} signed by {expected_key_id}")


def _sign_command(args: argparse.Namespace) -> None:
    payload_any = _load_json(args.payload)
    payload = _validate_signed_payload(payload_any)
    canonical = _canonical_json(payload)
    if args.payload.read_bytes() != canonical:
        raise ManifestError("CLI manifest payload is not canonical JSON")

    pinned_der = _public_key_der(args.public_key)
    expected_key_id = f"sha256:{hashlib.sha256(pinned_der).hexdigest()}"
    if payload["key_id"] != expected_key_id:
        raise ManifestError("CLI manifest payload does not name the committed public key")

    # The key reaches OpenSSL only through stdin, so it is never written to disk
    # and never appears in an argument list.
    signing_key = os.environ.get(args.private_key_env, "").encode("utf-8")
    if not signing_key.strip():
        raise ManifestError(f"CLI manifest signing key is not set in {args.private_key_env}")

    # A key whose public half is not the committed trust root would sign
    # manifests every installed cli.sh rejects, so refuse it before signing.
    signer_der = _run_openssl(["pkey", "-pubout", "-outform", "DER"], stdin=signing_key)
    if not hmac.compare_digest(signer_der, pinned_der):
        raise ManifestError("CLI manifest signing key does not match the committed public key")

    with tempfile.TemporaryDirectory(prefix="warding-cli-manifest-") as temporary:
        signature_path = Path(temporary) / "signature.bin"
        # PKCS#1 v1.5 is named explicitly: it is the schema's algorithm, and an
        # RSA-PSS key then fails here instead of signing in a scheme cli.sh
        # would read differently.
        _run_openssl(
            [
                "dgst",
                "-sha256",
                "-sign",
                "/dev/stdin",
                "-sigopt",
                "rsa_padding_mode:pkcs1",
                "-out",
                str(signature_path),
                str(args.payload),
            ],
            stdin=signing_key,
        )
        _assemble_command(
            argparse.Namespace(
                payload=args.payload,
                signature=signature_path,
                public_key=args.public_key,
                output=args.output,
            )
        )


def _key_info_command(args: argparse.Namespace) -> None:
    raw = args.public_key.read_bytes()
    info = {
        "key_id": public_key_id(args.public_key),
        "public_key_pem_base64": base64.b64encode(raw).decode("ascii"),
    }
    print(json.dumps(info, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    payload = subparsers.add_parser("payload", help="write the canonical payload to sign")
    payload.add_argument("--channel", choices=CHANNELS, required=True)
    payload.add_argument("--version", required=True)
    payload.add_argument("--wheel-url", required=True)
    payload.add_argument("--sha256", required=True)
    payload.add_argument("--python-requires", required=True)
    payload.add_argument("--pub-date", required=True)
    payload.add_argument("--public-key", type=Path, required=True)
    payload.add_argument("--output", type=Path, required=True)
    payload.set_defaults(handler=_payload_command)

    assemble = subparsers.add_parser(
        "assemble", help="verify a detached signature and write the signed manifest"
    )
    assemble.add_argument("--payload", type=Path, required=True)
    assemble.add_argument("--signature", type=Path, required=True)
    assemble.add_argument("--public-key", type=Path, required=True)
    assemble.add_argument("--output", type=Path, required=True)
    assemble.set_defaults(handler=_assemble_command)

    sign = subparsers.add_parser(
        "sign", help="sign the canonical payload with the release key and verify the result"
    )
    sign.add_argument("--payload", type=Path, required=True)
    sign.add_argument(
        "--private-key-env",
        required=True,
        help="name of the environment variable holding the PEM private key",
    )
    sign.add_argument("--public-key", type=Path, required=True)
    sign.add_argument("--output", type=Path, required=True)
    sign.set_defaults(handler=_sign_command)

    verify = subparsers.add_parser(
        "verify", help="verify a signed manifest against the pinned public key"
    )
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--public-key", type=Path, required=True)
    verify.add_argument("--expected-channel", choices=CHANNELS, required=True)
    verify.add_argument("--artifact-base", required=True)
    verify.set_defaults(handler=_verify_command)

    key_info = subparsers.add_parser(
        "key-info", help="print the public values that must be pinned in cli.sh"
    )
    key_info.add_argument("--public-key", type=Path, required=True)
    key_info.set_defaults(handler=_key_info_command)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        args.handler(args)
    except (ManifestError, OSError) as exc:
        print(f"cli-manifest: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
