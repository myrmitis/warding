"""The app install/update metadata reads and writes stay off the event loop.

An app install or update reads and writes small metadata files. ``get_app``
reads ``installed.json`` and ``app.json``. ``register_external_app`` registers a
self-managed app, and ``set_app_provenance`` records the source the app came
from. The local install route also resolves the source path and reads its
manifest. Each call is short, but on a stalled filesystem it blocks in the
kernel. On the loop thread that freezes every task, including the liveness
heartbeat, until the loop-stall watchdog kills the gateway. So each async caller
hands these calls to a worker thread.

The guards use the two tiers of ``test_apps_instances_loop_offload.py``:

- Behavior tests: each async entry point runs with recording doubles in place
  of the metadata functions, or with a ``Path`` class that records each call and
  then does the real filesystem work. A double records the thread it runs on, so
  a direct call records the loop thread and fails the test.
- AST ratchet: no direct call of a moved function may appear in an
  ``async def`` frame of ``registry.py``. A nested ``def`` that the frame calls
  directly counts as part of the frame. Other ``routes.py`` handlers still call
  ``get_app`` on the loop, so the ``routes.py`` check covers only the install
  and update handler frames.

``install_from_registry`` runs under its caller's ``app_lifecycle_lock``. The
last tests cancel an install during a metadata write. The install must not
unwind, and so release that lock, until the write is done.
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import threading
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from test_apps_instances_loop_offload import _module_tree, _recorder

import warding.apps.hooks_integration as hooks_mod
import warding.apps.manager as manager_mod
import warding.apps.registry as registry_mod
import warding.apps.routes as routes_mod
from warding.apps.bridges import RegistrationResult
from warding.apps.manager import APP_MANIFEST_FILENAME, AppResult

_APP = "metadata-offload"

# The metadata functions that install_from_registry calls. None may run on the loop.
_REGISTRY_METADATA_CALLS = frozenset({"get_app", "register_external_app", "set_app_provenance"})

# The Path methods that the install handler calls on the source tree.
_SOURCE_PATH_CALLS = ("resolve", "is_dir", "is_file", "read_text")

# The route handlers under guard, and the blocking filesystem calls they may not
# make on the loop.
_ROUTE_HANDLERS = frozenset({"handle_install_app", "handle_update_app"})
_ROUTE_FILESYSTEM_CALLS = frozenset({"get_app", *_SOURCE_PATH_CALLS})

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_source(root: Path) -> Path:
    """Create an app source tree whose manifest names ``_APP``."""
    root.mkdir(parents=True)
    manifest = {"name": _APP, "version": "1.0.0", "description": "metadata offload guard"}
    (root / APP_MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _json_post(path: str, body: dict[str, Any]) -> web.Request:
    """A mocked POST whose ``await request.json()`` returns *body*."""
    request = make_mocked_request("POST", path)
    request.json = AsyncMock(return_value=body)  # type: ignore[method-assign]
    return request


async def _no_retained_startup_hook(app_name: str, *, bounded: bool) -> bool:
    """Report that no timed-out startup hook of *app_name* is still running."""
    return True


def _stub_registry_install(
    monkeypatch: pytest.MonkeyPatch, source: Path, *, self_managed: bool
) -> None:
    """Take ``install_from_registry`` to its registration step without git or network.

    The fakes replace the catalog lookup, the manifest fetch, the clone and
    build, and the copy. They admit the app through the policy gates and the
    retained-startup-hook check, which are not under test. Each test patches the
    metadata functions itself.
    """
    entry: dict[str, Any] = {
        "name": _APP,
        "repo": f"https://example.com/{_APP}.git",
        "branch": "main",
    }
    if self_managed:
        entry["resources"] = "app"  # the app registers its own resources
    manifest = json.loads((source / APP_MANIFEST_FILENAME).read_text(encoding="utf-8"))
    copied = AppResult(ok=True, name=_APP, message="copied")

    async def _fetch_manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return manifest

    async def _clone_build(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"ok": True, "pkg_dir": source}

    monkeypatch.setattr(registry_mod, "get_registry_app", lambda name: entry)
    monkeypatch.setattr(registry_mod, "_fetch_app_manifest", _fetch_manifest)
    monkeypatch.setattr(registry_mod, "_clone_build_app", _clone_build)
    monkeypatch.setattr(registry_mod, "install_app", lambda *a, **k: copied)
    monkeypatch.setattr(registry_mod, "update_app", lambda *a, **k: copied)
    monkeypatch.setattr(registry_mod, "app_admission_denied", lambda *a, **k: None)
    monkeypatch.setattr(registry_mod, "app_execution_denied", lambda *a, **k: None)
    # _retained_startup_refusal imports this name when it runs, so patch the
    # defining module rather than the registry namespace.
    monkeypatch.setattr(hooks_mod, "stop_retained_startup_hooks", _no_retained_startup_hook)
    # The entry has no _registry marker, so it is official. A successful
    # official install starts a thread that can send a receipt over HTTP; keep
    # the test off the network.
    monkeypatch.setattr(registry_mod.install_receipt, "dispatch", lambda *a, **k: None)


def _patch_registry_writes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    register: Callable[..., Any],
    provenance: Callable[..., Any],
) -> None:
    """Install doubles for the two metadata writes of a registry install."""
    # install_from_registry imports register_external_app when it runs, so
    # patch the defining module.
    monkeypatch.setattr(manager_mod, "register_external_app", register)
    monkeypatch.setattr(registry_mod, "set_app_provenance", provenance)


def _recording_path_class(calls: list[tuple[str, threading.Thread]]) -> type[Path]:
    """Return a ``Path`` class that records the thread of each source-tree call.

    Each recorded method then calls the real one, so the handler still reads
    the real source tree. A path derived from an instance keeps the class, so
    ``source_path / "app.json"`` records too.
    """
    concrete = type(Path())

    def _spy(name: str) -> Callable[..., Any]:
        real = getattr(concrete, name)

        def _method(self: Path, *args: Any, **kwargs: Any) -> Any:
            calls.append((name, threading.current_thread()))
            return real(self, *args, **kwargs)

        return _method

    return type("_RecordingPath", (concrete,), {name: _spy(name) for name in _SOURCE_PATH_CALLS})


class _BlockingCall:
    """Wrap a double so that its call blocks in the worker thread until released."""

    def __init__(self, inner: Callable[..., Any]) -> None:
        self._inner = inner
        self.started = threading.Event()
        self.release = threading.Event()

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.started.set()
        self.release.wait(30)
        return self._inner(*args, **kwargs)


async def _install_under_lock(lock: Any) -> dict[str, Any]:
    """Install ``_APP`` as the routes do: under the app's lifecycle lock."""
    async with lock:
        return await registry_mod.install_from_registry(_APP)


async def _let_cancellation_land() -> None:
    """Run the loop's ready callbacks, so a delivered cancellation reaches the task.

    A task that does not wait for its worker unwinds on the first turn. A few
    turns of margin keep this deterministic without a wall-clock sleep.
    """
    for _ in range(5):
        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# Behavior: the metadata I/O runs on a worker thread, not the loop thread
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "self_managed,expected_calls",
    [
        (False, {"get_app", "set_app_provenance"}),
        (True, {"get_app", "register_external_app", "set_app_provenance"}),
    ],
    ids=["warding-managed", "self-managed"],
)
async def test_install_from_registry_metadata_io_runs_off_the_loop_thread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    self_managed: bool,
    expected_calls: set[str],
) -> None:
    """A registry install must not read or write app metadata on the loop thread.

    The check on *expected_calls* proves that the install reached every
    metadata call that its path makes.
    """
    loop_thread = threading.current_thread()
    threads: dict[str, list[threading.Thread]] = {name: [] for name in _REGISTRY_METADATA_CALLS}
    _stub_registry_install(
        monkeypatch, _write_source(tmp_path / "source"), self_managed=self_managed
    )
    monkeypatch.setattr(registry_mod, "get_app", _recorder(threads["get_app"]))
    _patch_registry_writes(
        monkeypatch,
        register=_recorder(threads["register_external_app"], result=AppResult(ok=True, name=_APP)),
        provenance=_recorder(threads["set_app_provenance"], result=True),
    )

    result = await registry_mod.install_from_registry(_APP)

    assert result["ok"] is True, result
    assert {name for name, record in threads.items() if record} == expected_calls
    on_loop = sorted(name for name, record in threads.items() if loop_thread in record)
    assert not on_loop, f"app metadata I/O ran on the event loop thread: {on_loop}"


@pytest.mark.asyncio
async def test_handle_install_app_reads_the_source_off_the_loop_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/apps/install must not touch the source tree on the loop thread.

    Before it takes the app's lifecycle lock, the handler resolves the source
    path, checks it, and reads its manifest for the app's name.
    """
    loop_thread = threading.current_thread()
    calls: list[tuple[str, threading.Thread]] = []
    source = _write_source(tmp_path / "source")
    monkeypatch.setattr(routes_mod, "Path", _recording_path_class(calls))
    # The lock, the startup-hook check, the copy, the resource registration, and
    # the backend start are not under test.
    monkeypatch.setattr(routes_mod, "app_lifecycle_lock", lambda name: asyncio.Lock())
    monkeypatch.setattr(routes_mod, "stop_retained_startup_hooks", _no_retained_startup_hook)
    monkeypatch.setattr(routes_mod, "install_app", lambda *a, **k: AppResult(ok=True, name=_APP))
    monkeypatch.setattr(routes_mod, "register_app", lambda name: RegistrationResult())
    monkeypatch.setattr(routes_mod, "start_app_backend", lambda name: None)

    resp = await routes_mod.handle_install_app(
        _json_post("/api/apps/install", {"source": str(source)})
    )

    assert resp.status == 201
    assert "read_text" in {name for name, _ in calls}, "the source manifest was never read"
    on_loop = sorted({name for name, thread in calls if thread is loop_thread})
    assert not on_loop, f"the install handler touched the source on the loop thread: {on_loop}"


@pytest.mark.asyncio
async def test_handle_update_app_reads_the_installed_metadata_off_the_loop_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/apps/{name}/update must not read the installed metadata on the
    loop thread. The app is not installed, so the handler answers 404 right
    after that read."""
    loop_thread = threading.current_thread()
    read_threads: list[threading.Thread] = []
    monkeypatch.setattr(routes_mod, "get_app", _recorder(read_threads))

    resp = await routes_mod.handle_update_app(
        make_mocked_request("POST", f"/api/apps/{_APP}/update", match_info={"name": _APP})
    )

    assert resp.status == 404
    assert read_threads, "get_app was never invoked"
    assert loop_thread not in read_threads, "get_app ran on the event loop thread"


# ---------------------------------------------------------------------------
# Cancellation: a metadata write finishes before the lifecycle lock is released
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "self_managed,blocked",
    [(False, "set_app_provenance"), (True, "register_external_app")],
    ids=["warding-managed-provenance", "self-managed-registration"],
)
async def test_cancelled_install_holds_the_lifecycle_lock_until_its_writes_finish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, self_managed: bool, blocked: str
) -> None:
    """A cancelled registry install must not release the app's lifecycle lock
    while a metadata write is still running.

    A cancelled ``to_thread`` await does not stop its thread. If the install
    unwound at once, a concurrent uninstall could remove the app, and the late
    write would then re-create its metadata. A self-managed install must also
    record its provenance with its registration: a cancellation may not cut the
    provenance off.
    """
    _stub_registry_install(
        monkeypatch, _write_source(tmp_path / "source"), self_managed=self_managed
    )
    monkeypatch.setattr(registry_mod, "get_app", lambda name: None)
    # A private lock table, so that this test's lock is not shared with others.
    monkeypatch.setattr(manager_mod, "_LIFECYCLE_LOCKS", {})
    provenance_threads: list[threading.Thread] = []
    writes: dict[str, Callable[..., Any]] = {
        "register_external_app": lambda *a, **k: AppResult(ok=True, name=_APP),
        "set_app_provenance": _recorder(provenance_threads, result=True),
    }
    gate = _BlockingCall(writes[blocked])
    writes[blocked] = gate
    _patch_registry_writes(
        monkeypatch,
        register=writes["register_external_app"],
        provenance=writes["set_app_provenance"],
    )
    lock = manager_mod.app_lifecycle_lock(_APP)

    task = asyncio.create_task(_install_under_lock(lock))
    try:
        assert await asyncio.to_thread(gate.started.wait, 10), f"{blocked} was never called"
        task.cancel()
        await _let_cancellation_land()
        assert not task.done(), "the install unwound while a metadata write was still running"
        assert lock.locked(), "the lifecycle lock was released while a metadata write was running"
    finally:
        gate.release.set()
        (outcome,) = await asyncio.gather(task, return_exceptions=True)

    assert isinstance(outcome, asyncio.CancelledError), outcome
    assert provenance_threads, "the install unwound before it recorded the app's provenance"


@pytest.mark.asyncio
async def test_a_write_that_fails_after_the_cancellation_is_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The caller receives the cancellation, so a metadata write that fails after
    it must leave a warning instead of disappearing."""
    _stub_registry_install(monkeypatch, _write_source(tmp_path / "source"), self_managed=False)
    monkeypatch.setattr(registry_mod, "get_app", lambda name: None)
    failure = OSError("installed.json could not be written")

    def _fail(*args: Any, **kwargs: Any) -> bool:
        raise failure

    gate = _BlockingCall(_fail)
    monkeypatch.setattr(registry_mod, "set_app_provenance", gate)

    with caplog.at_level(logging.WARNING, logger=registry_mod.logger.name):
        task = asyncio.create_task(registry_mod.install_from_registry(_APP))
        try:
            assert await asyncio.to_thread(gate.started.wait, 10), "the write was never called"
            task.cancel()
            await _let_cancellation_land()
        finally:
            gate.release.set()
            (outcome,) = await asyncio.gather(task, return_exceptions=True)

    assert isinstance(outcome, asyncio.CancelledError), outcome
    # Only the registry's own warning counts: asyncio also logs an exception
    # that nobody retrieved, but only when it collects the task, which is late.
    logged = [
        record
        for record in caplog.records
        if record.name == registry_mod.logger.name
        and record.levelno == logging.WARNING
        and record.exc_info is not None
        and record.exc_info[1] is failure
    ]
    assert logged, "the write failure after the cancellation was not logged"


# ---------------------------------------------------------------------------
# AST ratchet: no direct metadata call in the guarded async frames
# ---------------------------------------------------------------------------

# Scopes that are not part of the enclosing frame: a nested function or lambda
# runs only when something calls it.
_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _frame_nodes(nodes: Iterable[ast.AST]) -> Iterator[ast.AST]:
    """Yield *nodes* and their descendants, without entering a nested scope."""
    for node in nodes:
        yield node
        if not isinstance(node, _NESTED_SCOPES):
            yield from _frame_nodes(ast.iter_child_nodes(node))


def _calls_on_the_loop(tree: ast.AST) -> list[tuple[str, ast.Call]]:
    """Every call that runs in the frame of an ``async def`` in *tree*.

    This uses the scope rule of ``test_apps_instances_loop_offload.py``: a
    nested ``def`` or ``lambda`` is a separate frame, usually the callable
    handed to a worker, so it is not scanned. The one addition: when the async
    frame calls a nested sync ``def`` directly, that body runs on the loop too,
    so it is scanned as part of the frame.
    """
    found: list[tuple[str, ast.Call]] = []
    for frame in ast.walk(tree):
        if not isinstance(frame, ast.AsyncFunctionDef):
            continue
        local_defs = {
            node.name: node
            for node in _frame_nodes(frame.body)
            if isinstance(node, ast.FunctionDef)
        }
        bodies: list[list[ast.stmt]] = [frame.body]
        entered: set[str] = set()
        while bodies:
            for node in _frame_nodes(bodies.pop()):
                if not isinstance(node, ast.Call):
                    continue
                found.append((frame.name, node))
                callee = node.func.id if isinstance(node.func, ast.Name) else ""
                if callee in local_defs and callee not in entered:
                    entered.add(callee)
                    bodies.append(local_defs[callee].body)
    return found


def _direct_calls(
    tree: ast.AST, module: str, banned: frozenset[str], frames: frozenset[str] | None = None
) -> list[str]:
    """Calls of a *banned* name in the async frames of *tree*, or only in *frames*.

    Both the bare-name form (``get_app()``) and the attribute form
    (``manager.get_app()``) match, so a module prefix does not evade the check.
    A callable handed to a worker is a name, not a call, so it does not match.
    """
    offenders: list[str] = []
    for owner, call in _calls_on_the_loop(tree):
        if frames is not None and owner not in frames:
            continue
        func = call.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name in banned:
            offenders.append(f"{module}:{owner}:{call.lineno} calls {name}()")
    return offenders


def test_no_direct_metadata_call_in_registry_async_frames() -> None:
    """``registry.py`` may not call a metadata function directly in any async
    frame. A caller hands the function to a worker: as a bare name, a
    ``partial``, or a nested ``def`` that only the worker calls."""
    offenders = _direct_calls(
        _module_tree(registry_mod), registry_mod.__name__, _REGISTRY_METADATA_CALLS
    )
    assert not offenders, "direct app metadata I/O on the event loop:\n" + "\n".join(offenders)


def test_no_direct_filesystem_call_in_the_install_and_update_handlers() -> None:
    """The install and update handlers may not call a blocking filesystem
    function directly. The check names its frames, so it fails when one of
    them disappears instead of passing with nothing to scan."""
    tree = _module_tree(routes_mod)
    async_frames = {node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)}
    missing = sorted(_ROUTE_HANDLERS - async_frames)
    assert not missing, f"guarded handlers not found in {routes_mod.__name__}: {missing}"

    offenders = _direct_calls(
        tree, routes_mod.__name__, _ROUTE_FILESYSTEM_CALLS, frames=_ROUTE_HANDLERS
    )
    assert not offenders, "direct filesystem call on the event loop:\n" + "\n".join(offenders)
