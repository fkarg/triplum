"""Task-owned evaluation schemas and independently supplied target streams."""

from collections.abc import Iterable
from dataclasses import dataclass

import polars as pl

QUESTION_SCHEMA = {
    "id": pl.Utf8,
    "question": pl.Utf8,
    "answer": pl.Utf8,
    "aliases": pl.List(pl.Utf8),
    "gold_chunk_ids": pl.List(pl.Int64),
    "qtype": pl.Utf8,
    "answerable": pl.Boolean,
    "as_of": pl.Int64,
    "metadata": pl.Utf8,
}
TRIPLE_SCHEMA = {
    "question_id": pl.Utf8,
    "document_id": pl.Utf8,
    "subject": pl.Utf8,
    "predicate": pl.Utf8,
    "object": pl.Utf8,
}


@dataclass
class QAEvaluation:
    """Question batches for QA scoring; independent of the corpus source."""

    questions: Iterable[pl.DataFrame]


@dataclass
class ExtractionEvaluation:
    """Gold triple batches for extraction scoring; never a requirement on corpus data."""

    triples: Iterable[pl.DataFrame]
