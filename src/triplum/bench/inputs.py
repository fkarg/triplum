"""Compose corpus and evaluation sources; materialize only for current whole-frame algorithms.

A `Benchmark` holds datasets, not batches: the consumer chooses the batch size. Identity comes
off the datasets, so a run identity never reads a file. `materialize` is the explicit eager
bridge the existing algorithms use; it also runs the cross-source integrity checks that no
single source can make on its own, before anything is scored.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import polars as pl

from triplum.cache import content_key
from triplum.data.corpus import CHUNK_SCHEMA, DOC_SCHEMA, GRANT_SCHEMA, CorpusBatch, Document
from triplum.datasets import collate
from triplum.eval.inputs import (
    QUESTION_SCHEMA,
    TRIPLE_SCHEMA,
    GoldMappingError,
    Question,
    Triple,
)
from triplum.utils.data import DataLoader, Source

BATCH = 1024


@dataclass
class Benchmark:
    """An experiment's independently replaceable, replayable sources.

    Each source must yield the same ordered records on every pass for its fingerprint. The runner
    may read it again on a cold stage, so one-shot sources are not valid benchmark inputs.
    """

    name: str = "custom"
    corpus: Source[Document] | None = None
    qa: Source[Question] | None = None
    extraction: Source[Triple] | None = None
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


def _frames[T, B](source: Source[T], collate_fn: Callable[[list[T]], B]) -> list[B]:
    return list(DataLoader(source, batch_size=BATCH, collate_fn=collate_fn))


def _concat(frames: list[pl.DataFrame], schema) -> pl.DataFrame:
    return pl.concat(frames) if frames else pl.DataFrame(schema=schema)


def check(corpus: CorpusBatch, qa: pl.DataFrame | None) -> None:
    """Cross-source integrity: document ids are unique, and every gold chunk id a question names
    exists in the corpus. Raises `GoldMappingError` before anything is scored. Candidate ids in
    question metadata are hints for fixture building, not gold: upstream contexts can name a
    paragraph the released corpus lacks (one 2Wiki question does), so they are not checked."""
    dup = corpus.documents.filter(pl.col("id").is_duplicated())["id"].unique().to_list()
    if dup:
        raise GoldMappingError(f"duplicate document ids: {dup[:5]}")
    if qa is None:
        return
    ids = set(corpus.chunks["id"].to_list())  # empty corpus: any gold is an error
    for gold, qid in zip(qa["gold_chunk_ids"].to_list(), qa["id"].to_list()):
        missing = sorted(set(gold) - ids)
        if missing:
            raise GoldMappingError(f"question {qid}: gold chunks not in corpus: {missing[:5]}")


def identities(benchmark: Benchmark) -> tuple[str, str]:
    """The corpus identity and the evaluation identity of a benchmark, from the sources'
    fingerprints and without reading anything."""
    corpus_hash = (
        benchmark.corpus.fingerprint()
        if benchmark.corpus is not None
        else content_key("corpus", None)
    )
    evaluation_hash = content_key(
        "evaluation",
        {
            "qa": benchmark.qa.fingerprint() if benchmark.qa is not None else None,
            "extraction": benchmark.extraction.fingerprint()
            if benchmark.extraction is not None
            else None,
        },
    )
    return corpus_hash, evaluation_hash


def materialize(benchmark: Benchmark) -> PreparedBenchmark:
    """Consume each source once into the frames required by today's benchmark algorithms.

    This operation is deliberately eager. Use the sources/loaders directly for incremental
    processing. In particular, an unbounded stream must be bounded before calling this.
    Question-linked gold triples are restricted to the questions present, so a selection of
    questions selects their triples too.
    """
    if benchmark.corpus is not None:
        batches = _frames(benchmark.corpus, collate.corpus_batch)
        corpus = CorpusBatch(
            _concat([b.documents for b in batches], DOC_SCHEMA),
            _concat([b.grants for b in batches], GRANT_SCHEMA),
            _concat([b.chunks for b in batches], CHUNK_SCHEMA),
        )
    else:
        corpus = CorpusBatch(
            pl.DataFrame(schema=DOC_SCHEMA),
            pl.DataFrame(schema=GRANT_SCHEMA),
            pl.DataFrame(schema=CHUNK_SCHEMA),
        )
    qa = (
        _concat(_frames(benchmark.qa, collate.questions_frame), QUESTION_SCHEMA)
        if benchmark.qa is not None
        else None
    )
    extraction = (
        _concat(_frames(benchmark.extraction, collate.triples_frame), TRIPLE_SCHEMA)
        if benchmark.extraction is not None
        else None
    )
    if qa is not None and extraction is not None:
        extraction = extraction.filter(
            pl.col("question_id").is_null() | pl.col("question_id").is_in(qa["id"].implode())
        )
    check(corpus, qa)
    corpus_hash, evaluation_hash = identities(benchmark)
    return PreparedBenchmark(
        benchmark.name, corpus, qa, extraction, corpus_hash, evaluation_hash, benchmark.needs
    )
