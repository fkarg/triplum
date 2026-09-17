"""A stage fetches on the second call, recomputes exactly when its code or its inputs change,
streams through its artifact, and asks the store about its effects."""

import importlib
import linecache
import sys
from collections.abc import Iterator
from itertools import islice
from pathlib import Path

import polars as pl
import pytest
from pydantic import BaseModel
from triplum.bench.runstore import RunStore
from triplum.stage import LiveStream, Run, Stream, active, artifacts, stage
from triplum.store.sqlite.store import SqliteStore
from triplum.utils.data import RecordDataset

HELPERS = """
FACTOR = 2


def scale(x):
    return x * FACTOR
"""


class Item(BaseModel, frozen=True):
    n: int


class Calls:
    def __init__(self):
        self.n = 0


@pytest.fixture
def helpers(tmp_path, monkeypatch):
    path = tmp_path / "stage_helpers.py"
    path.write_text(HELPERS)
    monkeypatch.setattr(sys, "dont_write_bytecode", True)  # a same-size edit in the same
    # second would otherwise be served from a stale .pyc
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("stage_helpers", None)
    mod = importlib.import_module("stage_helpers")
    yield mod, path
    sys.modules.pop("stage_helpers", None)


@pytest.fixture
def run(tmp_path):
    root = tmp_path / "cache"
    with RunStore(root / "runs.db") as rs:
        rid = rs.start_run(_meta())
        with active(Run(store=rs, root=root, run_id=rid, seed=7)) as r:
            yield r


def _meta():
    return {
        "kind": "qa",
        "dataset": "t",
        "pipeline": "p",
        "config_hash": "c",
        "config_json": "{}",
        "code_version": "v",
        "dirty": 0,
        "code_hash": "",
        "corpus_hash": "x",
        "questions_hash": "y",
        "n": 0,
        "seed": 0,
        "viewer_json": "[]",
        "host": "h",
    }


def reload_after(mod, path: Path, old: str, new: str):
    path.write_text(path.read_text().replace(old, new))
    linecache.checkcache(str(path))
    return importlib.reload(mod)


def test_second_call_fetches_and_records_the_invocation(run, helpers):
    mod, _ = helpers
    calls = Calls()

    @stage
    def double(items: RecordDataset[Item], cfg: int) -> pl.DataFrame:
        calls.n += 1
        return pl.DataFrame({"n": [mod.scale(i.n) * cfg for i in items]})

    src = RecordDataset([Item(n=1), Item(n=2)])
    first = double(src, 3)
    second = double(src, 3)
    assert calls.n == 1 and first.equals(second)
    inv = run.store.invocations(run.run_id)
    assert inv["fetched"].to_list() == [0, 1] and inv["status"].to_list() == ["ok", "ok"]
    assert inv["key"][0] == inv["key"][1] and inv["structural_key"][0] == inv["key"][0]
    art = run.store.artifacts(inv["key"][0])
    assert len(art) == 1 and art[0]["kind"] == "frame" and art[0]["rows"] == 2
    manifest = run.store.manifest(art[0]["code"])
    assert "stage_helpers:scale" in manifest.functions
    assert manifest.constants["stage_helpers:FACTOR"] == "2"
    inputs = run.store.invocation_inputs(int(inv["id"][0]))
    assert [(i["name"], i["kind"]) for i in inputs] == [("items", "source"), ("cfg", "value")]
    # a different input is a different key, computed
    double(src, 4)
    assert calls.n == 2


def test_editing_a_helper_reruns_only_the_stage_that_used_it(run, helpers):
    mod, path = helpers
    calls = Calls()
    other = Calls()

    @stage
    def scaled(items: RecordDataset[Item]) -> pl.DataFrame:
        calls.n += 1
        return pl.DataFrame({"n": [mod.scale(i.n) for i in items]})

    @stage
    def plain(items: RecordDataset[Item]) -> pl.DataFrame:
        other.n += 1
        return pl.DataFrame({"n": [i.n for i in items]})

    src = RecordDataset([Item(n=1)])
    scaled(src)
    plain(src)
    reload_after(mod, path, "return x * FACTOR", "return x * FACTOR + 1")
    scaled(src)
    plain(src)
    assert calls.n == 2 and other.n == 1
    # the constant the helper reads is a dependency too
    reload_after(mod, path, "FACTOR = 2", "FACTOR = 3")
    scaled(src)
    assert calls.n == 3


def test_a_changed_upstream_code_invalidates_downstream_through_the_lineage(run, helpers):
    mod, path = helpers
    down = Calls()

    @stage
    def up(items: RecordDataset[Item]) -> pl.DataFrame:
        return pl.DataFrame({"n": [mod.scale(i.n) for i in items]})

    @stage
    def total(frame: pl.DataFrame) -> pl.DataFrame:
        down.n += 1
        return pl.DataFrame({"t": [int(frame["n"].sum())]})

    src = RecordDataset([Item(n=1)])
    assert total(up(src))["t"][0] == 2
    assert total(up(src))["t"][0] == 2 and down.n == 1
    reload_after(mod, path, "return x * FACTOR", "return x * FACTOR * 10")
    assert total(up(src))["t"][0] == 20 and down.n == 2
    # and the lineage of the new artifact names the new upstream artifact
    inv = run.store.invocations(run.run_id)
    last = inv.filter(pl.col("stage").str.ends_with("total")).row(-1, named=True)
    lineage = run.store.lineage(last["key"], last["code"])
    assert [row["stage"].rsplit(".", 1)[-1] for row in lineage] == ["total", "up"]


def test_a_store_subclass_reruns_stages_that_take_the_store(run, tmp_path):
    calls = Calls()

    class MyStore(SqliteStore):
        def bm25(self, query, k, viewer):
            return super().bm25(query, k, viewer)

    @stage
    def over(store: SqliteStore, q: str) -> pl.DataFrame:
        calls.n += 1
        return pl.DataFrame({"id": store.identity()})

    plain = SqliteStore(tmp_path / "a.sqlite")
    mine = MyStore(tmp_path / "b.sqlite")
    over(plain, "x")
    over(plain, "x")
    assert calls.n == 1
    over(mine, "x")
    assert calls.n == 2


def test_stream_publishes_on_exhaustion_and_replays_from_parquet(run):
    calls = Calls()

    @stage
    def gen(items: RecordDataset[Item]) -> Iterator[Item]:
        calls.n += 1
        for i in items:
            yield Item(n=i.n * 10)

    @stage
    def count(items: Iterator[Item]) -> pl.DataFrame:
        return pl.DataFrame({"c": [sum(1 for _ in items)]})

    src = RecordDataset([Item(n=i) for i in range(5)])
    live = gen(src)
    assert isinstance(live, LiveStream) and live.artifact is None
    assert count(live)["c"][0] == 5
    assert live.artifact is not None and live.artifact.kind == "stream"
    assert [i.n for i in live] == [0, 10, 20, 30, 40]  # a second pass reads the artifact
    replay = gen(src)
    assert isinstance(replay, Stream) and calls.n == 1
    assert [i.n for i in replay] == [0, 10, 20, 30, 40]
    assert count(replay)["c"][0] == 5
    inv = run.store.invocations(run.run_id)
    assert inv.filter(pl.col("stage").str.ends_with("count"))["fetched"].to_list() == [0, 1]


def test_an_interrupted_stream_leaves_no_artifact_and_the_consumer_is_unpublished(run):
    @stage
    def gen(items: RecordDataset[Item]) -> Iterator[Item]:
        yield from items

    @stage
    def first_two(items: Iterator[Item]) -> pl.DataFrame:
        return pl.DataFrame({"n": [i.n for i in islice(items, 2)]})

    src = RecordDataset([Item(n=i) for i in range(5)])
    live = gen(src)
    assert first_two(live)["n"].to_list() == [0, 1]
    del live
    inv = run.store.invocations(run.run_id)
    by_stage = {r["stage"].rsplit(".", 1)[-1]: r for r in inv.iter_rows(named=True)}
    assert by_stage["gen"]["status"] == "partial"
    assert run.store.artifacts(by_stage["gen"]["key"]) == []
    assert run.store.artifacts(by_stage["first_two"]["key"]) == []
    assert not list((run.root / "artifacts").rglob(".tmp-*"))


def test_store_effect_stage_asks_the_store(run, tmp_path):
    calls = Calls()

    @stage
    def ingest(store: SqliteStore, items: RecordDataset[Item]) -> None:
        calls.n += 1
        store.set_meta("items", str(len(items)))

    src = RecordDataset([Item(n=1)])
    a = SqliteStore(tmp_path / "a.sqlite")
    ingest(a, src)
    ingest(a, src)
    assert calls.n == 1 and a.get_meta("items") == "1"
    b = SqliteStore(tmp_path / "b.sqlite")  # another store file: the effect is absent there
    ingest(b, src)
    assert calls.n == 2
    inv = run.store.invocations(run.run_id)
    assert inv["fetched"].to_list() == [0, 1, 0]
    rows = run.store.artifacts(inv["key"][0])
    assert rows[0]["kind"] == "store" and rows[0]["path"] is None


def test_seeded_stages_get_a_derived_seed_and_adapters_make_a_stage_seeded(run):
    seen = []

    @stage
    def draw(items: RecordDataset[Item], seed: int) -> pl.DataFrame:
        seen.append(seed)
        return pl.DataFrame({"s": [seed]})

    class Sensitive:
        seed_sensitive = True
        adapter = "fake"
        model = "m"

    class Insensitive:
        seed_sensitive = False
        adapter = "fake"
        model = "m"

    @stage
    def with_llm(items: RecordDataset[Item], llm: object) -> pl.DataFrame:
        return pl.DataFrame({"n": [1]})

    src = RecordDataset([Item(n=1)])
    draw(src, seed=0)
    assert seen == [run.seed] or seen[0] != 0  # the wrapper replaces the caller's seed
    with_llm(src, Sensitive())
    with_llm(src, Insensitive())
    inv = run.store.invocations(run.run_id)
    rows = inv.filter(pl.col("stage").str.ends_with("with_llm")).to_dicts()
    assert rows[0]["seed"] is not None and rows[0]["key"] != rows[0]["structural_key"]
    assert rows[1]["seed"] is None and rows[1]["key"] == rows[1]["structural_key"]


def test_no_context_runs_the_function_directly(tmp_path):
    calls = Calls()

    @stage
    def f(x: int) -> pl.DataFrame:
        calls.n += 1
        return pl.DataFrame({"x": [x]})

    assert f(1)["x"][0] == 1 and f(1)["x"][0] == 1 and calls.n == 2
    assert f.fn(2)["x"][0] == 2


def test_an_opaque_argument_is_a_type_error(run):
    @stage
    def f(x: object) -> pl.DataFrame:
        return pl.DataFrame()

    with pytest.raises(TypeError, match="no identity"):
        f(object())


def test_records_artifact_round_trips(run):
    @stage
    def make(n: int) -> list[Item]:
        return [Item(n=i) for i in range(n)]

    assert make(3) == [Item(n=0), Item(n=1), Item(n=2)]
    assert make(3) == [Item(n=0), Item(n=1), Item(n=2)]
    inv = run.store.invocations(run.run_id)
    assert inv["fetched"].to_list() == [0, 1]
    art = artifacts.complete(run.root, make.name, inv["key"][0], inv["code"][0])
    assert art is not None and art.kind == "records" and art.rows == 3


def test_an_edited_effect_stage_runs_again_against_a_complete_store(run, tmp_path, helpers):
    mod, path = helpers
    calls = Calls()

    @stage
    def mark(store: SqliteStore, items: RecordDataset[Item]) -> None:
        calls.n += 1
        store.set_meta("mark", str(mod.scale(len(items))))

    src = RecordDataset([Item(n=1)])
    a = SqliteStore(tmp_path / "a.sqlite")
    mark(a, src)
    mark(a, src)
    assert calls.n == 1 and a.get_meta("mark") == "2"
    reload_after(mod, path, "return x * FACTOR", "return x * FACTOR + 5")
    mark(a, src)  # the store holds the effect, but the code that made it changed
    assert calls.n == 2 and a.get_meta("mark") == "7"
    inv = run.store.invocations(run.run_id)
    assert inv["fetched"].to_list() == [0, 1, 0]


def test_an_empty_stream_publishes_an_empty_artifact(run):
    @stage
    def nothing(items: RecordDataset[Item]) -> Iterator[Item]:
        return iter(())

    @stage
    def count(items: Iterator[Item]) -> pl.DataFrame:
        return pl.DataFrame({"c": [sum(1 for _ in items)]})

    src = RecordDataset([])
    live = nothing(src)
    assert count(live)["c"][0] == 0
    assert isinstance(live, LiveStream) and live.artifact is not None and live.artifact.rows == 0
    assert list(nothing(src)) == []
    inv = run.store.invocations(run.run_id)
    assert inv["status"].to_list() == ["ok", "ok", "ok"] and inv["fetched"].to_list() == [0, 0, 1]


def test_a_dict_subclass_of_frames_is_a_different_input(run):
    class Special(dict):
        pass

    calls = Calls()

    @stage
    def over(frames: dict) -> pl.DataFrame:
        calls.n += 1
        return pl.DataFrame({"n": [len(frames)]})

    df = pl.DataFrame({"a": [1]})
    over({"x": df})
    over({"x": df})
    over(Special({"x": df}))
    assert calls.n == 2


def test_manifests_exclude_the_harness_and_repeat_exactly(run):
    """The wrapper, the run store and the hashing run inside every recording; a streamed stage
    keeps its recording open while the consumer pulls. None of that is the stage's code."""

    @stage
    def gen(items: RecordDataset[Item]) -> Iterator[Item]:
        for i in items:
            yield Item(n=i.n + 1)

    @stage
    def total(items: Iterator[Item]) -> pl.DataFrame:
        return pl.DataFrame({"t": [sum(i.n for i in items)]})

    src = RecordDataset([Item(n=1), Item(n=2)])
    assert total(gen(src))["t"][0] == 5
    assert total(gen(src))["t"][0] == 5  # a lookup ran this time: the manifest must not see it
    assert total(gen(RecordDataset([Item(n=3)])))["t"][0] == 4
    inv = run.store.invocations(run.run_id)
    assert inv["fetched"].to_list() == [0, 0, 1, 1, 0, 0]
    codes = inv.group_by("stage").agg(pl.col("code").n_unique())["code"].to_list()
    assert codes == [1, 1]
    for code in inv["code"].unique():
        manifest = run.store.manifest(code)
        assert manifest is not None
        assert not any(
            k.startswith(("triplum.stage", "triplum.bench.runstore")) for k in manifest.functions
        )
        assert not any(
            k.startswith(("triplum.stage", "triplum.bench.runstore")) for k in manifest.constants
        )
