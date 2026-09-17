"""Sources compose without registering, unrelated task tables, or eager consumption."""

from collections.abc import Iterator

from triplum.bench.inputs import Benchmark, materialize
from triplum.data.corpus import CorpusBatch
from triplum.datasets import base
from triplum.eval.inputs import ExtractionEvaluation, QAEvaluation
from triplum.utils.data import DataLoader


def test_qa_only_composition_has_no_corpus_or_extraction_requirement():
    questions = base.questions_frame([base.question_row("q", "Who?", "A", [], [])])
    benchmark = Benchmark(name="custom", qa=QAEvaluation([questions]))
    assert benchmark.extraction is None
    inputs = materialize(benchmark)
    assert inputs.corpus.chunks.is_empty()
    assert inputs.qa is not None and inputs.qa["id"].to_list() == ["q"]
    assert inputs.extraction is None


def test_one_shot_corpus_is_consumed_only_at_explicit_materialization():
    batch = CorpusBatch(*base.corpus_frames("test", [("d", "", "hello", 0, None)]))
    pulled = []

    def stream() -> Iterator[CorpusBatch]:
        pulled.append("read")
        yield batch

    benchmark = Benchmark(name="stream", corpus=DataLoader(stream(), batch_size=None))
    assert pulled == []
    inputs = materialize(benchmark)
    assert pulled == ["read"]
    assert inputs.corpus.chunks["text"].to_list() == ["hello"]
    assert inputs.qa is None and inputs.extraction is None


def test_batch_boundaries_do_not_change_corpus_or_task_identity():
    batch = CorpusBatch(
        *base.corpus_frames("test", [("a", "", "A", 0, None), ("b", "", "B", 0, None)])
    )
    gold = base.triples_frame([(None, "a", "A", "is", "B"), (None, "b", "B", "is", "C")])
    whole = materialize(Benchmark(corpus=[batch], extraction=ExtractionEvaluation([gold])))
    split = materialize(
        Benchmark(
            corpus=[CorpusBatch(*(f.slice(i, 1) for f in batch)) for i in range(2)],
            extraction=ExtractionEvaluation(gold.iter_slices(1)),
        )
    )
    assert whole.corpus_hash == split.corpus_hash
    assert whole.evaluation_hash == split.evaluation_hash


def test_custom_benchmark_runs_without_a_registry_entry(tmp_path):
    from triplum.bench.config import LLMConfig, PipelineConfig, RunConfig
    from triplum.bench.runner import run_benchmark
    from triplum.bench.runstore import RunStore

    questions = base.questions_frame([base.question_row("q", "Who?", "A", [], [])])
    source = Benchmark(name="unregistered", qa=QAEvaluation(iter([questions])))
    cfg = RunConfig(
        dataset="unregistered",
        pipeline=PipelineConfig(name="closed_book", reader=LLMConfig(kind="fake")),
        judge=None,
        cache_root=str(tmp_path),
    )
    run_id = run_benchmark(cfg, data=source)
    with RunStore(tmp_path / "runs.db") as runs:
        assert runs.questions(run_id)["question_id"].to_list() == ["q"]
