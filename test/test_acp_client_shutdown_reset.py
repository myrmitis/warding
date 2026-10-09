"""``AcpClient.shutdown()`` must reset its state even when the kill fails.

``shutdown`` awaited ``_kill_process(force=True)`` and then called
``_reset_state()`` sequentially, so any exception out of the kill skipped the
reset entirely.

``_kill_process`` has several exits: four ``run_in_executor`` awaits (child
scan, record capture, escaped-child sweep) that are not individually guarded,
``subprocess_executor()`` refusing new work once the loop is tearing down, and
``asyncio.CancelledError`` -- a ``BaseException`` -- arriving mid-await, which
is precisely what a shutdown produces.

Nothing retries. Every caller treats ``shutdown`` as terminal and drops the
client right after: ``AcpWorker`` (``knowledge/llm_pool.py``) and
``_shutdown_quietly`` (``connections/mint.py``) both ``except Exception``, log,
and set their reference to ``None``. So a skipped reset is permanent.

The effect asserted here is the one with a security shape: for the claude
backend ``_reset_state`` reverts the ``.claude/settings.local.json`` that the
session's settings seed wrote, which exists only to carry ``bypassPermissions``
for the live session. The same file is also the USER's own per-project Claude
Code config, so the second half of this module pins the other direction: a file
this client never wrote is never touched. These tests use a real work directory
and a real file rather than asserting a mock was called.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from warding.acp.client import ACP_BACKEND_CLAUDE, AcpClient

_SEEDED = '{"permissions": {"defaultMode": "bypassPermissions"}}'
_USERS = '{"permissions": {"allow": ["Bash(git status)"]}}'


def _bare_client(tmp_path):
    """A claude-backend client with no live child, and the file's path."""
    client = AcpClient(work_dir=tmp_path)
    # `_is_claude` is a read-only property over the backend seam.
    client._acp_backend = ACP_BACKEND_CLAUDE
    # No live child: the reset's PID bookkeeping is not what these pin.
    client._process = None
    client._pid = None
    client._child_pids = {}
    return client, tmp_path / ".claude" / "settings.local.json"


def _attach_seed(client, settings, content=_SEEDED):
    """Stand in for the edition's ``_write_claude_local_settings`` hook."""

    def _seed():
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(content, encoding="utf-8")

    client._write_claude_local_settings = _seed  # type: ignore[attr-defined]


def _claude_client(tmp_path):
    """A client whose reset has one plainly observable effect on disk: the seed
    has run, so the file on disk is one this client wrote."""
    client, settings = _bare_client(tmp_path)
    _attach_seed(client, settings)
    client._seed_claude_local_settings("seed failed")
    assert settings.read_text(encoding="utf-8") == _SEEDED
    return client, settings


@pytest.mark.asyncio
async def test_a_cancelled_kill_still_resets_the_client(tmp_path):
    """Cancellation is the shutdown case, and it must not skip the reset."""
    client, settings = _claude_client(tmp_path)
    client._kill_process = AsyncMock(side_effect=asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        await client.shutdown()

    assert not settings.exists(), (
        "settings.local.json outlived the session it granted bypassPermissions "
        "for; no caller retries shutdown, so nothing else removes it"
    )
    assert client._session_id is None


@pytest.mark.asyncio
async def test_a_failing_kill_still_resets_the_client(tmp_path):
    """The executor refusing work during teardown looks like this."""
    client, settings = _claude_client(tmp_path)
    client._kill_process = AsyncMock(
        side_effect=RuntimeError("cannot schedule new futures after shutdown")
    )

    with pytest.raises(RuntimeError):
        await client.shutdown()

    assert not settings.exists()
    assert client._session_id is None


@pytest.mark.asyncio
async def test_a_clean_shutdown_still_resets(tmp_path):
    """Control: the path that already worked must keep working."""
    client, settings = _claude_client(tmp_path)
    client._kill_process = AsyncMock()

    await client.shutdown()

    assert not settings.exists()
    assert client._session_id is None


# ── A file this client did not write is not this client's to delete ──


@pytest.mark.asyncio
async def test_shutdown_keeps_the_users_own_settings_local_json(tmp_path):
    """The defect: every claude session shutdown unlinked the user's own
    ``<project>/.claude/settings.local.json`` -- their personal, usually
    version-control-ignored allow rules -- with no backup and no log. The public
    core never seeds the file, so it has nothing to undo."""
    client, settings = _bare_client(tmp_path)
    settings.parent.mkdir(parents=True)
    settings.write_text(_USERS, encoding="utf-8")
    client._kill_process = AsyncMock()

    await client.shutdown()

    assert settings.read_text(encoding="utf-8") == _USERS


def test_reset_state_alone_keeps_the_users_file(tmp_path):
    """``_reset_state`` runs on every failed-init retry too, not only shutdown."""
    client, settings = _bare_client(tmp_path)
    settings.parent.mkdir(parents=True)
    settings.write_text(_USERS, encoding="utf-8")

    client._reset_state()
    client._reset_state()

    assert settings.read_text(encoding="utf-8") == _USERS


def test_a_seed_that_overwrote_the_users_file_is_reverted_not_deleted(tmp_path):
    """The seed may land on top of a file the user already had. Undoing it must give
    the user's bytes back, not leave them with a deletion."""
    client, settings = _bare_client(tmp_path)
    settings.parent.mkdir(parents=True)
    settings.write_text(_USERS, encoding="utf-8")
    _attach_seed(client, settings)
    client._seed_claude_local_settings("seed failed")
    assert settings.read_text(encoding="utf-8") == _SEEDED

    client._reset_state()

    assert settings.read_text(encoding="utf-8") == _USERS


def test_a_seeded_file_the_user_edited_since_is_left_alone(tmp_path):
    """The record is a hash of what the seed left, so an edit made during the
    session makes the file the user's again."""
    client, settings = _claude_client(tmp_path)
    settings.write_text(_USERS, encoding="utf-8")

    client._reset_state()

    assert settings.read_text(encoding="utf-8") == _USERS


def test_a_reseed_restores_the_original_not_the_previous_seed(tmp_path):
    """The substitution retry re-seeds on the same client. What to restore is what
    was there before the FIRST seed."""
    client, settings = _bare_client(tmp_path)
    settings.parent.mkdir(parents=True)
    settings.write_text(_USERS, encoding="utf-8")
    _attach_seed(client, settings, content=_SEEDED)
    client._seed_claude_local_settings("seed failed")
    _attach_seed(client, settings, content='{"model": "substitute"}')
    client._seed_claude_local_settings("re-seed failed")

    client._reset_state()

    assert settings.read_text(encoding="utf-8") == _USERS


def test_a_reseed_keeps_an_edit_the_user_made_between_the_seeds(tmp_path):
    """Only a file still holding the previous seed's bytes goes back to the original.
    One the user rewrote in between is theirs, and restoring the pre-session bytes would
    discard that edit."""
    client, settings = _bare_client(tmp_path)
    settings.parent.mkdir(parents=True)
    settings.write_text(_USERS, encoding="utf-8")
    _attach_seed(client, settings, content=_SEEDED)
    client._seed_claude_local_settings("seed failed")
    edited = '{"permissions": {"allow": ["Bash(git diff)"]}}'
    settings.write_text(edited, encoding="utf-8")
    _attach_seed(client, settings, content='{"model": "substitute"}')
    client._seed_claude_local_settings("re-seed failed")

    client._reset_state()

    assert settings.read_text(encoding="utf-8") == edited


def test_a_reseed_after_the_user_deleted_the_file_deletes_it_again(tmp_path):
    client, settings = _bare_client(tmp_path)
    settings.parent.mkdir(parents=True)
    settings.write_text(_USERS, encoding="utf-8")
    _attach_seed(client, settings, content=_SEEDED)
    client._seed_claude_local_settings("seed failed")
    settings.unlink()
    _attach_seed(client, settings, content='{"model": "substitute"}')
    client._seed_claude_local_settings("re-seed failed")

    client._reset_state()

    assert not settings.exists()


def test_a_seed_that_fails_after_writing_is_still_undone(tmp_path):
    """A seed that raised halfway may already have changed the file; an unrecorded
    change could never be undone."""
    client, settings = _bare_client(tmp_path)

    def _seed():
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(_SEEDED, encoding="utf-8")
        raise OSError("disk full while writing the allowlist")

    client._write_claude_local_settings = _seed  # type: ignore[attr-defined]
    client._seed_claude_local_settings("seed failed")
    assert settings.exists()

    client._reset_state()

    assert not settings.exists()


def test_a_seed_that_changes_nothing_records_nothing(tmp_path):
    """Writing identical bytes over the user's file is not a change to undo."""
    client, settings = _bare_client(tmp_path)
    settings.parent.mkdir(parents=True)
    settings.write_text(_SEEDED, encoding="utf-8")
    _attach_seed(client, settings, content=_SEEDED)
    client._seed_claude_local_settings("seed failed")

    client._reset_state()

    assert settings.read_text(encoding="utf-8") == _SEEDED


def test_the_record_does_not_outlive_the_reset(tmp_path):
    """A second reset must not act on the first session's record: the file may have
    been recreated by the user in between."""
    client, settings = _claude_client(tmp_path)
    client._reset_state()
    assert not settings.exists()
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(_SEEDED, encoding="utf-8")

    client._reset_state()

    assert settings.read_text(encoding="utf-8") == _SEEDED
