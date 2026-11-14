"""The strict JSON store primitives, and the stores that use them.

A store file that cannot be read must survive: it reads as unreadable (never as
empty), a copy of bad bytes is kept once, and a write is refused with a clear
error. Only a missing file is an empty store.
"""

from __future__ import annotations

import json
import multiprocessing
import os
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from warding import atomic_write as aw
from warding.atomic_write import (
    NO_CHANGE,
    StoreUnreadableError,
    append_line,
    load_json_store,
    locked_update,
)


def _copies(path: Path) -> list[Path]:
    return sorted(path.parent.glob(path.name + ".corrupt-*"))


# ── load_json_store ──────────────────────────────────────────────────────────


class TestLoadJsonStore:
    def test_missing_file_is_absent_with_the_default(self, tmp_path):
        got = load_json_store(tmp_path / "s.json", default={"a": 1})
        assert (got.status, got.data) == ("absent", {"a": 1})
        assert got.error() is None

    def test_valid_file_is_ok(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text('{"a": 1}', encoding="utf-8")
        got = load_json_store(p, expect=dict)
        assert (got.status, got.data) == ("ok", {"a": 1})

    def test_byte_order_mark_is_not_damage(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_bytes(b"\xef\xbb\xbf" + b'{"a": 1}')
        assert load_json_store(p, expect=dict).data == {"a": 1}
        assert _copies(p) == []

    def test_bad_json_is_unreadable_and_copied_once(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_bytes(b'{"a": ')
        first = load_json_store(p, expect=dict)
        second = load_json_store(p, expect=dict)
        assert first.unreadable and second.unreadable
        assert p.read_bytes() == b'{"a": '
        copies = _copies(p)
        assert len(copies) == 1
        assert copies[0].read_bytes() == b'{"a": '
        assert first.preserved == copies[0] == second.preserved
        assert str(p) in str(first.error())

    def test_non_utf8_and_wrong_top_level_are_unreadable(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_bytes(b"\xff\xfe\x00")
        assert load_json_store(p).unreadable
        p.write_text("[1, 2]", encoding="utf-8")
        assert load_json_store(p, expect=dict).unreadable

    def test_read_error_is_unreadable_and_makes_no_copy(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text("{}", encoding="utf-8")
        with patch.object(aw, "read_bytes_with_retry", side_effect=PermissionError(13, "denied")):
            got = load_json_store(p, expect=dict)
        assert got.unreadable
        assert _copies(p) == []
        with pytest.raises(StoreUnreadableError):
            got.require_writable()

    def test_corrupt_copy_is_owner_only(self, tmp_path):
        if os.name != "posix":
            pytest.skip("POSIX permission bits")
        p = tmp_path / "s.json"
        p.write_bytes(b"{")
        load_json_store(p)
        assert _copies(p)[0].stat().st_mode & 0o077 == 0


# ── locked_update ────────────────────────────────────────────────────────────


def _bump(path: str, key: str, n: int) -> None:
    for _ in range(n):
        locked_update(path, lambda d: {**d, key: d.get(key, 0) + 1}, default={}, expect=dict)


class TestLockedUpdate:
    def test_creates_from_default_and_persists(self, tmp_path):
        p = tmp_path / "s.json"
        default: dict = {}
        locked_update(p, lambda d: {**d, "a": 1}, default=default)
        assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1}
        assert default == {}

    def test_no_change_skips_the_write(self, tmp_path):
        p = tmp_path / "s.json"
        locked_update(p, lambda d: NO_CHANGE, default={})
        assert not p.exists()

    def test_must_exist_refuses_to_create(self, tmp_path):
        p = tmp_path / "gone" / "s.json"
        with pytest.raises(FileNotFoundError):
            locked_update(p, lambda d: d, must_exist=True)
        assert not p.parent.exists()

    @pytest.mark.parametrize(
        "content", [b"{broken", b"\xff\xfe", b"[]"], ids=["bad-json", "bad-utf8", "wrong-type"]
    )
    def test_unreadable_store_is_never_written(self, tmp_path, content):
        p = tmp_path / "s.json"
        p.write_bytes(content)
        with pytest.raises(StoreUnreadableError) as err:
            locked_update(p, lambda d: {**d, "a": 1}, default={}, expect=dict)
        assert str(p) in str(err.value)
        assert p.read_bytes() == content

    def test_threads_both_persist(self, tmp_path):
        p = str(tmp_path / "s.json")
        threads = [threading.Thread(target=_bump, args=(p, f"k{i}", 20)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert json.loads(Path(p).read_text(encoding="utf-8")) == {f"k{i}": 20 for i in range(4)}

    @pytest.mark.skipif(os.name != "posix", reason="fork start method")
    def test_processes_both_persist(self, tmp_path):
        p = str(tmp_path / "s.json")
        ctx = multiprocessing.get_context("fork")
        procs = [ctx.Process(target=_bump, args=(p, f"k{i}", 15)) for i in range(3)]
        for proc in procs:
            proc.start()
        for proc in procs:
            proc.join(timeout=60)
            assert proc.exitcode == 0
        assert json.loads(Path(p).read_text(encoding="utf-8")) == {f"k{i}": 15 for i in range(3)}


# ── append_line ──────────────────────────────────────────────────────────────


class TestAppendLine:
    def test_appends_lines(self, tmp_path):
        p = tmp_path / "log.jsonl"
        append_line(p, '{"a": 1}')
        append_line(p, '{"a": 2}')
        assert p.read_text(encoding="utf-8") == '{"a": 1}\n{"a": 2}\n'

    def test_starts_a_new_line_after_a_torn_tail(self, tmp_path):
        p = tmp_path / "log.jsonl"
        p.write_bytes(b'{"a": 1}\n{"a"')
        append_line(p, '{"a": 3}')
        assert p.read_bytes() == b'{"a": 1}\n{"a"\n{"a": 3}\n'

    def test_failed_write_truncates_back(self, tmp_path):
        p = tmp_path / "log.jsonl"
        p.write_bytes(b'{"a": 1}\n{"a"')

        def half_write(fd, data, path):
            os.write(fd, data[: len(data) // 2])
            raise OSError(28, "No space left on device")

        with patch.object(aw, "_write_all", half_write):
            with pytest.raises(OSError):
                append_line(p, '{"a": 2}')
        assert p.read_bytes() == b'{"a": 1}\n{"a"'

    def test_rejects_a_line_break(self, tmp_path):
        with pytest.raises(ValueError):
            append_line(tmp_path / "log", "a\nb")


# ── the stores ───────────────────────────────────────────────────────────────

BAD_BYTES = b'{"sessions": [1, 2'


class TestSessionMap:
    def test_unreadable_map_survives_a_write(self, tmp_path):
        from warding.session_map import SessionMap

        (tmp_path / "session_map.json").write_bytes(BAD_BYTES)
        with patch("warding.session_map.config_dir", return_value=tmp_path):
            sm = SessionMap()
            with pytest.raises(StoreUnreadableError):
                sm.set("dashboard:one", "sid-1")
            with pytest.raises(StoreUnreadableError):
                sm.flush()
        assert (tmp_path / "session_map.json").read_bytes() == BAD_BYTES
        assert _copies(tmp_path / "session_map.json")

    def test_map_with_a_byte_order_mark_loads(self, tmp_path):
        from warding.session_map import SessionMap

        (tmp_path / "session_map.json").write_bytes(
            b"\xef\xbb\xbf" + json.dumps({"dashboard:one": {"sid": "sid-1"}}).encode()
        )
        with patch("warding.session_map.config_dir", return_value=tmp_path):
            assert SessionMap().has_hint("dashboard:one")


class TestCronStore:
    def test_unreadable_store_survives_a_save(self, tmp_path):
        from warding.cron import CronService

        store = tmp_path / "crons.json"
        store.write_bytes(BAD_BYTES)
        svc = CronService(base_dir=tmp_path)
        with pytest.raises(StoreUnreadableError):
            svc._save()
        assert store.read_bytes() == BAD_BYTES
        assert _copies(store)

    def test_store_with_a_byte_order_mark_loads(self, tmp_path):
        from warding.cron import CronService

        job = {
            "id": "a",
            "name": "n",
            "message": "m",
            "schedule": {"kind": "every", "every_secs": 60},
        }
        (tmp_path / "crons.json").write_bytes(
            b"\xef\xbb\xbf" + json.dumps({"version": 2, "jobs": [job]}).encode()
        )
        assert [j.id for j in CronService(base_dir=tmp_path)._jobs] == ["a"]

    def test_store_that_is_fixed_by_the_operator_saves_again(self, tmp_path):
        from warding.cron import CronService

        store = tmp_path / "crons.json"
        store.write_bytes(BAD_BYTES)
        svc = CronService(base_dir=tmp_path)
        store.write_text(json.dumps({"version": 2, "jobs": []}), encoding="utf-8")
        svc._load()
        svc._save()
        assert json.loads(store.read_text(encoding="utf-8"))["jobs"] == []


class TestUpdateState:
    def test_unreadable_state_is_kept_and_reported(self, tmp_path, monkeypatch):
        from warding import subagent_persistence as sp

        monkeypatch.setenv("WARDING_HOME", str(tmp_path))
        agent_dir = sp._agent_dir("agent1")
        agent_dir.mkdir(parents=True)
        (agent_dir / "state.json").write_bytes(BAD_BYTES)
        assert sp.update_state("agent1", status="done") is False
        assert (agent_dir / "state.json").read_bytes() == BAD_BYTES

    def test_missing_state_is_not_recreated(self, tmp_path, monkeypatch):
        from warding import subagent_persistence as sp

        monkeypatch.setenv("WARDING_HOME", str(tmp_path))
        assert sp.update_state("never-made", status="done") is False
        assert not sp._agent_dir("never-made").exists()


class TestDependencyLedger:
    def test_unreadable_ledger_survives_an_install_record(self, tmp_path, monkeypatch):
        from warding.apps import dependency_ledger as dl

        monkeypatch.setenv("WARDING_HOME", str(tmp_path))
        path = dl._ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(BAD_BYTES)
        with pytest.raises(StoreUnreadableError):
            dl.record_install("npm:foo", "app", "npm")
        assert path.read_bytes() == BAD_BYTES


class TestMcpJson:
    def test_unreadable_mcp_json_survives_a_toggle(self, tmp_path, monkeypatch):
        from warding.dashboard.handlers import mcp as handler

        monkeypatch.setenv("WARDING_HOME", str(tmp_path))
        path = handler._warding_mcp_json()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(BAD_BYTES)
        with pytest.raises(StoreUnreadableError):
            handler._set_warding_entry("srv", enabled=False, spec={"command": "x"})
        assert path.read_bytes() == BAD_BYTES

    def test_mcp_json_with_a_byte_order_mark_keeps_its_servers(self, tmp_path, monkeypatch):
        from warding.dashboard.handlers import mcp as handler

        monkeypatch.setenv("WARDING_HOME", str(tmp_path))
        path = handler._warding_mcp_json()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            b"\xef\xbb\xbf" + json.dumps({"mcpServers": {"keep": {"command": "k"}}}).encode()
        )
        handler._set_warding_entry("srv", enabled=False, spec={"command": "x"})
        servers = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]
        assert set(servers) == {"keep", "srv"}
