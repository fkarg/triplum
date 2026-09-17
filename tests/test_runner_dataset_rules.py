"""The runner refuses what it cannot evaluate honestly and nulls recall where it is undefined."""

from dataclasses import replace

import polars as pl
import pytest
from triplum.bench.config import EmbedderConfig, LLMConfig, PipelineConfig, RunConfig
from triplum.bench.runner import run_benchmark
from triplum.bench.runstore import RunStore
from triplum.eval.datasets import base, registry


def _frames(with_corpus=True, with_questions=True):
    documents, grants, chunks = base.corpus_frames(
        "t", [("d1", "A", "Alice met Bob.", 0, None), ("d2", "B", "Bob is tall.", 0, None)]
    )
    rows = [
        base.question_row("q1", "Who met Bob?", "Alice", [], [1]),
        base.question_row("q2", "Who is Zed?", "unknown", [], [], answerable=False),
    ]
    questions = base.questions_frame(rows if with_questions else [])
    if not with_corpus:
        questions = questions.with_columns(
            pl.lit([]).cast(pl.List(pl.Int64)).alias("gold_chunk_ids")
        )
        documents, grants, chunks = (
            base.empty(s) for s in (base.DOC_SCHEMA, base.GRANT_SCHEMA, base.CHUNK_SCHEMA)
        )
    triples = base.triples_frame([(None, "d1", "Alice", "met", "Bob")])
    return base.Frames(questions, documents, grants, chunks, triples)


@pytest.fixture
def fake_registry(monkeypatch, tmp_path):
    monkeypatch.setattr(base, "FIXTURE_DIR", tmp_path / "fixtures")
    base.FIXTURE_DIR.mkdir()

    def register(name, frames, **kw):
        spec = base.Spec(
            name, "test", (base.File("u", name, "0" * 64, 1),), "none", lambda p, n: frames, **kw
        )
        monkeypatch.setitem(registry.SPECS, name, spec)
        base.write_fixture(name, frames)

    return register


def _cfg(tmp_path, dataset, pipeline="bm25"):
    return RunConfig(
        dataset=dataset,
        n=None,
        fixture=True,
        pipeline=PipelineConfig(
            name=pipeline,
            reader=LLMConfig(kind="fake"),
            embedder=EmbedderConfig(kind="fake", dims=8),
        ),
        judge=None,
        store_path=str(tmp_path / f"{dataset}.sqlite"),
        runstore_path=str(tmp_path / "runs.db"),
        cache_root=str(tmp_path / "cache"),
    )


def test_unanswerable_question_gets_null_recall_and_the_run_completes(tmp_path, fake_registry):
    fake_registry("qa-test", _frames())
    run_id = run_benchmark(_cfg(tmp_path, "qa-test", "oracle"))
    q = RunStore(tmp_path / "runs.db").questions(run_id).sort("question_id")
    assert q["r5"].to_list() == [1.0, None]
    assert q["r5"].mean() == 1.0


def test_extraction_only_dataset_is_refused(tmp_path, fake_registry):
    fake_registry("triples-test", _frames(with_questions=False))
    with pytest.raises(ValueError, match="no questions"):
        run_benchmark(_cfg(tmp_path, "triples-test"))


def test_missing_capability_is_refused_before_running(tmp_path, fake_registry):
    fake_registry("viewer-test", _frames(), needs="a viewer per question")
    with pytest.raises(ValueError, match="needs a viewer per question"):
        run_benchmark(_cfg(tmp_path, "viewer-test"))


def test_corpus_less_dataset_only_runs_closed_book(tmp_path, fake_registry):
    fake_registry("cb-test", _frames(with_corpus=False))
    with pytest.raises(ValueError, match="only the closed_book pipeline"):
        run_benchmark(_cfg(tmp_path, "cb-test", "bm25"))
    run_id = run_benchmark(_cfg(tmp_path, "cb-test", "closed_book"))
    q = RunStore(tmp_path / "runs.db").questions(run_id)
    assert q.height == 2 and q["r2"].to_list() == [None, None]


def test_dense_without_an_embedder_is_refused_before_retrieval(tmp_path, fake_registry):
    fake_registry("qa-test", _frames())
    cfg = _cfg(tmp_path, "qa-test", "dense")
    cfg = replace(cfg, pipeline=replace(cfg.pipeline, embedder=None))
    with pytest.raises(ValueError, match="dense needs an embedder"):
        run_benchmark(cfg)
