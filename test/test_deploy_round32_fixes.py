"""Regression tests for deploy fixes.

- shell reaper must verify the distribution's warding:site tag before
  disable/delete (manifest distribution_id is attacker-writable).
- DEPLOY policy must grant cloudfront:DeleteOriginAccessControl — the
  user-invoked destroy() path calls it; without the grant every destroy
  silently leaked an OAC.
- fullstack policy must grant iam:GetPolicy on the boundary ARN — the
  boundary preflight calls it and misreports AccessDenied as "boundary absent".
"""
from pathlib import Path

from warding.deploy import iam as iam_mod

REPO = Path(__file__).resolve().parents[1]
REAPER_SH = (
    REPO / "src" / "warding" / "deploy" / "skills" / "artifact-deploy"
    / "scripts" / "reaper.sh"
)


def _statements(doc):
    return {st.get("Sid", ""): st for st in doc["Statement"]}


class TestReaperShellDistTagGate:
    def test_tag_verification_precedes_destructive_ops(self):
        src = REAPER_SH.read_text(encoding="utf-8")
        tag_idx = src.index("list-tags-for-resource")
        assert tag_idx < src.index("update-distribution"), (
            "distribution tag gate must run before Phase-1 disable"
        )
        assert tag_idx < src.index("delete-distribution"), (
            "distribution tag gate must run before Phase-2 delete"
        )

    def test_gate_fails_closed(self):
        src = REAPER_SH.read_text(encoding="utf-8")
        block = src.split("list-tags-for-resource", 1)[1][:900]
        assert "TAG_LOOKUP_FAILED" in src, "lookup failure must not pass the gate"
        assert "continue" in block, "mismatch must skip (fail closed), not proceed"
        assert 'warding:site' in src.split("Twin of the Lambda tag check", 1)[1][:1200]


class TestDeployPolicyOacDelete:
    def test_deploy_policy_does_not_grant_oac_delete(self):
        # OAC cannot be tag-scoped, so an
        # account-wide Delete on the DEPLOY profile lets a compromised deploy
        # session delete every OAC in the account. Cleanup is owned by the
        # reaper role; destroy() reports "deferred-to-reaper" instead.
        doc = iam_mod.policy_document(tier="static")
        st = _statements(doc)["CloudFrontOACManage"]
        assert "cloudfront:DeleteOriginAccessControl" not in st["Action"]
        assert "cloudfront:CreateOriginAccessControl" in st["Action"]


class TestBoundaryPreflightRead:
    def test_fullstack_policy_grants_get_policy_on_boundary(self):
        doc = iam_mod.policy_document(tier="fullstack")
        st = _statements(doc).get("BoundaryPreflightRead")
        assert st is not None, "fullstack policy must include BoundaryPreflightRead"
        assert st["Action"] == ["iam:GetPolicy"]
        assert iam_mod.BOUNDARY_POLICY_NAME in st["Resource"]
        assert st["Resource"].startswith("arn:aws:iam::")
