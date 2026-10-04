"""Probe results share one serialized transaction across harnesses and instances."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest

from junction import atomic_write, platform_compat
from junction.harness_router import connect


def _result(harness: str) -> connect.ProbeResult:
    return connect.ProbeResult(
        harness=harness,
        status=connect.STATUS_CONNECTED,
        models=1,
        checked_at=1_800_000_000.0,
        advertised=(connect.AdvertisedModel(f"{harness}/own-model", f"{harness} model"),),
    )


def test_concurrent_store_instances_retain_each_harness_and_its_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "routing"
    initial = _result("grok")
    connect.ProbeStore(directory).save(initial)
    contenders = threading.Barrier(2, timeout=10)
    held = threading.local()
    locks: list[os.stat_result] = []
    real_lock = platform_compat.file_lock
    real_load = connect.ProbeStore.load
    real_write = atomic_write.atomic_write

    @contextmanager
    def contended_lock(fd: int, *, exclusive: bool = True) -> Iterator[None]:
        assert exclusive
        locks.append(os.fstat(fd))
        contenders.wait()
        with real_lock(fd, exclusive=exclusive):
            held.active = True
            try:
                yield
            finally:
                held.active = False

    def load_locked(store: connect.ProbeStore) -> dict[str, connect.ProbeResult]:
        assert getattr(held, "active", False), "read must be inside the file lock"
        return real_load(store)

    def write_locked(path: Path, content: str, *, mode: int) -> None:
        assert getattr(held, "active", False), "replace must be inside the file lock"
        assert mode == 0o600
        real_write(path, content, mode=mode)

    with monkeypatch.context() as patch:
        patch.setattr(platform_compat, "file_lock", contended_lock)
        patch.setattr(connect.ProbeStore, "load", load_locked)
        patch.setattr(atomic_write, "atomic_write", write_locked)
        results = [_result("codex"), _result("opencode")]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(connect.ProbeStore(directory).save, result) for result in results
            ]
            for future in futures:
                future.result(timeout=15)

    assert len(locks) == 2
    lock_stat = (directory / connect.PROBES_LOCK_FILENAME).stat()
    data_stat = (directory / connect.PROBES_FILENAME).stat()
    assert all(os.path.samestat(lock, lock_stat) for lock in locks)
    assert not os.path.samestat(lock_stat, data_stat)
    stored = connect.ProbeStore(directory).load()
    assert stored == {result.harness: result for result in [initial, *results]}


def test_failed_replace_releases_lock_and_descriptor_without_losing_previous_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = connect.ProbeStore(tmp_path)
    original = _result("codex")
    store.save(original)
    descriptors: list[int] = []
    real_lock = platform_compat.file_lock

    @contextmanager
    def observe_lock(fd: int, *, exclusive: bool = True) -> Iterator[None]:
        descriptors.append(fd)
        with real_lock(fd, exclusive=exclusive):
            yield

    def fail_write(path: Path, content: str, *, mode: int) -> None:
        raise OSError("simulated replacement failure")

    with monkeypatch.context() as patch:
        patch.setattr(platform_compat, "file_lock", observe_lock)
        patch.setattr(atomic_write, "atomic_write", fail_write)
        with pytest.raises(OSError, match="simulated replacement failure"):
            store.save(_result("opencode"))

    assert len(descriptors) == 1
    with pytest.raises(OSError):
        os.fstat(descriptors[0])
    assert store.load() == {"codex": original}
    store.save(_result("opencode"))
    assert set(store.load()) == {"codex", "opencode"}


def test_failed_lock_does_not_read_or_replace_the_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = connect.ProbeStore(tmp_path)
    original = _result("codex")
    store.save(original)
    descriptors: list[int] = []

    @contextmanager
    def refuse_lock(fd: int, *, exclusive: bool = True) -> Iterator[None]:
        descriptors.append(fd)
        raise OSError("simulated lock failure")
        yield  # pragma: no cover

    def unexpected_read(store: connect.ProbeStore) -> dict[str, connect.ProbeResult]:
        pytest.fail("a failed lock must not enter the transaction")

    with monkeypatch.context() as patch:
        patch.setattr(platform_compat, "file_lock", refuse_lock)
        patch.setattr(connect.ProbeStore, "load", unexpected_read)
        with pytest.raises(OSError, match="simulated lock failure"):
            store.save(_result("opencode"))

    assert len(descriptors) == 1
    with pytest.raises(OSError):
        os.fstat(descriptors[0])
    assert store.load() == {"codex": original}


@pytest.mark.parametrize("contents", [None, "{bad json", "[]"])
def test_missing_or_corrupt_store_recovers_under_the_same_lock(
    tmp_path: Path, contents: str | None
) -> None:
    directory = tmp_path / "new-routing"
    if contents is not None:
        directory.mkdir()
        (directory / connect.PROBES_FILENAME).write_text(contents, encoding="utf-8")
    result = _result("opencode")
    store = connect.ProbeStore(directory)
    store.save(result)
    assert store.load() == {"opencode": result}
    raw = json.loads((directory / connect.PROBES_FILENAME).read_text(encoding="utf-8"))
    assert raw == {"opencode": result.to_dict()}


def test_updating_one_harness_retains_other_harnesses(tmp_path: Path) -> None:
    store = connect.ProbeStore(tmp_path)
    store.save(_result("codex"))
    store.save(_result("opencode"))
    latest = connect.ProbeResult(
        harness="codex", status=connect.STATUS_NEEDS_LOGIN, checked_at=1_800_000_100.0
    )
    store.save(latest)
    assert store.load() == {"codex": latest, "opencode": _result("opencode")}
