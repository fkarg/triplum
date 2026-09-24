"""A run is a sequence of stages: a second identical run fetches every one of them and reads
no dataset; replicates under derived seeds show where variance comes from."""

from collections.abc import Iterator

import polars as pl
import pytest

from triplum.bench.config import LLMConfig, PipelineConfig, RunConfig, replace
from triplum.bench.inputs import Benchmark
from triplum.bench.report import variance
from triplum.bench.runner import run_benchmark, run_experiment
from triplum.bench.runstore import RunStore
from triplum.data.corpus import Document, chunk_id
from triplum.eval.inputs import Question
from triplum.utils.data import IterableDataset, RecordDataset

DOCS = [
    Document(id="d1", source="t", text="Alice met Bob in Ghent."),
    Document(id="d2", source="t", text="Bob is tall."),
    Document(id="d3", source="t", text="Carol lives in Oslo."),
]
QUESTIONS = [
    Question(
        id="q1", question="Where did Alice meet Bob?", answer="Ghent", gold=(chunk_id("d1", 0),)
    ),
    Question(id="q2", question="Where does Carol live?", answer="Oslo", gold=(chunk_id("d3", 0),)),
]


class CountingCorpus(IterableDataset[Document]):
    """A replayable corpus whose reads are observable."""

    def __init__(self) -> None:
        self.reads = 0

    def __iter__(self) -> Iterator[Document]:
        self.reads += 1
        yield from DOCS

    def fingerprint(self) -> str:
        return "counting-corpus:v1"


def _cfg(tmp_path, **kw) -> RunConfig:
    return RunConfig(
        dataset="demo",
        pipeline=PipelineConfig(name="bm25", reader=LLMConfig(kind="fake")),
        judge=LLMConfig(kind="fake"),
        cache_root=str(tmp_path / "cache"),
        runstore_path=str(tmp_path / "runs.db"),
        **kw,
    )


def _bench(corpus=None) -> Benchmark:
    return Benchmark(name="demo", corpus=corpus or RecordDataset(DOCS), qa=RecordDataset(QUESTIONS))


def test_second_run_is_the_stored_run_and_reads_nothing(tmp_path):
    source = CountingCorpus()
    cfg = _cfg(tmp_path)
    first = run_benchmark(cfg, data=_bench(source))
    assert run_benchmark(cfg, data=_bench(source)) == first
    with RunStore(tmp_path / "runs.db") as rs:
        inv = rs.invocations(first)
        assert inv["fetched"].to_list() == [0] * inv.height
        assert set(inv["stage"].str.split(":").list.last()) == {
            "corpus_frames",
            "questions",
            "ingest",
            "retrieve",
            "answer",
        }
        row = rs.run(first)
        assert row is not None and rs.questions(first).height == 2 and row["n"] == 2
        assert row["code_hash"] and row["experiment_id"]
        # a forced run is a new run whose stages are all fetched: still no read
        forced = run_benchmark(replace(cfg, force=True), data=_bench(source))
        assert forced != first
        assert rs.invocations(forced)["fetched"].to_list() == [1] * inv.height
        assert rs.questions(forced).height == 2
        assert rs.artifact(forced, "store") is not None
    assert source.reads == 1


def test_one_benchmark_replays_its_source_for_cold_parameter_variants(tmp_path):
    source = CountingCorpus()
    benchmark = _bench(source)
    first_cfg = _cfg(tmp_path)
    second_cfg = replace(
        first_cfg,
        cache_root=str(tmp_path / "other-cache"),
        runstore_path=str(tmp_path / "other-runs.db"),
        pipeline=replace(first_cfg.pipeline, top_k=1),
    )
    first = run_benchmark(first_cfg, data=benchmark)
    second = run_benchmark(second_cfg, data=benchmark)
    assert source.reads == 2
    with RunStore(tmp_path / "runs.db") as runs:
        assert runs.questions(first).height == 2
    with RunStore(tmp_path / "other-runs.db") as runs:
        assert runs.questions(second).height == 2
        assert runs.invocations(second).filter(pl.col("stage").str.ends_with(":corpus_frames"))[
            "fetched"
        ].to_list() == [0]


def test_replicates_with_a_deterministic_reader_are_all_deterministic(tmp_path):
    cfg = _cfg(tmp_path, replicates=3)
    ids = run_experiment(cfg, data=_bench())
    assert len(ids) == 3 and len(set(ids)) == 3
    assert run_benchmark(replace(cfg, replicates=1), data=_bench()) == ids[0]
    with RunStore(tmp_path / "runs.db") as rs:
        runs = rs.runs().filter(pl.col("run_id").is_in(ids)).sort("replicate")
        assert runs["replicate"].to_list() == [0, 1, 2]
        assert runs["experiment_id"].n_unique() == 1
        stages, metrics = variance(rs, runs["experiment_id"][0])
    assert set(stages["verdict"]) == {"deterministic"}
    assert stages.filter(pl.col("stage") == "answer")["executed"][0] == 1
    assert metrics.filter(pl.col("metric") == "em")["std"][0] == 0.0


def test_a_perturbing_reader_adds_variance_and_retrieval_is_fetched(tmp_path):
    cfg = _cfg(tmp_path, replicates=3)
    cfg = replace(cfg, pipeline=replace(cfg.pipeline, reader=LLMConfig(kind="fake", perturb=True)))
    ids = run_experiment(cfg, data=_bench())
    with RunStore(tmp_path / "runs.db") as rs:
        row = rs.run(ids[0])
        assert row is not None
        stages, metrics = variance(rs, row["experiment_id"])
        answers = [rs.questions(rid)["answer"].to_list() for rid in ids]
    by_stage = {r["stage"]: r for r in stages.iter_rows(named=True)}
    assert by_stage["answer"]["verdict"] == "adds variance"
    assert by_stage["answer"]["executed"] == 3
    assert by_stage["retrieve"]["verdict"] == "deterministic"
    assert by_stage["retrieve"]["executed"] == 1
    assert len({tuple(a) for a in answers}) == 3
    f1 = metrics.filter(pl.col("metric") == "f1").row(0, named=True)
    assert f1["replicates"] == 3 and f1["std"] is not None  # the spread is measured, not assumed


def test_cli_replicates_prints_the_variance_tables(tmp_path, capsys):
    from triplum.bench.cli import main

    rc = main(
        [
            "bench",
            "run",
            "--pipeline",
            "bm25",
            "--dataset",
            "musique",
            "--n",
            "3",
            "--fixture",
            "--reader",
            "fake",
            "--judge",
            "fake",
            "--replicates",
            "2",
            "--cache-root",
            str(tmp_path),
            "--runstore",
            str(tmp_path / "runs.db"),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0 and "Stages across replicates" in out and "Metrics over replicates" in out
    with RunStore(tmp_path / "runs.db") as rs:
        rid = rs.runs()["run_id"][0]
    assert main(["bench", "variance", rid, "--runstore", str(tmp_path / "runs.db")]) == 0
    assert "deterministic" in capsys.readouterr().out


def test_an_extraction_only_benchmark_cannot_be_run(tmp_path):
    with pytest.raises(ValueError, match="no questions"):
        run_benchmark(_cfg(tmp_path), data=Benchmark(name="x", corpus=RecordDataset(DOCS)))


def test_judge_configuration_is_in_the_run_identity(tmp_path):
    cfg = _cfg(tmp_path)
    first = run_benchmark(cfg, data=_bench())
    hotter = replace(cfg, judge=LLMConfig(kind="fake", temperature=0.7))
    assert run_benchmark(hotter, data=_bench()) != first
    assert run_benchmark(cfg, data=_bench()) == first
