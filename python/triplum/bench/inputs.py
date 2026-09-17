"""Compose corpus and evaluation sources; materialize only for current whole-frame algorithms.

The generic dataset/loader API does not depend on this module. A custom benchmark needs no
registry entry and its sources need not have a known length, hash, or random access.
"""

from collections.abc import Iterable
from dataclasses import dataclass

import polars as pl

from triplum.cache import content_key
from triplum.data.corpus import CHUNK_SCHEMA, DOC_SCHEMA, GRANT_SCHEMA, CorpusBatch
from triplum.datasets.corpus import CorpusDataset
from triplum.datasets.frames import FrameDataset
from triplum.eval.inputs import (
    QUESTION_SCHEMA,
    TRIPLE_SCHEMA,
    ExtractionEvaluation,
    QAEvaluation,
)


@dataclass
class Benchmark:
    """An experiment's independently replaceable sources, not a universal dataset shape."""

    name: str = "custom"
    corpus: Iterable[CorpusBatch] = ()
    qa: QAEvaluation | None = None
    extraction: ExtractionEvaluation | None = None
    needs: str | None = None


@dataclass
class PreparedBenchmark:
    """Explicit eager boundary for the existing runner; not a source extension interface."""

    name: str
    corpus: CorpusBatch
    qa: pl.DataFrame | None
    extraction: pl.DataFrame | None
    corpus_hash: str
    evaluation_hash: str
    needs: str | None = None


def materialize(benchmark: Benchmark) -> PreparedBenchmark:
    """Consume each source once into the frames required by today's benchmark algorithms.

    This operation is deliberately eager. Use the sources/loaders directly for incremental
    processing. In particular, an unbounded stream must be bounded before calling this.
    """
    documents, grants, chunks = [], [], []
    for batch in benchmark.corpus:
        documents.append(batch.documents)
        grants.append(batch.grants)
        chunks.append(batch.chunks)

    def collect(frames: Iterable[pl.DataFrame], schema) -> pl.DataFrame:
        batches = list(frames)
        return pl.concat(batches) if batches else pl.DataFrame(schema=schema)

    corpus = CorpusBatch(
        collect(documents, DOC_SCHEMA),
        collect(grants, GRANT_SCHEMA),
        collect(chunks, CHUNK_SCHEMA),
    )
    qa = collect(benchmark.qa.questions, QUESTION_SCHEMA) if benchmark.qa is not None else None
    extraction = (
        collect(benchmark.extraction.triples, TRIPLE_SCHEMA)
        if benchmark.extraction is not None
        else None
    )
    return PreparedBenchmark(
        benchmark.name,
        corpus,
        qa,
        extraction,
        CorpusDataset(corpus).fingerprint(),
        content_key(
            "evaluation",
            {
                "qa": FrameDataset(qa).fingerprint() if qa is not None else None,
                "extraction": FrameDataset(extraction).fingerprint()
                if extraction is not None
                else None,
            },
        ),
        benchmark.needs,
    )
