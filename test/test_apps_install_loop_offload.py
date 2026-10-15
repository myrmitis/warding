"""The app install/update copy stays off the event loop.

``install_app`` and ``update_app`` copy a whole app source tree into the data
home. The copy is blocking filesystem work. On a large tree it can take minutes.
The event loop runs one callback at a time, so a copy on the loop thread freezes
every task, including the liveness heartbeat. The loop-stall watchdog then
kills the gateway. Each async caller must hand the copy to a worker thread.

``test_app_manager.py`` proves that an offloaded copy does not block the loop,
but that test does the offload itself. It cannot see a caller that stops
offloading. The guards in this file sit at the callers, in the two tiers that
``test_apps_instances_loop_offload.py`` uses for the apps-dir walk:

- Behavior tests: each async entry point runs with a recording double in place
  of ``install_app`` / ``update_app``. The double records the thread it runs
  on, and it checks that the loop can still run a no-op while the copy is
  outstanding. A caller that calls the copy directly fails, and so does one
  that hands the copy to a worker but blocks the loop until it finishes.
- AST ratchet: no direct call of ``install_app`` / ``update_app`` may appear
  inside an ``async def`` frame of ``routes.py`` or ``registry.py``. A nested
  ``def`` / ``lambda`` is a separate frame (the offloaded callable itself), so
  ``run_in_executor(pool, lambda: update_app(...))`` passes. A nested ``def``
  that the async frame calls directly still counts, because its body runs on
  the loop. This file imports the frame scan from
  ``test_apps_instances_loop_offload.py``, so both ratchets apply one scope
  rule.
"""

from __future__ import annotations

import ast
import asyncio
import concurrent.futures
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from aiohttp import web
from aiohttp.streams import StreamReader
from aiohttp.test_utils import make_mocked_request
from test_apps_instances_loop_offload import _calls_in_async_frames, _module_tree

import warding.apps.hooks_integration as hooks_mod
import warding.apps.registry as registry_mod
import warding.apps.routes as routes_mod
from warding.apps.bridges import RegistrationResult
from warding.apps.manager import APP_MANIFEST_FILENAME, AppResult

_APP = "offload-guard"

# The blocking tree copies. Every async caller must offload both.
_COPY_FUNCTIONS = frozenset({"install_app", "update_app"})

# How long the copy double waits for the loop to run a no-op. A caller that
# awaits the worker leaves the loop idle, so the no-op runs at once. The bound
# only runs out when a caller blocks the loop on the worker, and that fails.
_LOOP_PROBE_TIMEOUT_S = 30.0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _copied() -> AppResult:
    return AppResult(ok=True, name=_APP, message="copied")


@dataclass(frozen=True)
class _CopyCall:
    thread: threading.Thread
    loop_ran: bool


def _copy_recorder(calls: list[_CopyCall]) -> Callable[..., AppResult]:
    """A copy double that records its thread and whether the loop stays free.

    A worker thread alone proves too little: a caller can submit the copy to a
    pool and then block the loop on ``.result()`` or ``join()``. So the double
    asks the loop to run a no-op and waits for it. The no-op runs only while the
    caller awaits the copy and leaves the loop free. Call this from the test
    coroutine, so it binds the test's loop.
    """
    loop = asyncio.get_running_loop()
    loop_thread = threading.current_thread()

    async def _noop() -> None:
        return None

    def _copy(*args: Any, **kwargs: Any) -> AppResult:
        thread = threading.current_thread()
        loop_ran = False
        if thread is not loop_thread:
            ping = asyncio.run_coroutine_threadsafe(_noop(), loop)
            try:
                ping.result(timeout=_LOOP_PROBE_TIMEOUT_S)
                loop_ran = True
            except concurrent.futures.TimeoutError:
                ping.cancel()
        calls.append(_CopyCall(thread, loop_ran))
        return _copied()

    return _copy


def _assert_offloaded(calls: list[_CopyCall], what: str) -> None:
    """Fail unless *what* ran on a worker while the loop stayed free.

    Call this from the test coroutine, which runs on the loop thread.
    """
    loop_thread = threading.current_thread()
    assert calls, f"{what} was never invoked"
    assert all(
        call.thread is not loop_thread for call in calls
    ), f"{what} ran synchronously on the event loop thread"
    assert all(
        call.loop_ran for call in calls
    ), f"the event loop stayed blocked while {what} ran on a worker"


def _write_source(root: Path) -> Path:
    """Create an app source tree whose manifest names ``_APP``."""
    root.mkdir(parents=True)
    manifest = {"name": _APP, "version": "1.0.0", "description": "offload guard"}
    (root / APP_MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _json_post(path: str, body: dict[str, Any], **kwargs: Any) -> web.Request:
    """A mocked POST whose ``await request.json()`` returns *body*."""
    payload = StreamReader(mock.Mock(_reading_paused=False), 2**16, loop=asyncio.get_running_loop())
    payload.feed_data(json.dumps(body).encode("utf-8"))
    payload.feed_eof()
    return make_mocked_request("POST", path, payload=payload, **kwargs)


async def _no_retained_startup_hook(app_name: str, *, bounded: bool) -> bool:
    """Report that no timed-out startup hook of *app_name* is still running."""
    return True


def _stub_handler_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Admit a route handler through the lifecycle steps around its copy.

    The per-app lock, the retained-startup-hook check, resource registration and
    deregistration, and the backend start/stop are not under test. The fakes
    admit the request and do no work.
    """
    monkeypatch.setattr(routes_mod, "app_lifecycle_lock", lambda name: asyncio.Lock())
    monkeypatch.setattr(routes_mod, "stop_retained_startup_hooks", _no_retained_startup_hook)
    monkeypatch.setattr(routes_mod, "register_app", lambda name: RegistrationResult())
    monkeypatch.setattr(routes_mod, "deregister_app", lambda name: RegistrationResult())
    monkeypatch.setattr(routes_mod, "start_app_backend", lambda name: None)
    monkeypatch.setattr(routes_mod, "stop_app_backend", lambda name: None)


def _stub_registry_install(
    monkeypatch: pytest.MonkeyPatch, source: Path, *, installed: dict[str, Any] | None
) -> None:
    """Take ``install_from_registry`` to its copy step without git or network.

    The fakes replace the catalog lookup, the manifest fetch, and the clone and
    build. They also admit the app through the policy gates and the
    retained-startup-hook check, which are not under test.
    """
    entry = {"name": _APP, "repo": f"https://example.com/{_APP}.git", "branch": "main"}
    manifest = json.loads((source / APP_MANIFEST_FILENAME).read_text(encoding="utf-8"))

    async def _fetch_manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return manifest

    async def _clone_build(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"ok": True, "pkg_dir": source}

    monkeypatch.setattr(registry_mod, "get_registry_app", lambda name: entry)
    monkeypatch.setattr(registry_mod, "get_app", lambda name: installed)
    monkeypatch.setattr(registry_mod, "_fetch_app_manifest", _fetch_manifest)
    monkeypatch.setattr(registry_mod, "_clone_build_app", _clone_build)
    monkeypatch.setattr(registry_mod, "app_admission_denied", lambda *a, **k: None)
    monkeypatch.setattr(registry_mod, "app_execution_denied", lambda *a, **k: None)
    # _retained_startup_refusal imports this name when it runs, so patch the
    # defining module rather than the registry namespace.
    monkeypatch.setattr(hooks_mod, "stop_retained_startup_hooks", _no_retained_startup_hook)
    # The entry has no _registry marker, so it is official. A successful
    # official install starts a daemon thread that can send a receipt over
    # HTTP; keep the test off the network.
    monkeypatch.setattr(registry_mod.install_receipt, "dispatch", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# Behavior: the copy runs on a worker thread, not the loop thread
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_install_app_copies_off_the_loop_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/apps/install must not run the install copy on the loop thread."""
    copy_calls: list[_CopyCall] = []
    source = _write_source(tmp_path / "source")
    _stub_handler_lifecycle(monkeypatch)
    monkeypatch.setattr(routes_mod, "install_app", _copy_recorder(copy_calls))

    resp = await routes_mod.handle_install_app(
        _json_post("/api/apps/install", {"source": str(source)})
    )

    assert resp.status == 201
    _assert_offloaded(copy_calls, "install_app")


@pytest.mark.asyncio
async def test_handle_update_app_copies_off_the_loop_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/apps/{name}/update must not run the update copy on the loop thread.

    The empty body makes the handler update from the recorded source, as the
    dashboard's update action does.
    """
    copy_calls: list[_CopyCall] = []
    installed = {
        "name": _APP,
        "lifecycle": "gateway",
        "source": str(_write_source(tmp_path / "source")),
        "enabled": True,
    }
    _stub_handler_lifecycle(monkeypatch)
    monkeypatch.setattr(routes_mod, "get_app", lambda name: installed)
    monkeypatch.setattr(routes_mod, "update_app", _copy_recorder(copy_calls))

    resp = await routes_mod.handle_update_app(
        _json_post(f"/api/apps/{_APP}/update", {}, match_info={"name": _APP})
    )

    assert resp.status == 200
    _assert_offloaded(copy_calls, "update_app")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "installed,copier",
    [(None, "install_app"), ({"name": _APP}, "update_app")],
    ids=["fresh-install", "reinstall"],
)
async def test_install_from_registry_copies_off_the_loop_thread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    installed: dict[str, Any] | None,
    copier: str,
) -> None:
    """A registry install or reinstall must not run its copy on the loop thread.

    Both copy functions are doubles, so nothing real is copied whichever one
    the install picks. The check on *copier* proves the test reached the call
    site that its case guards.
    """
    copy_calls: dict[str, list[_CopyCall]] = {name: [] for name in _COPY_FUNCTIONS}
    for name, record in copy_calls.items():
        monkeypatch.setattr(registry_mod, name, _copy_recorder(record))
    _stub_registry_install(monkeypatch, _write_source(tmp_path / "source"), installed=installed)

    result = await registry_mod.install_from_registry(_APP)

    assert result["ok"] is True, result
    _assert_offloaded(copy_calls[copier], copier)


# ---------------------------------------------------------------------------
# AST ratchet: no direct call of the copy in an async frame
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module", [routes_mod, registry_mod], ids=["routes", "registry"])
def test_no_direct_app_copy_in_async_frames(module: Any) -> None:
    """``install_app`` / ``update_app`` may not be called directly in an async
    frame. The caller must hand the copy to a worker as a callable: a bare name,
    a ``partial``, a ``lambda`` or a nested ``def``. A nested ``def`` that the
    frame calls directly counts as a direct call. The check matches the
    bare-name form and the attribute form (``manager.install_app()``), so a
    module prefix does not evade it."""
    offenders: list[str] = []
    for owner, call in _calls_in_async_frames(_module_tree(module)):
        func = call.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name in _COPY_FUNCTIONS:
            offenders.append(f"{module.__name__}:{owner}:{call.lineno} calls {name}()")
    assert not offenders, "direct app copy on the event loop:\n" + "\n".join(offenders)
