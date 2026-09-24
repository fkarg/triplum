"""Simple seeded variants of benchmark corpus sources."""

from __future__ import annotations

from collections.abc import Iterator

from triplum.bench.inputs import Benchmark
from triplum.cache import content_key
from triplum.data.corpus import Document
from triplum.datasets import fixtures
from triplum.eval.inputs import Question
from triplum.utils.data import IterableDataset, Source


class DistractorCorpus(IterableDataset[Document]):
    """Keep question evidence plus ``count`` seeded distractor chunks.

    Identity does not read either source. The simple first implementation reads the whole corpus
    when iterated; each pass repeats selection with the same seed.
    """

    def __init__(
        self, corpus: Source[Document], qa: Source[Question], *, count: int, seed: int
    ) -> None:
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("count must be a non-negative integer")
        self.corpus = corpus
        self.qa = qa
        self.count = count
        self.seed = seed

    def fingerprint(self) -> str:
        return content_key(
            "distractor-corpus",
            [1, self.corpus.fingerprint(), self.qa.fingerprint(), self.count, self.seed],
        )

    def __iter__(self) -> Iterator[Document]:
        selected = fixtures.subset(
            Benchmark(corpus=self.corpus, qa=self.qa),
            n=None,
            distractors=self.count,
            seed=self.seed,
        )
        assert selected.corpus is not None
        return iter(selected.corpus)
