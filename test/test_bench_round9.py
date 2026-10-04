"""Four bench defects, covered as enforcement points where a rule was
missing one, and as ordinary fixes where the defect was one-off.

Two are the recurring class, and each shows *where* an enforcement point must sit:

* `_measurable_count` guards leaf VALUES, so nested OBJECT access needs a reader for
  the containers too (`_section`) or `{"corpus": null}` still crashes;
* the "every refusal needs a catch site" rule needs an enforcement point rather than
  a per-command habit, or `bench fetch` lets `UnsafePathError` escape -- the right
  shape is inheritance (`BenchRefusal`) rather than a tuple of types to keep in sync.

The other two are separate classes: an open store leaking out of a raising ingest, and
the comparison's compatibility claim omitting the environment it was measured in.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import yaml

from junction.eval.bench.corpus import BenchInstance, BenchSession, BenchTurn
from junction.eval.bench.datasets import CorpusFetchError
from junction.eval.bench.errors import BenchRefusal
from junction.eval.bench.ingest import IngestConfig, IngestError, ingest_instance
from junction.eval.bench.retrieval import RetrievalNotMeasurable
from junction.eval.bench.run import compare_reports
from junction.eval.bench.safepath import UnsafePathError

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "memory-benchmark.yml"


def _refused(out: str) -> bool:
    """True when the comparison declined to publish a delta.

    Two headers exist -- `## Not comparable` for a whole-report mismatch and
    `## session-level @k — not comparable` for a single cut-off -- so a
    case-sensitive substring check silently only covers one of them.
    """
    return "not comparable" in out.lower()


def _instance() -> BenchInstance:
    return BenchInstance(
        instance_id="r9",
        sessions=(
            BenchSession(
                "s1",
                (
                    BenchTurn(turn_id="t1", session_id="s1", speaker="A", text="malta lessons"),
                    BenchTurn(turn_id="t2", session_id="s1", speaker="B", text="espresso row"),
                ),
                "2023/04/10 (Mon) 23:07",
            ),
        ),
        queries=(),
    )


# ── Every deliberate refusal is catchable by one name ────────────────────────


@pytest.mark.parametrize(
    "refusal",
    [UnsafePathError, CorpusFetchError, IngestError, RetrievalNotMeasurable],
)
def test_every_refusal_type_inherits_the_one_base(refusal: type) -> None:
    """Inheritance is the enforcement point; a tuple would be a list to forget.

    `bench fetch` caught `CorpusFetchError` and let `UnsafePathError` escape as a
    traceback from the same command, because the rule lived in each handler by hand.
    """
    assert issubclass(refusal, BenchRefusal)
    # Still a RuntimeError, so existing callers and `except RuntimeError` keep working.
    assert issubclass(refusal, RuntimeError)


def test_the_dispatch_reports_a_refusal_instead_of_raising(monkeypatch) -> None:
    """Any subcommand: the floor is the dispatch, not the handler."""
    from junction import cli_bench

    def refuse(*_a: object, **_k: object):
        raise UnsafePathError("refusing to use that cache directory: protected location")

    monkeypatch.setattr("junction.eval.bench.datasets.ensure", refuse)
    args = argparse.Namespace(bench_action="fetch", corpus="locomo10")

    rc = cli_bench.bench_cmd(args)
    assert rc == 1, "a refusal must be a non-zero exit, not an exception"

    # And the inner dispatch still raises -- proving the wrapper is what converts it,
    # so this test fails if the wrapper is removed.
    with pytest.raises(UnsafePathError):
        cli_bench._bench_dispatch(args)


def test_a_new_refusal_type_needs_no_cli_change() -> None:
    """The property that makes this an enforcement point rather than a fix."""
    from junction import cli_bench

    class FutureRefusal(BenchRefusal):
        pass

    def refuse(*_a: object, **_k: object):
        raise FutureRefusal("a refusal invented after the CLI was written")

    import junction.eval.bench.datasets as datasets_mod

    original = datasets_mod.ensure
    datasets_mod.ensure = refuse  # type: ignore[assignment]
    try:
        rc = cli_bench.bench_cmd(argparse.Namespace(bench_action="fetch", corpus="locomo10"))
    finally:
        datasets_mod.ensure = original  # type: ignore[assignment]
    assert rc == 1


# ── A raising ingest must not leak the open store ───────────────────────────


def test_a_failed_ingest_closes_the_store(tmp_path: Path) -> None:
    """Otherwise the caller's TemporaryDirectory cleanup raises on the open sqlite
    file — on Windows that MASKS the refusal, which is the diagnostic's whole job."""
    calls = {"n": 0}

    def flaky(text: str):
        calls["n"] += 1
        return [0.1, 0.2] if calls["n"] <= 2 else None

    with pytest.raises(IngestError):
        ingest_instance(
            _instance(),
            db_path=tmp_path / "leak.db",
            embed_fn=flaky,
            config=IngestConfig(granularity="turn", timeline="now"),
        )

    # The observable consequence of a leaked handle: the directory cannot be cleared.
    # On POSIX unlink succeeds regardless, so assert on the sqlite side-files that a
    # still-open connection leaves behind instead.
    leftovers = sorted(p.name for p in tmp_path.iterdir())
    assert "leak.db-wal" not in leftovers and "leak.db-shm" not in leftovers, (
        f"the store was left open: {leftovers}"
    )


def test_a_successful_ingest_still_hands_the_store_to_the_caller(tmp_path: Path) -> None:
    """Ownership transfers on the successful return; the guard must not close it."""
    loaded = ingest_instance(
        _instance(),
        db_path=tmp_path / "ok.db",
        embed_fn=lambda _t: [0.1, 0.2],
        config=IngestConfig(granularity="turn", timeline="now"),
    )
    try:
        assert loaded.report.written == 2
        # Usable, i.e. not closed underneath us.
        assert loaded.store.search_episodic(query_embedding=[0.1, 0.2], query_text="malta") == [] or True
    finally:
        loaded.close()


# ── Malformed nested objects refuse instead of crashing ─────────────────────


def _report(**overrides: object) -> dict:
    base: dict = {
        "corpus": {"fingerprint": "f" * 64},
        "config": {
            "ingest": {"granularity": "turn", "timeline": "now"},
            "retrieval": {"limit": 20, "mmr": True},
            "search_backend": "sqlite_cosine",
            "embedder": "qwen3-embedding:0.6b@1024",
            "environment": {"python": "3.12.10", "platform": "linux-x86_64"},
        },
        "metrics": {
            "session": {"recall_all@5": 0.5},
            "session_measurable": {"5": 1977},
            "session_population": {"5": "a" * 64},
        },
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "broken",
    [
        {"corpus": None},
        {"config": None},
        {"metrics": None},
        {"corpus": "not a dict"},
        {"metrics": []},
        {"metrics": {"session": None}},
    ],
)
def test_a_malformed_report_section_refuses_instead_of_crashing(broken: dict) -> None:
    """`.get("corpus", {})` defaults only for a MISSING key, not a present null."""
    out = compare_reports(_report(**broken), _report(), k=5)
    assert _refused(out)


def test_a_well_formed_pair_still_compares() -> None:
    """The suite must not be able to pass by refusing everything."""
    out = compare_reports(_report(), _report(), k=5)
    assert not _refused(out)


# ── The environment is part of the comparability claim ─────────────────────


def test_a_changed_environment_refuses() -> None:
    """A runner or dependency bump must not be published as a code delta."""
    baseline = _report()
    candidate = _report()
    candidate["config"]["environment"] = {"python": "3.13.1", "platform": "linux-x86_64"}
    out = compare_reports(baseline, candidate, k=5)
    assert _refused(out)
    assert "environment" in out


def test_the_environment_identity_records_what_can_move_a_number() -> None:
    from junction.eval.bench.run import _environment_identity

    identity = _environment_identity()
    assert set(identity) == {"python", "platform", "sqlite", "numpy"}
    assert all(isinstance(v, str) and v for v in identity.values())


def test_the_measuring_job_pins_its_runner() -> None:
    """`ubuntu-latest` on a lane that produces comparable numbers means a silent
    image bump reads as a code change."""
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert doc["jobs"]["measure"]["runs-on"] == "ubuntu-24.04"
