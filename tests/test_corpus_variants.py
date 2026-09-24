"""A seeded corpus variant replays without reading its inputs for identity."""

from collections.abc import Iterator

import pytest

from triplum.bench.config import LLMConfig, PipelineConfig, RunConfig
from triplum.bench.inputs import Benchmark, identities, materialize
from triplum.bench.runner import run_benchmark, store_path
from triplum.data.corpus import Document, chunk_id
from triplum.datasets.variants import DistractorCorpus
from triplum.eval.inputs import Question
from triplum.utils.data import IterableDataset, RecordDataset


class CountingCorpus(IterableDataset[Document]):
    def __init__(self) -> None:
        self.reads = 0

    def fingerprint(self) -> str:
        return "four-documents:v1"

    def __iter__(self) -> Iterator[Document]:
        self.reads += 1
        for name in ("gold", "extra-a", "extra-b", "extra-c"):
            yield Document(id=name, source="test", text=name)


def test_seeded_distractors_are_lazy_replayable_and_identified():
    corpus = CountingCorpus()
    qa = RecordDataset(
        [Question(id="q", question="Which?", answer="gold", gold=(chunk_id("gold", 0),))]
    )
    variant = DistractorCorpus(corpus, qa, count=1, seed=4)
    another_seed = DistractorCorpus(corpus, qa, count=1, seed=5)
    assert variant.fingerprint() != another_seed.fingerprint()
    assert corpus.reads == 0
    first = list(variant)
    assert list(variant) == first
    assert corpus.reads == 2
    assert [doc.id for doc in first] == ["gold", "extra-a"]
    assert [doc.id for doc in another_seed] == ["gold", "extra-c"]
    prepared = materialize(Benchmark(corpus=variant, qa=qa))
    assert prepared.corpus.chunks.height == 2


@pytest.mark.parametrize("count", [-1, True, 1.5])
def test_distractor_count_must_be_a_non_negative_integer(count):
    with pytest.raises(ValueError, match="count"):
        DistractorCorpus(CountingCorpus(), RecordDataset([]), count=count, seed=0)


def test_seeded_variants_get_distinct_corpus_stores(tmp_path):
    corpus = CountingCorpus()
    qa = RecordDataset(
        [Question(id="q", question="Which?", answer="gold", gold=(chunk_id("gold", 0),))]
    )
    cfg = RunConfig(
        dataset="demo",
        pipeline=PipelineConfig(name="bm25", reader=LLMConfig(kind="fake")),
        judge=None,
        cache_root=str(tmp_path),
    )
    paths = []
    for seed in (4, 5):
        benchmark = Benchmark(
            name="demo", corpus=DistractorCorpus(corpus, qa, count=1, seed=seed), qa=qa
        )
        paths.append(store_path(cfg, benchmark.name, identities(benchmark)[0]))
        run_benchmark(cfg, data=benchmark)
    assert paths[0] != paths[1]
    assert all(path.exists() for path in paths)
