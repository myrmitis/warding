"""Opt-in, observation-only pytest/xdist hang evidence.

Load with ``python -m pytest -p scripts.ci_pytest_diagnostics
--hang-diagnostics-dir=/absolute/path``. Logs contain node IDs, phases and
thread stacks, not locals or environment variables. No timeout/retry changes.
"""

from __future__ import annotations

import atexit
import faulthandler
import json
import math
import os
from pathlib import Path
import threading
import time

import pytest

_KEY = pytest.StashKey()
_CONSOLE = pytest.StashKey()


def pytest_addoption(parser):
    group = parser.getgroup("hang diagnostics")
    group.addoption("--hang-diagnostics-dir", default=None)
    group.addoption("--hang-diagnostics-interval", type=float, default=60.0)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_load_initial_conftests(early_config):
    # This explicit -p plugin loads before capture starts. Preserve the real
    # console descriptor; terminalreporter writes can themselves be captured.
    if getattr(early_config.known_args_namespace, "hang_diagnostics_dir", None):
        fd = os.dup(2)
        early_config.stash[_CONSOLE] = fd
        atexit.register(os.close, fd)
    yield


class Recorder:
    def __init__(self, config, root, interval):
        self.config = config
        self.console = config.stash[_CONSOLE]
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.interval = interval
        self.worker = getattr(config, "workerinput", {}).get("workerid", "controller")
        self.pid = os.getpid()
        self.prefix = f"{self.worker}-{self.pid}"
        self.events = (self.root / f"{self.prefix}.jsonl").open("a", encoding="utf-8", buffering=1)
        self.stacks = (self.root / f"{self.prefix}.stacks").open("a", encoding="utf-8", buffering=1)
        self.state = ("configure", "", time.monotonic())
        self.offsets = {}
        self.stop = threading.Event()
        self.record("configure")
        self.thread = threading.Thread(target=self.watch, name="pytest-hang-diagnostics", daemon=True)
        self.thread.start()
        # Keep watching through sessionfinish, unconfigure, and the interpreter's
        # non-daemon-thread join (which precedes atexit). Never delay process exit.
        atexit.register(self.close)

    def record(self, phase, nodeid="", **extra):
        # Diagnostics must never become a new test failure. Some application
        # tests patch time.time/time.monotonic globally; evidence collection is
        # best-effort and must survive those mocks and I/O teardown races.
        try:
            now_mono = time.monotonic()
            now_wall = time.time()
            self.state = (phase, nodeid, now_mono)
            self.events.write(json.dumps({
                "time": now_wall, "worker": self.worker, "pid": self.pid,
                "phase": phase, "nodeid": nodeid, **extra,
            }) + "\n")
        except Exception as exc:
            try:
                self.announce(
                    f"[hang-diagnostics] event write failed: {type(exc).__name__}"
                )
            except Exception:
                pass

    def announce(self, text):
        data = (text + "\n").encode("utf-8", errors="replace")
        while data:
            written = os.write(self.console, data)
            data = data[written:]

    def relay(self):
        # Workers' captured stdout is not a live xdist transport. Relay their
        # on-disk stacks from the controller before job cancellation can erase
        # the summary. Bounded reads also avoid a huge allocation after a stall.
        for path in sorted(self.root.glob("*.stacks")):
            with path.open("r", encoding="utf-8", errors="replace") as stream:
                stream.seek(self.offsets.get(path, 0))
                text = stream.read(65536)
                self.offsets[path] = stream.tell()
            if text:
                self.announce(f"[hang-diagnostics {path.name}]\n{text}")

    def watch(self):
        deadline = time.monotonic() + self.interval
        while not self.stop.wait(min(1.0, self.interval)):
            try:
                if time.monotonic() >= deadline:
                    phase, nodeid, started = self.state
                    self.stacks.write(json.dumps({
                        "time": time.time(), "worker": self.worker, "pid": self.pid,
                        "phase": phase, "nodeid": nodeid,
                        "phase_seconds": round(time.monotonic() - started, 3),
                    }) + "\n")
                    self.stacks.flush()
                    # Do not take ownership of dump_traceback_later or signals:
                    # pytest-timeout and pytest's faulthandler keep their timers.
                    faulthandler.dump_traceback(file=self.stacks, all_threads=True)
                    deadline = time.monotonic() + self.interval
                if self.worker == "controller":
                    self.relay()
            except (OSError, ValueError) as exc:
                self.announce(f"[hang-diagnostics] evidence write failed: {type(exc).__name__}")
                return

    @pytest.hookimpl(optionalhook=True)
    def pytest_handlecrashitem(self, crashitem, report, sched):
        # Observe only: never alter the report or reschedule work.
        self.record("crashitem", crashitem)
        self.announce(f"[hang-diagnostics] crashitem {crashitem}")

    def close(self):
        self.stop.set()
        self.thread.join(timeout=1)
        # Do not close a descriptor while faulthandler might still be using it.
        if not self.thread.is_alive():
            self.events.close()
            self.stacks.close()


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    root = config.getoption("--hang-diagnostics-dir")
    if not root:
        return
    interval = config.getoption("--hang-diagnostics-interval")
    if not math.isfinite(interval) or interval <= 0:
        raise pytest.UsageError("--hang-diagnostics-interval must be finite and positive")
    recorder = Recorder(config, root, interval)
    config.stash[_KEY] = recorder
    config.pluginmanager.register(recorder, "ci-hang-recorder")


def _record(config, phase, nodeid="", **extra):
    recorder = config.stash.get(_KEY, None)
    if recorder is not None:
        recorder.record(phase, nodeid, **extra)
    return recorder


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_collection(session):
    _record(session.config, "collection")
    yield
    _record(session.config, "collection-finished")


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtestloop(session):
    _record(session.config, "runtestloop")
    yield
    _record(session.config, "runtestloop-finished")


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_setup(item):
    _record(item.config, "setup", item.nodeid)
    yield
    _record(item.config, "setup-finished", item.nodeid)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_call(item):
    _record(item.config, "call", item.nodeid)
    yield
    _record(item.config, "call-finished", item.nodeid)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_teardown(item):
    _record(item.config, "teardown", item.nodeid)
    yield
    _record(item.config, "teardown-finished", item.nodeid)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    _record(session.config, "sessionfinish", exitstatus=int(exitstatus))
    yield
    _record(session.config, "sessionfinish-finished", exitstatus=int(session.exitstatus))


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_unconfigure(config):
    _record(config, "unconfigure")
    yield
    _record(config, "interpreter-shutdown")


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    recorder = _record(node.config, "worker-down", worker_id=node.gateway.id, error=str(error))
    if recorder is not None and error is not None:
        recorder.announce(f"[hang-diagnostics] worker-down {node.gateway.id}: {error}")
        for path in sorted(recorder.root.glob(f"{node.gateway.id}-*.jsonl")):
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - 8192))
                tail = stream.read().decode("utf-8", errors="replace")
            recorder.announce(f"[hang-diagnostics {path.name}] last events:\n{tail}")
        recorder.relay()
