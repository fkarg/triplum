"""Collators: record lists onto the canonical frames. Consumers pass these to a `DataLoader`;
a source never batches. The projection is part of `data.corpus.RECORD_VERSION`."""

from __future__ import annotations

import json

import polars as pl

from triplum.data.corpus import (
    CHUNK_SCHEMA,
    DOC_SCHEMA,
    GRANT_SCHEMA,
    CorpusBatch,
    Document,
    chunk_id,
)
from triplum.eval.inputs import QUESTION_SCHEMA, TRIPLE_SCHEMA, Question, Triple


def corpus_batch(documents: list[Document]) -> CorpusBatch:
    """One document row, one grant row per principal (granted at 0, open), one chunk row per
    segment with its text sliced from the document text."""
    doc_rows, grant_rows, chunk_rows = [], [], []
    for d in documents:
        doc_rows.append((d.id, d.source, d.uri, d.observed_at, json.dumps(d.metadata)))
        grant_rows.extend((d.id, p, 0, None) for p in d.grants)
        for s in d.segments:
            parent = chunk_id(d.id, s.parent) if s.parent is not None else None
            chunk_rows.append(
                (
                    chunk_id(d.id, s.ordinal),
                    d.id,
                    parent,
                    s.level,
                    s.start,
                    s.end,
                    d.text[s.start : s.end],
                )
            )
    return CorpusBatch(
        pl.DataFrame(doc_rows, schema=DOC_SCHEMA, orient="row"),
        pl.DataFrame(grant_rows, schema=GRANT_SCHEMA, orient="row"),
        pl.DataFrame(chunk_rows, schema=CHUNK_SCHEMA, orient="row"),
    )


def questions_frame(questions: list[Question]) -> pl.DataFrame:
    rows = [
        (
            q.id,
            q.question,
            q.answer,
            list(q.aliases),
            list(q.gold),
            q.qtype,
            q.answerable,
            q.as_of,
            json.dumps(q.metadata),
        )
        for q in questions
    ]
    return pl.DataFrame(rows, schema=QUESTION_SCHEMA, orient="row")


def triples_frame(triples: list[Triple]) -> pl.DataFrame:
    rows = [(t.question_id, t.document_id, t.subject, t.predicate, t.object) for t in triples]
    return pl.DataFrame(rows, schema=TRIPLE_SCHEMA, orient="row")
