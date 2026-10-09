"""Regression tests for namespace launcher file placement and cleanup sweep.

Verifies:
  (a) namespace_argv() writes the launcher to ~/.warding/run/ with PID in name
  (b) cleanup_stale_sandbox_profiles() removes dead-PID files (.py and .sb)
  (c) cleanup_stale_sandbox_profiles() removes old-mtime live-PID files (age-based)
  (d) OverflowError from absurdly long PID strings is handled gracefully
  (e) makedirs-failure falls back to system tmpdir
  (f) run_dir is created with mode 0o700
  (g) non-conforming filenames are left untouched
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from warding.sandbox import (
    _LAUNCHER_MAX_AGE_SECONDS,
    _ensure_run_dir,
    cleanup_stale_sandbox_profiles,
    namespace_argv,
)


@pytest.fixture()
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect HOME so the sandbox run dir resolves under ``tmp_path/.warding``.

    The run dir is ``config_dir()/run``. ``config_dir()`` reads ``WARDING_HOME``
    (pinned to a different tmp dir by conftest), so also redirect
    ``sandbox.config_dir`` to ``tmp_path/".warding"`` — keeping the
    ``.warding/run`` layout these tests assert. ``expanduser``/``HOME`` are still
    patched for the non-run-dir ``~`` lookups in this module.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path) + p[1:] if p.startswith("~") else p)
    monkeypatch.setattr("warding.sandbox.config_dir", lambda: tmp_path / ".warding")
    return tmp_path


class TestNamespaceArgvPlacement:
    """namespace_argv() launcher lands in ~/.warding/run/ with PID."""

    @patch("warding.sandbox.detect_backend", return_value="namespace")
    def test_launcher_in_run_dir(self, _mock_detect, fake_home: Path):
        run_dir = fake_home / ".warding" / "run"
        result = namespace_argv(["kiro-cli", "--version"])

        # Result should be [python, launcher_path, *real_argv]
        assert len(result) >= 2
        launcher = result[1]
        assert launcher.startswith(str(run_dir)), f"launcher {launcher} not under {run_dir}"

    @patch("warding.sandbox.detect_backend", return_value="namespace")
    def test_launcher_has_pid_in_name(self, _mock_detect, fake_home: Path):
        result = namespace_argv(["kiro-cli", "--version"])
        launcher = Path(result[1])
        # Filename pattern: warding_sandbox_{pid}_{random}.py
        assert launcher.name.startswith(f"warding_sandbox_{os.getpid()}_")
        assert launcher.suffix == ".py"

    @patch("warding.sandbox.detect_backend", return_value="namespace")
    def test_launcher_is_executable(self, _mock_detect, fake_home: Path):
        result = namespace_argv(["kiro-cli", "--version"])
        launcher = result[1]
        stat = os.stat(launcher)
        assert stat.st_mode & 0o700 == 0o700


class TestRunDirMode:
    """_ensure_run_dir() creates directory with 0o700 permissions."""

    def test_run_dir_mode_0o700(self, fake_home: Path):
        run_dir = _ensure_run_dir()
        stat = os.stat(run_dir)
        assert stat.st_mode & 0o777 == 0o700

    def test_run_dir_mode_enforced_on_existing(self, fake_home: Path):
        """Even if the dir already exists with wrong perms, chmod fixes it."""
        run_dir = fake_home / ".warding" / "run"
        run_dir.mkdir(parents=True, mode=0o755)
        result = _ensure_run_dir()
        stat = os.stat(result)
        assert stat.st_mode & 0o777 == 0o700

    def test_makedirs_failure_falls_back(self, fake_home: Path, monkeypatch: pytest.MonkeyPatch):
        """If makedirs raises, fall back to system tmpdir."""
        # Create a regular file at the expected dir path to cause makedirs failure
        warding_dir = fake_home / ".warding"
        warding_dir.mkdir(parents=True, exist_ok=True)
        # Put a regular file where "run" dir should be
        (warding_dir / "run").write_text("blocker")

        run_dir = _ensure_run_dir()
        import tempfile
        assert run_dir == tempfile.gettempdir()


class TestCleanupSweep:
    """cleanup_stale_sandbox_profiles() sweeps both .py and .sb dead-PID files."""

    def test_removes_dead_pid_py(self, fake_home: Path):
        run_dir = fake_home / ".warding" / "run"
        run_dir.mkdir(parents=True)
        # PID 99999999 is almost certainly dead
        dead_file = run_dir / "warding_sandbox_99999999_abc123.py"
        dead_file.write_text("# dead launcher")

        removed = cleanup_stale_sandbox_profiles()
        assert not dead_file.exists()
        assert removed == 1

    def test_removes_dead_pid_sb(self, fake_home: Path):
        run_dir = fake_home / ".warding" / "run"
        run_dir.mkdir(parents=True)
        dead_file = run_dir / "warding_sandbox_99999999_xyz789.sb"
        dead_file.write_text("(version 1)")

        removed = cleanup_stale_sandbox_profiles()
        assert not dead_file.exists()
        assert removed == 1

    def test_removes_old_mtime_live_pid(self, fake_home: Path):
        """Age-based reaping: old file removed even if tagged PID is alive."""
        run_dir = fake_home / ".warding" / "run"
        run_dir.mkdir(parents=True)
        # Use our own PID — definitely alive
        live_file = run_dir / f"warding_sandbox_{os.getpid()}_old123.py"
        live_file.write_text("# old launcher")
        # Set mtime to 2 hours ago (well past threshold)
        old_time = time.time() - _LAUNCHER_MAX_AGE_SECONDS - 100
        os.utime(live_file, (old_time, old_time))

        removed = cleanup_stale_sandbox_profiles()
        assert not live_file.exists()
        assert removed == 1

    def test_keeps_fresh_live_pid(self, fake_home: Path):
        """Fresh file with live PID is kept."""
        run_dir = fake_home / ".warding" / "run"
        run_dir.mkdir(parents=True)
        live_file = run_dir / f"warding_sandbox_{os.getpid()}_fresh123.py"
        live_file.write_text("# fresh launcher")

        removed = cleanup_stale_sandbox_profiles()
        assert live_file.exists()
        assert removed == 0

    def test_keeps_live_pid_sb(self, fake_home: Path):
        run_dir = fake_home / ".warding" / "run"
        run_dir.mkdir(parents=True)
        live_file = run_dir / f"warding_sandbox_{os.getpid()}_live456.sb"
        live_file.write_text("(version 1)")

        removed = cleanup_stale_sandbox_profiles()
        assert live_file.exists()
        assert removed == 0

    def test_overflow_error_resilience(self, fake_home: Path):
        """Absurdly long digit string doesn't crash the sweep."""
        run_dir = fake_home / ".warding" / "run"
        run_dir.mkdir(parents=True)
        # PID that exceeds sys.maxsize causing OverflowError in os.kill
        huge_pid = "9" * 30  # 30 digits > sys.maxsize on 64-bit
        bad_file = run_dir / f"warding_sandbox_{huge_pid}_x.py"
        bad_file.write_text("# overflow")
        # Also add a normal dead-PID file to confirm sweep continues
        normal_dead = run_dir / "warding_sandbox_99999999_y.py"
        normal_dead.write_text("# dead")

        removed = cleanup_stale_sandbox_profiles()
        # Both should be removed (huge via age fallback or error, normal via dead-PID)
        assert not normal_dead.exists()
        assert removed >= 1  # at least the normal dead one

    def test_ignores_nonconforming_filenames(self, fake_home: Path):
        run_dir = fake_home / ".warding" / "run"
        run_dir.mkdir(parents=True)
        # Wrong prefix
        f1 = run_dir / "other_file_99999999_abc.py"
        f1.write_text("# unrelated")
        # Wrong suffix
        f2 = run_dir / "warding_sandbox_99999999_abc.txt"
        f2.write_text("# unrelated")
        # No PID (no underscore separator)
        f3 = run_dir / "warding_sandbox_nopid.py"
        f3.write_text("# unrelated")
        # Right prefix, right suffix, but non-digit PID
        f4 = run_dir / "warding_sandbox_notapid_abc.py"
        f4.write_text("# unrelated")

        removed = cleanup_stale_sandbox_profiles()
        assert f1.exists()
        assert f2.exists()
        assert f3.exists()
        assert f4.exists()
        assert removed == 0

    def test_no_run_dir_is_noop(self, fake_home: Path):
        """If ~/.warding/run/ doesn't exist, no crash."""
        removed = cleanup_stale_sandbox_profiles()  # should not raise
        assert removed == 0
