"""Isolated subprocess probes; run without the application's root conftest.

python -m unittest discover -s scripts -p test_ci_pytest_diagnostics.py -v
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "pytest.ini").write_text("[pytest]\nxfail_strict=true\n", encoding="utf-8")
        self.logs = self.root / "evidence"

    def command(self, extra=(), enabled=True):
        args = [sys.executable, "-m", "pytest", "-c", str(self.root / "pytest.ini"),
                "--confcutdir", str(self.root), "-p", "scripts.ci_pytest_diagnostics", "-q"]
        if enabled:
            args += [f"--hang-diagnostics-dir={self.logs}", "--hang-diagnostics-interval=0.05"]
        return args + list(extra) + [str(self.root / "test_probe.py")]

    def environment(self):
        env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONPATH=str(ROOT))
        for key in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
            env.pop(key, None)
        return env

    def run_probe(self, source, *, conftest="", extra=(), enabled=True):
        (self.root / "test_probe.py").write_text(source, encoding="utf-8")
        (self.root / "conftest.py").write_text(conftest, encoding="utf-8")
        return subprocess.run(self.command(extra, enabled), cwd=self.root, env=self.environment(),
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                              encoding="utf-8", timeout=20)

    def events(self):
        return [json.loads(line) for file in self.logs.glob("*.jsonl")
                for line in file.read_text(encoding="utf-8").splitlines()]

    def assert_phase_dump(self, result, phase, nodeid=None):
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f'"phase": "{phase}"', result.stdout)
        self.assertIn("Thread ", result.stdout)
        if nodeid:
            self.assertIn(nodeid, result.stdout)

    def test_disabled_is_inert(self):
        result = self.run_probe("def test_ok(): pass\n", enabled=False)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(self.logs.exists())

    def test_phase_journal_and_success_unchanged(self):
        result = self.run_probe("def test_ok(): pass\n")
        self.assertEqual(result.returncode, 0, result.stdout)
        phases = [event["phase"] for event in self.events()]
        for phase in ("collection", "setup", "call", "teardown", "sessionfinish", "interpreter-shutdown"):
            self.assertIn(phase, phases)

    def test_assertion_and_strict_xpass_remain_failures(self):
        for source in ("def test_failure(): assert False\n",
                       "import pytest\n@pytest.mark.xfail\ndef test_xpass(): pass\n"):
            with self.subTest(source=source):
                result = self.run_probe(source)
                self.assertEqual(result.returncode, 1, result.stdout)

    def test_patched_time_cannot_break_the_test_run(self):
        result = self.run_probe(
            "def test_mocked_clock(): assert True\n",
            conftest=(
                "import pytest, unittest.mock\n"
                "@pytest.fixture(autouse=True)\n"
                "def mocked_clock():\n"
                "    with unittest.mock.patch('time.time', side_effect=[1.0]):\n"
                "        yield\n"
            ),
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("[hang-diagnostics] event write failed: StopIteration", result.stdout)

    def test_setup_stall(self):
        result = self.run_probe("def test_slow(): pass\n", conftest=(
            "import pytest, time\n@pytest.fixture(autouse=True)\n"
            "def slow_setup(): time.sleep(0.35)\n"))
        self.assert_phase_dump(result, "setup", "test_probe.py::test_slow")

    def test_call_stall(self):
        result = self.run_probe("import time\ndef test_slow(): time.sleep(0.35)\n")
        self.assert_phase_dump(result, "call", "test_probe.py::test_slow")

    def test_teardown_stall(self):
        result = self.run_probe("def test_slow(): pass\n", conftest=(
            "import pytest, time\n@pytest.fixture(autouse=True)\n"
            "def slow_teardown():\n    yield\n    time.sleep(0.35)\n"))
        self.assert_phase_dump(result, "teardown", "test_probe.py::test_slow")

    def test_sessionfinish_stall(self):
        result = self.run_probe("def test_ok(): pass\n", conftest=(
            "import time\ndef pytest_sessionfinish(session, exitstatus): time.sleep(0.35)\n"))
        self.assert_phase_dump(result, "sessionfinish")

    def test_interpreter_thread_join_stall(self):
        result = self.run_probe("import threading, time\ndef test_thread():\n"
                                "    threading.Thread(target=time.sleep, args=(0.6,)).start()\n")
        self.assert_phase_dump(result, "interpreter-shutdown")

    def test_diagnostics_are_live_before_process_exit(self):
        (self.root / "test_probe.py").write_text(
            "import time\ndef test_wait(): time.sleep(2)\n", encoding="utf-8")
        output = self.root / "live.log"
        with output.open("w", encoding="utf-8") as stream:
            process = subprocess.Popen(self.command(), cwd=self.root, env=self.environment(),
                                       stdout=stream, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    text = output.read_text(encoding="utf-8")
                    if '"phase": "call"' in text and "Thread " in text:
                        self.assertIsNone(process.poll(), text)
                        break
                    time.sleep(0.02)
                else:
                    self.fail(output.read_text(encoding="utf-8"))
                self.assertEqual(process.wait(timeout=8), 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)

    @unittest.skipUnless(importlib.util.find_spec("xdist"), "pytest-xdist unavailable")
    def test_worker_crash_is_named_and_remains_failed(self):
        result = self.run_probe("import os\ndef test_crash(): os._exit(17)\n",
                                extra=("-p", "xdist.plugin", "-n", "2", "--max-worker-restart=0"))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("[hang-diagnostics] crashitem test_probe.py::test_crash", result.stdout)
        self.assertIn("[hang-diagnostics] worker-down gw", result.stdout)
        self.assertTrue(any(e["phase"] == "call" and e["worker"].startswith("gw") for e in self.events()))

    @unittest.skipUnless(importlib.util.find_spec("pytest_timeout"), "pytest-timeout unavailable")
    def test_timeout_remains_failure(self):
        result = self.run_probe("import time\ndef test_timeout(): time.sleep(4)\n",
                                extra=("-p", "pytest_timeout", "--timeout=0.3"))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Timeout", result.stdout)

    @unittest.skipUnless(importlib.util.find_spec("pytest_cov"), "pytest-cov unavailable")
    def test_coverage_is_still_written(self):
        (self.root / "sample.py").write_text("def value(): return 42\n", encoding="utf-8")
        result = self.run_probe("from sample import value\ndef test_value(): assert value() == 42\n",
                                extra=("-p", "pytest_cov", "--cov=sample", "--cov-report=xml:coverage.xml"))
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('filename="sample.py"', (self.root / "coverage.xml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
