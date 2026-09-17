"""Sources compose without registering, unrelated task tables, or eager consumption; identity
comes off the sources and the cross-source checks run before anything is scored."""

from collections.abc import Iterator

import pytest
from triplum.bench.inputs import Benchmark, materialize
from triplum.data.corpus import Document, chunk_id
from triplum.eval.inputs import GoldMappingError, Question, Triple
from triplum.utils.data import IterableDataset, RecordDataset, Take


def _doc(i: str, text: str = "hello") -> Document:
    return Document(id=i, source="t", text=text)


def test_qa_only_composition_has_no_corpus_or_extraction_requirement():
    benchmark = Benchmark(
        name="custom", qa=RecordDataset([Question(id="q", question="Who?", answer="A")])
    )
    assert benchmark.extraction is None
    inputs = materialize(benchmark)
    assert inputs.corpus.chunks.is_empty()
    assert inputs.qa is not None and inputs.qa["id"].to_list() == ["q"]
    assert inputs.extraction is None


def test_one_shot_corpus_is_consumed_only_at_explicit_materialization():
    pulled = []

    class Stream(IterableDataset[Document]):
        def __iter__(self) -> Iterator[Document]:
            pulled.append("read")
            yield _doc("d")

        def fingerprint(self) -> str:
            return "stream:v1"

    benchmark = Benchmark(name="stream", corpus=Stream())
    assert pulled == []
    inputs = materialize(benchmark)
    assert pulled == ["read"]
    assert inputs.corpus.chunks["text"].to_list() == ["hello"]
    assert inputs.corpus_hash == "stream:v1"
    assert inputs.qa is None and inputs.extraction is None


def test_identity_is_the_sources_fingerprint_not_the_materialised_content():
    corpus = RecordDataset([_doc("a", "A"), _doc("b", "B")])
    gold = RecordDataset([Triple(subject="A", predicate="is", object="B", document_id="a")])
    questions = RecordDataset(
        [Question(id="q1", question="?", answer="A", gold=(chunk_id("a", 0),))] * 2
        + [Question(id="q2", question="?", answer="B", gold=(chunk_id("b", 0),))]
    )
    whole = materialize(Benchmark(corpus=corpus, qa=questions, extraction=gold))
    fewer = materialize(Benchmark(corpus=corpus, qa=Take(questions, 1), extraction=gold))
    assert whole.corpus_hash == fewer.corpus_hash == corpus.fingerprint()
    assert whole.evaluation_hash != fewer.evaluation_hash
    assert fewer.qa is not None and fewer.qa.height == 1


def test_question_linked_triples_follow_the_selected_questions():
    triples = RecordDataset(
        [
            Triple(subject="s", predicate="p", object="o", question_id="q1"),
            Triple(subject="s", predicate="p", object="o", question_id="q2"),
            Triple(subject="s", predicate="p", object="o", document_id="d"),
        ]
    )
    questions = RecordDataset([Question(id=q, question="?", answer="a") for q in ("q1", "q2")])
    inputs = materialize(Benchmark(qa=Take(questions, 1), extraction=triples))
    assert inputs.extraction is not None
    assert inputs.extraction["question_id"].to_list() == ["q1", None]


def test_materialize_rejects_gold_outside_the_corpus_and_duplicate_documents():
    corpus = RecordDataset([_doc("a")])
    bad = RecordDataset([Question(id="q", question="?", answer="x", gold=(chunk_id("zzz", 0),))])
    with pytest.raises(GoldMappingError, match="not in corpus"):
        materialize(Benchmark(corpus=corpus, qa=bad))
    hint = RecordDataset(
        [Question(id="q", question="?", answer="x", metadata={"candidate_chunk_ids": [7]})]
    )
    materialize(Benchmark(corpus=corpus, qa=hint))  # candidate ids are hints, not gold
    with pytest.raises(GoldMappingError, match="duplicate"):
        materialize(Benchmark(corpus=RecordDataset([_doc("a"), _doc("a", "other")])))


def test_custom_benchmark_runs_without_a_registry_entry(tmp_path):
    from triplum.bench.config import LLMConfig, PipelineConfig, RunConfig
    from triplum.bench.runner import run_benchmark
    from triplum.bench.runstore import RunStore

    source = Benchmark(
        name="unregistered", qa=RecordDataset([Question(id="q", question="Who?", answer="A")])
    )
    cfg = RunConfig(
        dataset="unregistered",
        pipeline=PipelineConfig(name="closed_book", reader=LLMConfig(kind="fake")),
        judge=None,
        cache_root=str(tmp_path),
    )
    run_id = run_benchmark(cfg, data=source)
    with RunStore(tmp_path / "runs.db") as runs:
        assert runs.questions(run_id)["question_id"].to_list() == ["q"]


def test_gold_without_a_corpus_is_an_error():
    bad = RecordDataset([Question(id="q", question="?", answer="x", gold=(1,))])
    with pytest.raises(GoldMappingError, match="not in corpus"):
        materialize(Benchmark(qa=bad))
