"""The meetings agents must be named the way they can actually be dispatched.

Regression cover for a bug that made the app's whole agent half a no-op: every
`meeting_agents` entry asked for `meetings/meetings-<agent>`, and every dispatch
came back `Mode 'meetings/meetings-note-taker' not found`, so no note-taker,
sketch-artist or task-extractor ever ran. Transcription, the dictionary, the noise
gate and the queues all worked — the agent simply never started.

The namespaced form is a display / tracking id. What can be dispatched is the
agent's DECLARED name (its `name` field), because that is what kiro-cli
enumerates and what `bridges._register_agents` publishes through
`publish_materialized_agents`. `bridges` says so at the call site:

    # The DECLARED name only — kiro-cli enumerates agents by their
    # `name` field, so the namespaced filename stem is not a name it
    # can resolve (see _scan_materialized_agents).
    dispatchable.add(agent_name)

Nothing here needs a gateway or a model: the assertions compare what the app asks
for against what it ships on disk, which is the pair that has to agree.
"""

from __future__ import annotations

import json
from pathlib import Path

from warding.apps.builtins.meetings.backend import constants as k
from warding.apps.builtins.meetings.backend import store

APP_ROOT = Path(k.__file__).resolve().parent.parent
AGENTS_DIR = APP_ROOT / "agents"


def _declared_names() -> set[str]:
    """The `name` of every agent JSON this app ships."""
    return {
        json.loads(p.read_text(encoding="utf-8"))["name"] for p in AGENTS_DIR.glob("*.json")
    }


def _manifest_agents() -> list[str]:
    """The agent files app.json declares, so a shipped-but-unlisted file is caught."""
    manifest = json.loads((APP_ROOT / "app.json").read_text(encoding="utf-8"))
    return list(manifest.get("agents") or [])


class TestTheAppShipsWhatItAsksFor:
    def test_the_agents_dir_is_not_empty(self):
        """Guards the two tests below from passing vacuously."""
        assert _declared_names()

    def test_every_configured_agent_is_a_declared_name(self):
        declared = _declared_names()
        for entry in store.DEFAULT_MEETING_AGENTS:
            assert entry["agent"] in declared, (
                f"{entry['id']} asks for {entry['agent']!r}, which is not the `name` of "
                f"any shipped agent. Declared: {sorted(declared)}"
            )

    def test_the_task_extractor_is_a_declared_name(self):
        """The always-on system agent is not in `meeting_agents`, so it needs its own
        assertion — and it was broken the same way."""
        assert k.TASK_EXTRACTOR_AGENT in _declared_names()

    def test_no_configured_agent_carries_the_namespace(self):
        """The specific shape of the bug: a slash makes it unresolvable.

        Kept separate from the membership test above so a future rename that
        happens to reintroduce a slash fails with the reason, not just "not found
        in the set".
        """
        refs = [e["agent"] for e in store.DEFAULT_MEETING_AGENTS] + [k.TASK_EXTRACTOR_AGENT]
        for ref in refs:
            assert "/" not in ref, (
                f"{ref!r} is the namespaced id, which kiro-cli cannot resolve — use "
                "the agent's declared `name`"
            )

    def test_every_shipped_agent_is_declared_in_the_manifest(self):
        """An agent file that app.json does not list is never registered at all,
        so it would be missing at dispatch for a completely different reason."""
        listed = {Path(p).name for p in _manifest_agents()}
        on_disk = {p.name for p in AGENTS_DIR.glob("*.json")}
        assert on_disk <= listed, f"shipped but unlisted in app.json: {sorted(on_disk - listed)}"

    def test_the_task_extractor_constant_matches_its_file(self):
        """The constant exists so two call sites cannot drift; pin it to the file."""
        path = AGENTS_DIR / f"{k.TASK_EXTRACTOR_AGENT}.json"
        assert path.is_file(), f"no shipped agent file for {k.TASK_EXTRACTOR_AGENT!r}"
        assert json.loads(path.read_text(encoding="utf-8"))["name"] == k.TASK_EXTRACTOR_AGENT


class TestReadConfig:
    """``read_config`` returns the persisted agent list as stored."""

    @staticmethod
    def _save(root: Path, agents: object) -> None:
        (root / k.CONFIG_FILE).write_text(
            json.dumps({"meeting_agents": agents}), encoding="utf-8"
        )

    def test_a_declared_ref_is_returned_untouched(self, tmp_path):
        self._save(
            tmp_path,
            [{"id": "note-taker", "agent": "meetings-note-taker", "builtin": True}],
        )
        agents = store.read_config(tmp_path)["meeting_agents"]
        assert agents[0]["agent"] == "meetings-note-taker"

    def test_a_malformed_agents_list_does_not_raise(self, tmp_path):
        """read_config is on the request path; a hand-edited config must not 500."""
        self._save(tmp_path, ["not-a-dict", 7, None])
        assert store.read_config(tmp_path)["meeting_agents"] == ["not-a-dict", 7, None]

    def test_a_non_list_agents_value_does_not_raise(self, tmp_path):
        self._save(tmp_path, {"unexpected": "shape"})
        assert store.read_config(tmp_path)["meeting_agents"] == {"unexpected": "shape"}

    def test_a_fresh_install_still_gets_the_defaults(self, tmp_path):
        agents = store.read_config(tmp_path)["meeting_agents"]
        assert [a["agent"] for a in agents] == [
            a["agent"] for a in store.DEFAULT_MEETING_AGENTS
        ]
