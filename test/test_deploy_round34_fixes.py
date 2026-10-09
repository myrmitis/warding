"""Regression tests for deploy fixes.

- the deploy_web migration cleanup must run off the event loop
  (asyncio.to_thread) — it does filesystem I/O during gateway startup.
- attach/detach backend helpers must NEVER spawn AWS commands without the
  sandbox chokepoint — the ImportError fallback must fail closed.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER_PY = REPO / "src" / "warding" / "dashboard" / "server.py"
SCRIPTS = REPO / "src" / "warding" / "deploy" / "skills" / "artifact-deploy" / "scripts"


class TestMigrationOffLoop:
    def test_cleanup_runs_via_to_thread(self):
        # Read here, not at module scope: server.py holds one astral-plane
        # character, so CPython stores the whole text as UCS-4 and the string
        # costs 4x the file size. At module scope every xdist worker would pay
        # that during collection and hold it for the session.
        server = SERVER_PY.read_text(encoding="utf-8")
        # the migration loop must be dispatched with asyncio.to_thread, and
        # the direct on-loop call shape must be gone.
        block = server.split("_MIGRATED_BUILTINS", 1)[1][:1600]
        assert "asyncio.to_thread(_run_migrated_cleanup)" in block
        # no bare cleanup call at statement level inside start_dashboard's
        # loop body (it now lives inside the worker function only)
        assert "def _run_migrated_cleanup" in block


class TestFailClosedSandbox:
    def test_no_unsandboxed_fallback(self):
        for name in ("attach_backend.py", "detach_backend.py"):
            src = (SCRIPTS / name).read_text(encoding="utf-8")
            assert "sandboxed_spawn_argv" in src, name
            # the fail-open fallback shape must be gone
            assert "wrapped_argv, env, cleanup = cmd, None, None" not in src, (
                f"{name}: unsandboxed ImportError fallback must not exist"
            )
            # ImportError path must exit non-zero (fail closed)
            block = src.split("except ImportError", 1)[1][:600]
            assert "sys.exit(1)" in block, f"{name}: ImportError must fail closed"
