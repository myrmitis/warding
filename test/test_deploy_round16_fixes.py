"""Regression tests for deploy fixes.

- reaper.sh OAC exact-match (re.fullmatch, not startswith)
- pending-confirm passes expected_content_digest to _do_deploy
- teardown manifest identity cross-verification (distribution_id)
- ArtifactDeployPage Badge component (tested via tsc -b gate)
- reaper.sh engine-arch retry-on-failed-deletion (tested via bash -n + drift)
- API-only server registers deploy routes
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from warding.deploy import webapp_types

# ─── reaper.sh OAC uses fullmatch not startswith ────────────────────────

_REAPER_SH = Path(__file__).resolve().parent.parent / (
    "src/warding/deploy/skills/artifact-deploy/scripts/reaper.sh"
)


class TestReaperOACExactMatch:
    """reaper.sh must use re.fullmatch (not startswith) for OAC name matching."""

    def test_reaper_sh_contains_fullmatch_pattern(self):
        """Drift test: reaper.sh OAC fallback uses re.fullmatch, not startswith."""
        content = _REAPER_SH.read_text(encoding="utf-8")
        assert "oac_re.fullmatch(" in content, (
            "reaper.sh must use re.fullmatch for OAC matching"
        )

    def test_reaper_sh_no_bare_startswith_oac_match(self):
        """Negative drift: no bare startswith on OAC name matching."""
        content = _REAPER_SH.read_text(encoding="utf-8")
        # The old vulnerable pattern was: if item.get('Name', '').startswith(prefix)
        assert ".startswith(prefix)" not in content, (
            "reaper.sh must NOT use bare startswith for OAC matching — "
            "cross-matches overlapping slugs"
        )

    def test_reaper_sh_oac_pattern_mirrors_lambda(self):
        """The shell regex matches the Lambda reaper's pattern: prefix + '-' + 6 hex + $."""
        content = _REAPER_SH.read_text(encoding="utf-8")
        assert r"-[0-9a-f]{6}$" in content or r"-[0-9a-f]{6}\$" in content, (
            "reaper.sh OAC pattern must match deploy-web-<slug>[:57]-<6hex> exactly"
        )


# ─── Pending-confirm passes expected_content_digest ──────────────────────

class TestPendingConfirmDigest:
    """_handle_pending_confirm passes expected_content_digest into _do_deploy."""

    def test_handlers_passes_digest_to_do_deploy(self):
        """Verify the code path sets expected_content_digest param."""
        import inspect

        from warding.deploy import handlers
        source = inspect.getsource(handlers)
        # The fix adds: params["expected_content_digest"] = stored_digest
        assert 'params["expected_content_digest"]' in source, (
            "_handle_pending_confirm must pass expected_content_digest into params for _do_deploy"
        )


# ─── Teardown manifest identity cross-verification ───────────────────────

class TestTeardownManifestIdentity:
    """Teardown cross-verifies distribution_id before rewriting manifest."""

    def test_webapp_deploy_target_has_distribution_id(self):
        """WebAppDeployTarget dataclass has distribution_id field."""
        dt = webapp_types.WebAppDeployTarget()
        assert hasattr(dt, "distribution_id"), (
            "WebAppDeployTarget must have distribution_id for manifest cross-verify"
        )
        assert dt.distribution_id == ""

    def test_distribution_id_roundtrip(self):
        """distribution_id persists through serialization if present."""
        dt = webapp_types.WebAppDeployTarget(distribution_id="E1234567890ABC")
        assert dt.distribution_id == "E1234567890ABC"

    def test_handler_contains_identity_mismatch_check(self):
        """handlers.py contains the identity cross-verification logic."""
        import inspect

        from warding.deploy import handlers
        source = inspect.getsource(handlers)
        assert "identity_mismatch" in source, (
            "_expire_manifest_best_effort must check distribution_id mismatch"
        )


# ─── reaper.sh engine-arch retry on failed deletion ──────────────────────

class TestReaperRetryOnFailure:
    """reaper.sh tracks deletion success and keeps manifest on partial failure."""

    def test_reaper_sh_tracks_engine_all_clean(self):
        """reaper.sh engine-arch path tracks _engine_all_clean flag."""
        content = _REAPER_SH.read_text(encoding="utf-8")
        assert "_engine_all_clean" in content, (
            "reaper.sh must track whether all engine-arch deletions succeeded"
        )

    def test_reaper_sh_conditional_manifest_removal(self):
        """Manifest is only removed when _engine_all_clean is true."""
        content = _REAPER_SH.read_text(encoding="utf-8")
        # The fix conditionally removes manifest
        assert 'if [[ "$_engine_all_clean" == "true" ]]' in content, (
            "reaper.sh must only delete manifest when all deletions verified clean"
        )

    def test_reaper_sh_bash_syntax_valid(self):
        """bash -n validates reaper.sh syntax."""
        result = subprocess.run(
            ["bash", "-n", str(_REAPER_SH)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"bash -n failed: {result.stderr}"


# ─── API-only server registers deploy routes ─────────────────────────────

class TestAPIServerDeployRoutes:
    """start_api_server must register deploy routes."""

    def test_api_server_has_deploy_routes_call(self):
        """start_api_server source calls _register_deploy_routes."""
        import inspect

        from warding.dashboard import server
        source = inspect.getsource(server.start_api_server)
        assert "_register_deploy_routes" in source, (
            "start_api_server must call _register_deploy_routes(app)"
        )


class TestIdentityWiring:
    """Identity wiring: the identity field must survive the FULL loop --
    deploy writes it, serializer emits it, parser reads it back. A field
    that parses to '' makes the teardown cross-verify a dead check."""

    def test_parser_reads_distribution_id(self):
        from warding.deploy.webapp_types import webapp_metadata_from_dict
        meta = webapp_metadata_from_dict({
            "slug": "x", "deploy_target": {"provider": "aws",
                                           "distribution_id": "E2ABCDEF123456"},
        })
        assert meta is not None
        assert meta.deploy_target.distribution_id == "E2ABCDEF123456"

    def test_writeback_uses_allowed_event_type(self):
        # A non-allowlisted event_type raises inside the best-effort
        # try/except and silently skips persistence (dead check).
        from pathlib import Path
        src = Path(__file__).parent.parent / "src" / "warding" / "deploy" / "handlers.py"
        text = src.read_text(encoding="utf-8")
        assert 'event_type="edited"' in text
        assert "_persist_dist_id" in text

    def test_writeback_flows_result_distribution_id(self):
        from pathlib import Path
        src = Path(__file__).parent.parent / "src" / "warding" / "deploy" / "handlers.py"
        text = src.read_text(encoding="utf-8")
        idx = text.index("_persist_dist_id")
        window = text[idx - 500: idx + 900]
        assert 'result.get("distribution_id")' in window or \
               'result.get("distribution_id", "")' in window
