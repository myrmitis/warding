"""Corrupt-store edge cases found in review of the strict store primitives."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web

from warding import atomic_write as aw
from warding.atomic_write import StoreUnreadableError, load_json_store, locked_update

BAD_BYTES = b'{"sessions": [1, 2'


def _copies(path: Path) -> list[Path]:
    return sorted(path.parent.glob(path.name + ".corrupt-*"))


class TestCorruptCopyCap:
    def test_only_the_newest_copies_are_kept(self, tmp_path):
        p = tmp_path / "s.json"
        for i in range(aw.CORRUPT_COPIES_KEPT + 4):
            p.write_bytes(b'{"bad": %d' % i)
            assert load_json_store(p).unreadable
        copies = _copies(p)
        assert len(copies) == aw.CORRUPT_COPIES_KEPT
        assert copies[-1].read_bytes() == b'{"bad": %d' % (aw.CORRUPT_COPIES_KEPT + 3)

    def test_the_oldest_copy_is_always_kept(self, tmp_path):
        p = tmp_path / "s.json"
        for i in range(aw.CORRUPT_COPIES_KEPT + 4):
            p.write_bytes(b'{"bad": %d' % i)
            load_json_store(p)
        assert _copies(p)[0].read_bytes() == b'{"bad": 0'


class TestSessionMapMergeOnRecovery:
    """What the operator did while the map was refused, after the file reads again."""

    @staticmethod
    def _refused_map(tmp_path, entries):
        from warding.session_map import SessionMap

        path = tmp_path / "session_map.json"
        path.write_text(json.dumps(entries), encoding="utf-8")
        with patch.object(aw, "read_bytes_with_retry", side_effect=PermissionError(13, "no")):
            sm = SessionMap()
        assert sm._store_error is not None
        return sm, path

    def test_a_binding_deleted_while_refused_stays_deleted(self, tmp_path):
        disk = {"dashboard:a": {"sid": "sid-a"}, "dashboard:b": {"sid": "sid-b"}}
        with patch("warding.session_map.config_dir", return_value=tmp_path):
            sm, path = self._refused_map(tmp_path, disk)
            sm.delete("dashboard:a")
            sm.set("dashboard:c", "sid-c")
        assert set(json.loads(path.read_text(encoding="utf-8"))) == {"dashboard:b", "dashboard:c"}

    def test_a_binding_set_then_deleted_while_refused_stays_deleted(self, tmp_path):
        disk = {"dashboard:a": {"sid": "sid-a"}}
        with patch("warding.session_map.config_dir", return_value=tmp_path):
            sm, path = self._refused_map(tmp_path, disk)
            sm.set("dashboard:a", "sid-new")
            sm.delete("dashboard:a")
            sm.set("dashboard:b", "sid-b")
        assert set(json.loads(path.read_text(encoding="utf-8"))) == {"dashboard:b"}

    def test_a_rebind_while_refused_wins_and_keeps_the_disk_fields(self, tmp_path):
        disk = {"dashboard:a": {"sid": "sid-old", "cwd": "/work", "flags": {"temporary": True}}}
        with patch("warding.session_map.config_dir", return_value=tmp_path):
            sm, path = self._refused_map(tmp_path, disk)
            sm.set("dashboard:a", "sid-new")
        saved = json.loads(path.read_text(encoding="utf-8"))["dashboard:a"]
        assert saved["sid"] == "sid-new"
        assert saved["cwd"] == "/work"
        assert saved["flags"] == {"temporary": True}

    def test_a_flag_set_while_refused_does_not_hide_the_disk_session(self, tmp_path):
        disk = {"dashboard:a": {"sid": "sid-a", "flags": {"incognito": True}}}
        with patch("warding.session_map.config_dir", return_value=tmp_path):
            sm, path = self._refused_map(tmp_path, disk)
            sm.set_flag("dashboard:a", "temporary", True)
        saved = json.loads(path.read_text(encoding="utf-8"))["dashboard:a"]
        assert saved["sid"] == "sid-a"
        assert saved["flags"] == {"incognito": True, "temporary": True}

    def test_recovery_on_a_worker_thread_reads_the_file_without_the_map_lock(self, tmp_path):
        from warding import session_map as sm_mod

        disk = {"dashboard:a": {"sid": "sid-a"}}
        held: list[bool] = []
        real = aw.read_bytes_with_retry

        def probe(path):
            held.append(sm_mod._MAP_LOCK._is_owned())  # RLock: owned by this thread?
            return real(path)

        async def scenario(sm):
            with patch.object(aw, "read_bytes_with_retry", probe):
                sm.set("dashboard:b", "sid-b")  # on a loop: the flush is deferred
                await sm.aflush()  # the write, and the recovery, run on a worker thread

        with patch("warding.session_map.config_dir", return_value=tmp_path):
            sm, path = self._refused_map(tmp_path, disk)
            asyncio.run(scenario(sm))
        assert held and not any(held)
        assert set(json.loads(path.read_text(encoding="utf-8"))) == {"dashboard:a", "dashboard:b"}


class TestSessionMapSignature:
    def test_a_good_file_that_replaces_the_bad_one_during_the_read_is_not_recorded_bad(
        self, tmp_path
    ):
        from warding.session_map import SessionMap

        path = tmp_path / "session_map.json"
        path.write_bytes(BAD_BYTES)
        real = aw.read_bytes_with_retry

        def swap_after_read(p):
            raw = real(p)
            path.write_text(json.dumps({"dashboard:a": {"sid": "sid-a"}}), encoding="utf-8")
            return raw

        with patch("warding.session_map.config_dir", return_value=tmp_path):
            with patch.object(aw, "read_bytes_with_retry", swap_after_read):
                sm = SessionMap()
            assert sm._store_error is not None
            sm.set("dashboard:b", "sid-b")  # the next write sees the changed file and recovers
        assert set(json.loads(path.read_text(encoding="utf-8"))) == {"dashboard:a", "dashboard:b"}


class TestMustExistLeavesNoLock:
    def test_missing_record_in_an_existing_directory_leaves_no_lock_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            locked_update(tmp_path / "state.json", lambda d: d, must_exist=True)
        assert list(tmp_path.iterdir()) == []


class TestUpdateStateNeverRaises:
    def test_a_lock_failure_returns_false(self, tmp_path, monkeypatch):
        from warding import subagent_persistence as sp

        monkeypatch.setenv("WARDING_HOME", str(tmp_path))
        agent_dir = sp._agent_dir("agent2")
        agent_dir.mkdir(parents=True)
        (agent_dir / "state.json").write_text("{}", encoding="utf-8")
        with patch.object(sp, "locked_update", side_effect=OSError("could not acquire lock")):
            assert sp.update_state("agent2", status="done") is False


class TestCronLoadEdges:
    def test_a_store_deleted_between_stat_and_load_reads_as_empty(self, tmp_path):
        from warding.cron import CronService

        svc = CronService(base_dir=tmp_path)
        (tmp_path / "crons.json").write_text('{"version": 2, "jobs": []}', encoding="utf-8")
        gone = aw.StoreLoad("absent", {}, path=tmp_path / "crons.json")
        with patch("warding.cron.load_json_store", return_value=gone):
            svc._load()
        assert svc._jobs == []

    def test_a_document_without_a_jobs_list_is_not_re_read_every_tick(self, tmp_path):
        from warding.cron import CronService

        store = tmp_path / "crons.json"
        store.write_text('{"version": 2, "jobs": null}', encoding="utf-8")
        svc = CronService(base_dir=tmp_path)
        assert svc._store_error is not None
        with patch.object(svc, "_load") as reload:
            svc._sync()
        reload.assert_not_called()
        assert store.read_text(encoding="utf-8") == '{"version": 2, "jobs": null}'


class TestSessionMapRecovery:
    def test_a_transient_read_error_does_not_refuse_writes_for_good(self, tmp_path):
        from warding.session_map import SessionMap

        path = tmp_path / "session_map.json"
        path.write_text(json.dumps({"dashboard:old": {"sid": "sid-old"}}), encoding="utf-8")
        with patch("warding.session_map.config_dir", return_value=tmp_path):
            with patch.object(aw, "read_bytes_with_retry", side_effect=PermissionError(13, "no")):
                sm = SessionMap()
            assert sm._store_error is not None
            sm.set("dashboard:new", "sid-new")
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert set(saved) == {"dashboard:old", "dashboard:new"}
        assert sm._store_error is None

    def test_a_parse_failure_stays_refused_until_the_file_changes(self, tmp_path):
        from warding.session_map import SessionMap

        path = tmp_path / "session_map.json"
        path.write_bytes(BAD_BYTES)
        with patch("warding.session_map.config_dir", return_value=tmp_path):
            sm = SessionMap()
            with pytest.raises(StoreUnreadableError):
                sm.set("dashboard:one", "sid-1")
            assert path.read_bytes() == BAD_BYTES
            path.write_text(json.dumps({"dashboard:old": {"sid": "sid-old"}}), encoding="utf-8")
            sm.set("dashboard:two", "sid-2")
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert {"dashboard:old", "dashboard:two"} <= set(saved)


class TestMcpGlobalWriters:
    @pytest.fixture
    def sandbox(self, tmp_path, monkeypatch):
        from warding.dashboard.handlers import mcp as handler

        g = tmp_path / "kiro" / "mcp.json"
        g.parent.mkdir(parents=True)
        monkeypatch.setattr(handler, "_GLOBAL_MCP_JSON", g)
        monkeypatch.setattr(handler, "_MCP_LOCK_PATH", g.with_suffix(".lock"))
        monkeypatch.setattr(handler, "_WARDING_MCP_JSON", tmp_path / "home" / "mcp.json")
        monkeypatch.setattr(handler, "_extra_mcp_scopes", list)
        monkeypatch.setattr(handler, "_sync_mcp_to_agent", lambda *a, **k: None)
        monkeypatch.setattr(handler, "sel", lambda: MagicMock())
        return handler, g

    @staticmethod
    def _put(handler, name, body):
        req = MagicMock(spec=web.Request)
        req.json = AsyncMock(return_value=body)
        req.match_info = {"name": name}
        req.method = "PUT"
        req.app = {}
        req.get = lambda key, default=None: default
        return asyncio.run(handler.api_mcp_server_detail(req))

    def test_put_over_an_unreadable_global_file_leaves_it_alone(self, sandbox):
        handler, g = sandbox
        g.write_bytes(BAD_BYTES)
        resp = self._put(handler, "srv", {"command": "x"})
        assert resp.status == 500
        assert g.read_bytes() == BAD_BYTES

    def test_put_over_a_global_file_with_a_byte_order_mark_keeps_its_servers(self, sandbox):
        handler, g = sandbox
        doc = {"mcpServers": {"keep": {"command": "k"}}}
        g.write_bytes(b"\xef\xbb\xbf" + json.dumps(doc).encode())
        resp = self._put(handler, "srv", {"command": "x"})
        assert resp.status == 200
        assert set(json.loads(g.read_text(encoding="utf-8"))["mcpServers"]) == {"keep", "srv"}

    def test_removal_replies_with_a_warning_when_the_file_is_unreadable(self, sandbox):
        handler, g = sandbox
        g.write_bytes(BAD_BYTES)

        remove = MagicMock(spec=web.Request)
        remove.json = AsyncMock(return_value={"name": "srv"})
        remove.app = {}
        remove.get = lambda key, default=None: default
        resp = asyncio.run(handler.api_mcp_remove(remove))
        assert resp.status == 200
        assert json.loads(resp.body)["removed"] is False
        assert "unchanged" in json.loads(resp.body)["warning"]

        delete = MagicMock(spec=web.Request)
        delete.match_info = {"name": "srv"}
        delete.method = "DELETE"
        delete.app = {}
        delete.get = lambda key, default=None: default
        resp = asyncio.run(handler.api_mcp_server_detail(delete))
        assert resp.status == 404
        assert "unchanged" in json.loads(resp.body)["warning"]
        assert g.read_bytes() == BAD_BYTES

    def test_removal_reply_has_no_warning_for_a_readable_file(self, sandbox):
        handler, g = sandbox
        g.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
        delete = MagicMock(spec=web.Request)
        delete.match_info = {"name": "srv"}
        delete.method = "DELETE"
        delete.app = {}
        delete.get = lambda key, default=None: default
        resp = asyncio.run(handler.api_mcp_server_detail(delete))
        assert "warning" not in json.loads(resp.body)
