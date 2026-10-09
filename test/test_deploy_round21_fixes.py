"""Regression tests for deploy fixes.

- the app-arch (CloudFormation stack) reap path verifies the stack's
  warding:site identity tag before deletion, matching the engine-arch
  gate; deploy-backend.sh tags stacks at creation.
- webapp_metadata.public_url validation rejects Basic-auth userinfo
  (https://user:pass@host) at the backend; safeHttpUrl mirrors it in the FE.
"""
from pathlib import Path

import pytest

_SKILL = Path(__file__).resolve().parents[1] / (
    "src/warding/deploy/skills/artifact-deploy"
)


# --- Stack identity gate ---


def test_f1_deploy_backend_tags_stack_at_creation():
    src = (_SKILL / "scripts/deploy-backend.sh").read_text(encoding="utf-8")
    assert '--tags "warding:site=$SLUG"' in src


def test_f1_lambda_gates_every_delete_stack():
    src = (_SKILL / "scripts/reaper_lambda/index.py").read_text(encoding="utf-8")
    assert "_stack_site_tag_ok" in src
    # The Phase A main path reads stack tags from describe_stacks and refuses
    # on mismatch before delete_stack.
    assert "app_reap_stack_tag_mismatch" in src
    # _del_stack (dry-run/manual path) is gated.
    fn = src.split("def _del_stack", 1)[1].split("\ndef ", 1)[0]
    assert "_stack_site_tag_ok" in fn
    # Phase B DELETE_FAILED retry is gated.
    phase_b = src.split('elif status == "DELETE_FAILED"', 1)[1][:600]
    assert "_stack_site_tag_ok" in phase_b


def test_f1_shell_reaper_gates_stack_deletion():
    src = (_SKILL / "scripts/reaper.sh").read_text(encoding="utf-8")
    # Both Phase A and the Phase B DELETE_FAILED retry check the tag.
    assert src.count("warding:site") >= 2
    assert "tag mismatch" in src


# --- Userinfo rejection ---


def _validate(url: str):
    from warding.validation import _validate_webapp_metadata_shape
    _validate_webapp_metadata_shape({"deploy_target": {"public_url": url}})


def test_f2_backend_rejects_userinfo_url():
    from warding.validation import ValidationError
    with pytest.raises(ValidationError):
        _validate("https://user:secret@attacker.example/path")
    with pytest.raises(ValidationError):
        _validate("https://user@attacker.example/")


def test_f2_backend_accepts_plain_https():
    _validate("https://d123.cloudfront.net/site/")
    _validate("")  # draft state


def test_f2_frontend_safe_http_url_rejects_userinfo():
    src = (
        Path(__file__).resolve().parents[1] / "website/src/lib/safeUrl.ts"
    ).read_text(encoding="utf-8")
    assert "u.username || u.password" in src
