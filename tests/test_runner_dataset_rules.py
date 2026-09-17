"""The runner refuses what it cannot evaluate honestly and nulls recall where it is undefined."""

from dataclasses import replace

import pytest
from triplum.bench.config import EmbedderConfig, LLMConfig, PipelineConfig, RunConfig
from triplum.bench.inputs import Benchmark
from triplum.bench.runner import run_benchmark
from triplum.bench.runstore import RunStore
from triplum.data.corpus import Document, chunk_id
from triplum.datasets import base, fixtures, registry
from triplum.eval.inputs import Question, Triple
from triplum.utils.data import RecordDataset


def _benchmark(with_corpus=True, with_questions=True):
    documents = [
        Document(id="d1", source="t", text="A\nAlice met Bob."),
        Document(id="d2", source="t", text="B\nBob is tall."),
    ]
    questions = [
        Question(id="q1", question="Who met Bob?", answer="Alice", gold=(chunk_id("d1", 0),)),
        Question(id="q2", question="Who is Zed?", answer="unknown", answerable=False),
    ]
    if not with_corpus:
        documents = []
        questions = [q.model_copy(update={"gold": ()}) for q in questions]
    triples = [Triple(subject="Alice", predicate="met", object="Bob", document_id="d1")]
    return Benchmark(
        corpus=RecordDataset(documents),
        qa=RecordDataset(questions) if with_questions else None,
        extraction=RecordDataset(triples),
    )


@pytest.fixture
def fake_registry(monkeypatch, tmp_path):
    monkeypatch.setattr(fixtures, "FIXTURE_DIR", tmp_path / "fixtures")
    fixtures.FIXTURE_DIR.mkdir()

    def register(name, benchmark, **kw):
        entry = base.Entry(
            name=name, family="test", licence="none", build=lambda s: benchmark, **kw
        )
        monkeypatch.setitem(registry.ENTRIES, name, entry)
        fixtures.write(name, benchmark)

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
    fake_registry("qa-test", _benchmark())
    run_id = run_benchmark(_cfg(tmp_path, "qa-test", "oracle"))
    q = RunStore(tmp_path / "runs.db").questions(run_id).sort("question_id")
    assert q["r5"].to_list() == [1.0, None]
    assert q["r5"].mean() == 1.0


def test_extraction_only_dataset_is_refused(tmp_path, fake_registry):
    fake_registry("triples-test", _benchmark(with_questions=False))
    with pytest.raises(ValueError, match="no questions"):
        run_benchmark(_cfg(tmp_path, "triples-test"))


def test_missing_capability_is_refused_before_running(tmp_path, fake_registry):
    fake_registry("viewer-test", _benchmark(), needs="a viewer per question")
    with pytest.raises(ValueError, match="needs a viewer per question"):
        run_benchmark(_cfg(tmp_path, "viewer-test"))


def test_corpus_less_dataset_only_runs_closed_book(tmp_path, fake_registry):
    fake_registry("cb-test", _benchmark(with_corpus=False))
    with pytest.raises(ValueError, match="only the closed_book pipeline"):
        run_benchmark(_cfg(tmp_path, "cb-test", "bm25"))
    run_id = run_benchmark(_cfg(tmp_path, "cb-test", "closed_book"))
    q = RunStore(tmp_path / "runs.db").questions(run_id)
    assert q.height == 2 and q["r2"].to_list() == [None, None]


def test_dense_without_an_embedder_is_refused_before_retrieval(tmp_path, fake_registry):
    fake_registry("qa-test", _benchmark())
    cfg = _cfg(tmp_path, "qa-test", "dense")
    cfg = replace(cfg, pipeline=replace(cfg.pipeline, embedder=None))
    with pytest.raises(ValueError, match="dense needs an embedder"):
        run_benchmark(cfg)
