"""The app routes and the registry install keep their file I/O off the event loop.

An app install or update reads and writes small metadata files. ``get_app``
reads ``installed.json`` and ``app.json``. ``register_external_app`` registers a
self-managed app, and ``set_app_provenance`` records the source the app came
from. The registry install also checks the trust grants, the admission policy
and the execution policy, which read config files, and resolves the app's
subdirectory. The app routes read app metadata, app config, UI files, cached
blobs and ``config.json``. Each call is short, but on a stalled filesystem it
blocks in the kernel. On the loop thread that freezes every task, including the
liveness heartbeat, until the loop-stall watchdog kills the gateway. So each
async caller hands these calls to a worker thread.

The guards use the two tiers of ``test_apps_instances_loop_offload.py``:

- Behavior tests: each async entry point runs with recording doubles in place
  of the metadata functions, or with a ``Path`` class that records each call and
  then does the real filesystem work. A double records the thread it runs on, so
  a direct call records the loop thread and fails the test.
- AST ratchet: no direct call of a moved function may appear in an
  ``async def`` frame of ``registry.py`` or ``routes.py``. A nested ``def`` that
  the frame calls directly counts as part of the frame. Other async functions
  of ``registry.py`` still run the policy checks on the loop, so that check
  covers only ``install_from_registry``.

``install_from_registry`` runs under its caller's ``app_lifecycle_lock``. The
cancellation tests cancel an install during a metadata write. The install must
not unwind, and so release that lock, until the write is done. The same holds
for the tree copy (``install_app`` or ``update_app``) in a registry install and
in the install and update handlers.
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

# The policy and containment checks of install_from_registry. Each reads a
# config file or resolves a path. Other async registry functions still call
# some of them on the loop, so this set is checked in that one frame only.
_REGISTRY_INSTALL_FRAME = "install_from_registry"
_REGISTRY_INSTALL_POLICY_CALLS = frozenset(
    {
        "trusted_app_repository",
        "repository_bound_grant_denied",
        "app_admission_denied",
        "app_execution_denied",
        "_contained_join",
    }
)

# The blocking filesystem calls that no async frame of routes.py may make
# directly. A method name matches on any receiver, so a Path method is covered
# whatever the variable is called. The underscored names are the routes.py
# helpers that group several of these calls into one worker hop.
_ROUTE_FILESYSTEM_CALLS = frozenset(
    {
        "_ui_file_refusal",
        "_prepare_blob_cache_path",
        "_read_config_object",
        "_write_config_object",
        "_remove_app_workspace",
        "get_app",
        "get_app_manifest",
        "app_data_dir",
        "atomic_write",
        "rmtree",
        "resolve",
        "exists",
        "is_dir",
        "is_file",
        "mkdir",
        "read_text",
        "read_bytes",
        "write_text",
        "write_bytes",
    }
)

# Handlers that the module-wide routes.py check must find as async frames.
# Each one did blocking file I/O on the loop before it was moved.
_ROUTE_HANDLERS = frozenset(
    {
        "handle_install_app",
        "handle_update_app",
        "handle_get_app",
        "handle_get_manifest",
        "handle_uninstall_preview",
        "handle_uninstall_app",
        "handle_enable_app",
        "handle_disable_app",
        "handle_open_app",
        "handle_app_config",
        "handle_app_ui_file",
        "handle_blob_proxy",
        "_fetch_git_blob",
        "handle_registries",
    }
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_source(root: Path, **manifest_fields: Any) -> Path:
    """Create an app source tree whose manifest names ``_APP``."""
    root.mkdir(parents=True)
    manifest = {"name": _APP, "version": "1.0.0", "description": "metadata offload guard"}
    manifest.update(manifest_fields)
    (root / APP_MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _spy(record: list[threading.Thread], real: Callable[..., Any]) -> Callable[..., Any]:
    """A stand-in that records the thread it runs on, then calls *real*."""

    def _fn(*args: Any, **kwargs: Any) -> Any:
        record.append(threading.current_thread())
        return real(*args, **kwargs)

    return _fn


def _on_loop(calls: Iterable[tuple[str, threading.Thread]], loop: threading.Thread) -> list[str]:
    """The names of the recorded *calls* that ran on the *loop* thread."""
    return sorted({name for name, thread in calls if thread is loop})


def _json_post(
    path: str, body: dict[str, Any], match_info: dict[str, str] | None = None
) -> web.Request:
    """A mocked POST whose ``await request.json()`` returns *body*."""
    request = make_mocked_request("POST", path, match_info=match_info or {})
    request.json = AsyncMock(return_value=body)  # type: ignore[method-assign]
    return request


async def _no_retained_startup_hook(app_name: str, *, bounded: bool) -> bool:
    """Report that no timed-out startup hook of *app_name* is still running."""
    return True


def _stub_registry_install(
    monkeypatch: pytest.MonkeyPatch,
    source: Path,
    *,
    self_managed: bool,
    subdirectory: str = "",
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
    if subdirectory:
        entry["subdirectory"] = subdirectory
    manifest = json.loads(
        (source / subdirectory / APP_MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
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


def _recording_path_class(
    calls: list[tuple[str, threading.Thread]], names: Iterable[str] = _SOURCE_PATH_CALLS
) -> type[Path]:
    """Return a ``Path`` class that records the thread of each call of *names*.

    Each recorded method then calls the real one, so the handler still works
    on the real files. A path derived from an instance keeps the class, so
    ``source_path / "app.json"`` and ``path.parent`` record too.
    """
    concrete = type(Path())

    def _spy(name: str) -> Callable[..., Any]:
        real = getattr(concrete, name)

        def _method(self: Path, *args: Any, **kwargs: Any) -> Any:
            calls.append((name, threading.current_thread()))
            return real(self, *args, **kwargs)

        return _method

    return type("_RecordingPath", (concrete,), {name: _spy(name) for name in names})


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
async def test_install_from_registry_policy_checks_run_off_the_loop_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A registry install must not check its trust grants, its admission and
    execution policies, or its subdirectory's containment on the loop thread.

    The app sits in a subdirectory and declares an install script, so the
    install reaches the containment check and all three admission gates: before
    the clone, after the build and after the script. The script does not run:
    a fake process stands in for it.
    """
    loop_thread = threading.current_thread()
    source = tmp_path / "source"
    _write_source(source / "pkg", setup={"onInstall": "true"})
    _stub_registry_install(monkeypatch, source, self_managed=False, subdirectory="pkg")
    monkeypatch.setattr(registry_mod, "get_app", lambda name: None)
    _patch_registry_writes(
        monkeypatch,
        register=lambda *a, **k: AppResult(ok=True, name=_APP),
        provenance=lambda *a, **k: True,
    )
    threads: dict[str, list[threading.Thread]] = {
        name: [] for name in _REGISTRY_INSTALL_POLICY_CALLS
    }
    monkeypatch.setattr(
        registry_mod, "trusted_app_repository", _recorder(threads["trusted_app_repository"], "")
    )
    monkeypatch.setattr(
        registry_mod,
        "repository_bound_grant_denied",
        _recorder(threads["repository_bound_grant_denied"]),
    )
    monkeypatch.setattr(
        registry_mod, "app_admission_denied", _recorder(threads["app_admission_denied"])
    )
    monkeypatch.setattr(
        registry_mod, "app_execution_denied", _recorder(threads["app_execution_denied"])
    )
    monkeypatch.setattr(
        registry_mod,
        "_contained_join",
        _spy(threads["_contained_join"], registry_mod._contained_join),
    )

    class _FinishedScript:
        """A finished install script: exit 0, no output, no process group."""

        pid = None
        returncode = 0

        async def communicate(self) -> tuple[bytes, None]:
            return b"", None

    async def _spawn(*args: Any, **kwargs: Any) -> _FinishedScript:
        return _FinishedScript()

    monkeypatch.setattr(registry_mod, "wrap_argv", lambda argv, **k: (argv, None))
    monkeypatch.setattr(registry_mod, "cgroup_scope_argv", lambda argv: argv)
    monkeypatch.setattr(registry_mod, "create_subprocess_limited", _spawn)

    result = await registry_mod.install_from_registry(_APP)

    assert result["ok"] is True, result
    assert len(threads["app_admission_denied"]) == 3, "not every admission gate was reached"
    unreached = sorted(name for name, record in threads.items() if not record)
    assert not unreached, f"the install never reached: {unreached}"
    on_loop = sorted(name for name, record in threads.items() if loop_thread in record)
    assert not on_loop, f"install policy checks ran on the event loop thread: {on_loop}"


# Each handler reads the app's metadata before it does anything else, and
# answers 404 when the app is not installed.
_METADATA_HANDLERS = [
    ("handle_update_app", "POST", f"/api/apps/{_APP}/update"),
    ("handle_get_app", "GET", f"/api/apps/{_APP}"),
    ("handle_uninstall_preview", "GET", f"/api/apps/{_APP}/uninstall/preview"),
    ("handle_uninstall_app", "POST", f"/api/apps/{_APP}/uninstall"),
    ("handle_enable_app", "POST", f"/api/apps/{_APP}/enable"),
    ("handle_disable_app", "POST", f"/api/apps/{_APP}/disable"),
    ("handle_open_app", "POST", f"/api/apps/{_APP}/open"),
    ("handle_app_config", "GET", f"/api/apps/{_APP}/config"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler,method,path", _METADATA_HANDLERS, ids=[h for h, _, _ in _METADATA_HANDLERS]
)
async def test_route_handlers_read_the_app_metadata_off_the_loop_thread(
    monkeypatch: pytest.MonkeyPatch, handler: str, method: str, path: str
) -> None:
    """An app route must not read the installed metadata on the loop thread.

    The app is not installed, so each handler answers 404 right after that
    read.
    """
    loop_thread = threading.current_thread()
    read_threads: list[threading.Thread] = []
    monkeypatch.setattr(routes_mod, "get_app", _recorder(read_threads))

    resp = await getattr(routes_mod, handler)(
        make_mocked_request(method, path, match_info={"name": _APP})
    )

    assert resp.status == 404
    assert read_threads, "get_app was never invoked"
    assert loop_thread not in read_threads, "get_app ran on the event loop thread"


@pytest.mark.asyncio
async def test_handle_get_manifest_reads_the_manifest_off_the_loop_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/apps/{name}/manifest must not read app.json on the loop thread."""
    loop_thread = threading.current_thread()
    read_threads: list[threading.Thread] = []
    monkeypatch.setattr(routes_mod, "get_app_manifest", _recorder(read_threads))

    resp = await routes_mod.handle_get_manifest(
        make_mocked_request("GET", f"/api/apps/{_APP}/manifest", match_info={"name": _APP})
    )

    assert resp.status == 404
    assert read_threads, "get_app_manifest was never invoked"
    assert loop_thread not in read_threads, "get_app_manifest ran on the event loop thread"


@pytest.mark.asyncio
async def test_handle_app_config_touches_the_data_dir_off_the_loop_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /api/apps/{name}/config must not create the data directory or look
    for config.json on the loop thread. No config exists, so the handler seeds
    an empty one and answers ``{}``."""
    loop_thread = threading.current_thread()
    calls: list[tuple[str, threading.Thread]] = []
    data_threads: list[threading.Thread] = []
    data_dir = _recording_path_class(calls, ("is_file", "mkdir"))(tmp_path / "data")
    data_dir.mkdir()
    calls.clear()
    monkeypatch.setattr(routes_mod, "get_app", lambda name: {"name": name})
    # handle_app_config imports app_data_dir when it runs, so patch the
    # defining module.
    monkeypatch.setattr(manager_mod, "app_data_dir", _recorder(data_threads, data_dir))

    resp = await routes_mod.handle_app_config(
        make_mocked_request("GET", f"/api/apps/{_APP}/config", match_info={"name": _APP})
    )

    assert resp.status == 200
    assert data_threads, "app_data_dir was never invoked"
    assert loop_thread not in data_threads, "app_data_dir ran on the event loop thread"
    assert "is_file" in {name for name, _ in calls}, "the config file was never checked"
    on_loop = _on_loop(calls, loop_thread)
    assert not on_loop, f"the config handler touched the disk on the loop thread: {on_loop}"


@pytest.mark.asyncio
async def test_handle_app_ui_file_checks_the_file_off_the_loop_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /apps/{name}/ui/{path} must not check or resolve the file on the
    loop thread. The handler serves every asset of an app's UI."""
    loop_thread = threading.current_thread()
    calls: list[tuple[str, threading.Thread]] = []
    apps = _recording_path_class(calls, ("is_file", "resolve"))(tmp_path / "apps")
    (tmp_path / "apps" / _APP / "ui").mkdir(parents=True)
    (tmp_path / "apps" / _APP / "ui" / "app.js").write_text("export {};", encoding="utf-8")
    monkeypatch.setattr(routes_mod, "apps_dir", lambda: apps)

    resp = await routes_mod.handle_app_ui_file(
        make_mocked_request(
            "GET",
            f"/apps/{_APP}/ui/app.js",
            match_info={"name": _APP, "path": "app.js"},
        )
    )

    assert isinstance(resp, web.FileResponse)
    assert {"is_file", "resolve"} <= {name for name, _ in calls}
    on_loop = _on_loop(calls, loop_thread)
    assert not on_loop, f"the UI file handler touched the disk on the loop thread: {on_loop}"


@pytest.mark.asyncio
async def test_handle_blob_proxy_checks_the_cache_off_the_loop_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /api/apps/blob must not resolve, create or check the cache path on
    the loop thread. The blob is already cached, so no clone runs."""
    loop_thread = threading.current_thread()
    calls: list[tuple[str, threading.Thread]] = []
    clone_url = "https://example.com/acme.git"
    cache_root = _recording_path_class(calls, ("is_file", "mkdir", "resolve"))(tmp_path / "blobs")
    cached = tmp_path / "blobs" / routes_mod._blob_cache_key("acme", clone_url) / "main"
    cached.mkdir(parents=True)
    (cached / "logo.png").write_bytes(b"\x89PNG")
    entry = {"repo": "acme", "gitUrl": clone_url, "branch": "main"}
    monkeypatch.setattr(routes_mod, "get_registry_app_by_repo", lambda repo: entry)
    monkeypatch.setattr(routes_mod, "known_registry_repos", lambda: {"acme"})
    monkeypatch.setattr(routes_mod, "_blob_cache_dir", lambda: cache_root)

    resp = await routes_mod.handle_blob_proxy(
        make_mocked_request("GET", "/api/apps/blob?repo=acme&path=logo.png&ref=main")
    )

    assert isinstance(resp, web.FileResponse)
    assert {"is_file", "mkdir", "resolve"} <= {name for name, _ in calls}
    on_loop = _on_loop(calls, loop_thread)
    assert not on_loop, f"the blob proxy touched the cache on the loop thread: {on_loop}"


@pytest.mark.asyncio
async def test_fetch_git_blob_reads_the_checkout_off_the_loop_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blob fetch must not resolve or check the checkout, or create the
    cache directory, on the loop thread. A fake clone writes the blob."""
    loop_thread = threading.current_thread()
    calls: list[tuple[str, threading.Thread]] = []
    recording_path = _recording_path_class(calls, ("is_file", "mkdir", "resolve"))
    monkeypatch.setattr(routes_mod, "Path", recording_path)
    # _fetch_git_blob imports this name when it runs, so patch the defining module.
    monkeypatch.setattr(registry_mod, "is_clone_host_trusted", lambda url: True)
    monkeypatch.setattr(routes_mod, "anonymous_git_env", lambda **extra: {})
    monkeypatch.setattr(routes_mod, "wrap_argv", lambda argv, **k: (argv, None))
    monkeypatch.setattr(routes_mod, "cgroup_scope_argv", lambda argv: argv)

    class _FinishedClone:
        """A finished ``git clone`` that left the blob in its checkout."""

        returncode = 0

        def __init__(self, checkout: str) -> None:
            Path(checkout, "logo.png").write_bytes(b"\x89PNG")

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b""

    async def _spawn(*argv: Any, **kwargs: Any) -> _FinishedClone:
        return _FinishedClone(argv[-1])

    monkeypatch.setattr(routes_mod, "create_subprocess_limited", _spawn)
    cache_path = recording_path(tmp_path / "blobs" / "acme" / "main" / "logo.png")

    ok = await routes_mod._fetch_git_blob(
        "acme", "main", "logo.png", cache_path, git_url="https://example.com/acme.git"
    )

    assert ok is True
    assert (tmp_path / "blobs" / "acme" / "main" / "logo.png").read_bytes() == b"\x89PNG"
    assert {"is_file", "mkdir", "resolve"} <= {name for name, _ in calls}
    on_loop = _on_loop(calls, loop_thread)
    assert not on_loop, f"the blob fetch touched the disk on the loop thread: {on_loop}"


@pytest.mark.asyncio
async def test_handle_registries_put_reads_and_writes_the_config_off_the_loop_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PUT /api/apps/registries must not read, create or write config.json on
    the loop thread."""
    loop_thread = threading.current_thread()
    calls: list[tuple[str, threading.Thread]] = []
    write_threads: list[threading.Thread] = []
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"registries": []}), encoding="utf-8")
    monkeypatch.setattr(
        routes_mod, "Path", _recording_path_class(calls, ("is_file", "read_text", "mkdir"))
    )
    monkeypatch.setattr(routes_mod, "config_path", lambda: cfg)
    monkeypatch.setattr(routes_mod, "atomic_write", _spy(write_threads, routes_mod.atomic_write))

    resp = await routes_mod.handle_registries(
        _json_post("/api/apps/registries", {"registries": []})
    )

    assert resp.status == 200
    assert {"is_file", "read_text", "mkdir"} <= {name for name, _ in calls}
    assert write_threads, "config.json was never written"
    assert loop_thread not in write_threads, "config.json was written on the event loop thread"
    on_loop = _on_loop(calls, loop_thread)
    assert not on_loop, f"the registries handler touched config.json on the loop: {on_loop}"


@pytest.mark.asyncio
async def test_handle_uninstall_app_removes_the_workspace_off_the_loop_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/apps/{name}/uninstall must not look for or remove a registry
    app's source workspace on the loop thread."""
    loop_thread = threading.current_thread()
    calls: list[tuple[str, threading.Thread]] = []
    workspace = _recording_path_class(calls, ("is_dir",))(tmp_path / "workspace")
    workspace.mkdir()
    calls.clear()
    info = {
        "name": _APP,
        "source": f"registry:{_APP}",
        "resources": "app",
        "lifecycle": "gateway",
        "manifest": {},
    }
    monkeypatch.setattr(routes_mod, "get_app", lambda name: info)
    monkeypatch.setattr(routes_mod, "app_lifecycle_lock", lambda name: asyncio.Lock())
    monkeypatch.setattr(routes_mod, "stop_retained_startup_hooks", _no_retained_startup_hook)
    monkeypatch.setattr(routes_mod, "trust_grant_removal_blocked", lambda name: None)
    monkeypatch.setattr(
        routes_mod, "classify_and_clean_for_uninstall", lambda *a, **k: {"removable": []}
    )
    monkeypatch.setattr(routes_mod, "uninstall_app", lambda *a, **k: AppResult(ok=True, name=_APP))
    # _remove_app_workspace imports this name when it runs, so patch the
    # defining module.
    monkeypatch.setattr(registry_mod, "app_source_dir", lambda name: workspace)
    request = _json_post(f"/api/apps/{_APP}/uninstall", {})
    request.match_info.update({"name": _APP})  # type: ignore[attr-defined]

    resp = await routes_mod.handle_uninstall_app(request)

    assert resp.status == 200, resp.text
    assert not (tmp_path / "workspace").exists(), "the workspace was not removed"
    assert "is_dir" in {name for name, _ in calls}, "the workspace was never checked"
    on_loop = _on_loop(calls, loop_thread)
    assert not on_loop, f"the uninstall touched the workspace on the loop thread: {on_loop}"


def test_get_app_version_sync_cannot_erase_a_concurrent_provenance_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``get_app`` runs on the loop, without the lifecycle lock, while a registry
    install writes provenance on a worker thread. So nothing orders its read of
    ``installed.json`` against that write. This lands the write between the
    read and the manifest check, the window a write-back would use. The
    provenance must survive, and the drifted manifest version is still
    returned."""
    monkeypatch.setenv("WARDING_HOME", str(tmp_path))
    meta = manager_mod.InstalledApp(name=_APP, version="1.0.0", lifecycle="app")
    manager_mod._write_installed(_APP, meta)
    app_json = manager_mod.app_dir(_APP) / APP_MANIFEST_FILENAME
    app_json.write_text(json.dumps({"name": _APP, "version": "2.0.0"}), encoding="utf-8")
    url = f"https://example.com/{_APP}.git"
    real_from_json_file = manager_mod.AppManifest.from_json_file

    class _ProvenanceLandsMidRead(manager_mod.AppManifest):  # type: ignore[misc]
        @classmethod
        def from_json_file(cls, path: Any) -> Any:
            manager_mod.set_app_provenance(
                _APP, source=f"registry:{_APP}", url=url, commit="c" * 40
            )
            return real_from_json_file(path)

    monkeypatch.setattr(manager_mod, "AppManifest", _ProvenanceLandsMidRead)

    info = manager_mod.get_app(_APP)

    assert info is not None and info["version"] == "2.0.0", info
    stored = manager_mod._read_installed(_APP)
    assert (
        stored is not None and stored.sourceUrl == url
    ), "get_app wrote back a stale installed.json snapshot over the provenance"


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
# Cancellation: the tree copy finishes before the lifecycle lock is released
# ---------------------------------------------------------------------------


async def _assert_cancel_waits_for(
    task: asyncio.Task[Any], gate: _BlockingCall, lock: asyncio.Lock, copy: str
) -> None:
    """Cancel *task* while *gate* blocks its copy, and check that it waits.

    The task must not unwind, and so release *lock*, until the copy is done.
    It must then end with the cancellation.
    """
    try:
        assert await asyncio.to_thread(gate.started.wait, 10), f"{copy} was never called"
        task.cancel()
        await _let_cancellation_land()
        assert not task.done(), f"the task unwound while {copy} was still copying"
        assert lock.locked(), f"the lifecycle lock was released while {copy} was copying"
    finally:
        gate.release.set()
        (outcome,) = await asyncio.gather(task, return_exceptions=True)

    assert isinstance(outcome, asyncio.CancelledError), outcome


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "installed,copy",
    [(False, "install_app"), (True, "update_app")],
    ids=["new-install", "update"],
)
async def test_cancelled_registry_install_holds_the_lock_until_its_copy_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, installed: bool, copy: str
) -> None:
    """A cancelled registry install must not unwind while its tree copy runs.

    If it did, it would release the app's lifecycle lock, and a concurrent
    uninstall could remove the app during the copy. Its ``finally`` could also
    restore a moved-aside checkout while the copy still reads the checkout path.
    """
    _stub_registry_install(monkeypatch, _write_source(tmp_path / "source"), self_managed=False)
    existing = {"name": _APP} if installed else None
    monkeypatch.setattr(registry_mod, "get_app", lambda name: existing)
    _patch_registry_writes(
        monkeypatch,
        register=lambda *a, **k: AppResult(ok=True, name=_APP),
        provenance=lambda *a, **k: True,
    )
    gate = _BlockingCall(lambda *a, **k: AppResult(ok=True, name=_APP, message="copied"))
    monkeypatch.setattr(registry_mod, copy, gate)
    monkeypatch.setattr(manager_mod, "_LIFECYCLE_LOCKS", {})
    lock = manager_mod.app_lifecycle_lock(_APP)

    task = asyncio.create_task(_install_under_lock(lock))
    await _assert_cancel_waits_for(task, gate, lock, copy)


def _patch_route_lifecycle(monkeypatch: pytest.MonkeyPatch) -> asyncio.Lock:
    """Stub the route steps around the copy, and return the handler's lock.

    The startup-hook check, the resource registration, and the backend start
    and stop are not under test.
    """
    lock = asyncio.Lock()
    monkeypatch.setattr(routes_mod, "app_lifecycle_lock", lambda name: lock)
    monkeypatch.setattr(routes_mod, "stop_retained_startup_hooks", _no_retained_startup_hook)
    monkeypatch.setattr(routes_mod, "register_app", lambda name: RegistrationResult())
    monkeypatch.setattr(routes_mod, "deregister_app", lambda name: RegistrationResult())
    monkeypatch.setattr(routes_mod, "start_app_backend", lambda name: None)
    monkeypatch.setattr(routes_mod, "stop_app_backend", lambda name: None)
    return lock


@pytest.mark.asyncio
async def test_cancelled_install_request_holds_the_lock_until_its_copy_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/apps/install must not release the app's lifecycle lock while
    its copy runs, when the request is cancelled."""
    source = _write_source(tmp_path / "source")
    lock = _patch_route_lifecycle(monkeypatch)
    gate = _BlockingCall(lambda *a, **k: AppResult(ok=True, name=_APP))
    monkeypatch.setattr(routes_mod, "install_app", gate)

    task = asyncio.create_task(
        routes_mod.handle_install_app(_json_post("/api/apps/install", {"source": str(source)}))
    )
    await _assert_cancel_waits_for(task, gate, lock, "install_app")


@pytest.mark.asyncio
async def test_cancelled_update_request_holds_the_lock_until_its_copy_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/apps/{name}/update must not release the app's lifecycle lock
    while its copy runs, when the request is cancelled."""
    source = _write_source(tmp_path / "source")
    lock = _patch_route_lifecycle(monkeypatch)
    info = {"name": _APP, "lifecycle": "gateway", "enabled": True, "source": str(source)}
    monkeypatch.setattr(routes_mod, "get_app", lambda name: info)
    gate = _BlockingCall(lambda *a, **k: AppResult(ok=True, name=_APP))
    monkeypatch.setattr(routes_mod, "update_app", gate)

    request = _json_post(f"/api/apps/{_APP}/update", {"source": str(source)}, {"name": _APP})
    task = asyncio.create_task(routes_mod.handle_update_app(request))
    await _assert_cancel_waits_for(task, gate, lock, "update_app")


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


def test_no_direct_policy_check_in_install_from_registry() -> None:
    """``install_from_registry`` may not run a policy or containment check
    directly. The check names its frame, so it fails when the frame
    disappears instead of passing with nothing to scan."""
    tree = _module_tree(registry_mod)
    async_frames = {node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)}
    assert _REGISTRY_INSTALL_FRAME in async_frames, f"{_REGISTRY_INSTALL_FRAME} not found"

    offenders = _direct_calls(
        tree,
        registry_mod.__name__,
        _REGISTRY_INSTALL_POLICY_CALLS,
        frames=frozenset({_REGISTRY_INSTALL_FRAME}),
    )
    assert not offenders, "direct policy check on the event loop:\n" + "\n".join(offenders)


def test_no_direct_filesystem_call_in_routes_async_frames() -> None:
    """No async frame of ``routes.py`` may call a blocking filesystem function
    directly. The handlers that were moved off the loop must still be async
    frames, so a renamed handler cannot leave the check scanning less than it
    did."""
    tree = _module_tree(routes_mod)
    async_frames = {node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)}
    missing = sorted(_ROUTE_HANDLERS - async_frames)
    assert not missing, f"guarded handlers not found in {routes_mod.__name__}: {missing}"

    offenders = _direct_calls(tree, routes_mod.__name__, _ROUTE_FILESYSTEM_CALLS)
    assert not offenders, "direct filesystem call on the event loop:\n" + "\n".join(offenders)
