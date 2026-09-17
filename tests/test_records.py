"""Boundary records validate once at the parse; collators project them onto the canonical
frames; ids are stable functions of the source's declared key, never of parse position."""

import json

import polars as pl
import pytest
from pydantic import ValidationError
from triplum.data.corpus import (
    CHUNK_SCHEMA,
    DOC_SCHEMA,
    GRANT_SCHEMA,
    Document,
    Segment,
    chunk_id,
    content_id,
)
from triplum.datasets import collate
from triplum.eval.inputs import QUESTION_SCHEMA, TRIPLE_SCHEMA, Question, Triple


def test_document_defaults_to_one_segment_over_its_text():
    d = Document(id="d", source="t", text="hello")
    assert d.segments == (Segment(ordinal=0, start=0, end=5),)
    assert d.grants == ("public",) and d.chunk_ids() == [chunk_id("d", 0)]


@pytest.mark.parametrize(
    "segments,message",
    [
        ([Segment(ordinal=0, start=0, end=9)], "span outside"),
        ([Segment(ordinal=1, start=0, end=1), Segment(ordinal=1, start=1, end=2)], "unique"),
        ([Segment(ordinal=-1, start=0, end=1)], "non-negative"),
        ([Segment(ordinal=0, start=0, end=1, parent=7, level=1)], "parent must exist"),
        (
            [Segment(ordinal=0, start=0, end=1), Segment(ordinal=1, start=0, end=1, parent=0)],
            "lower level",
        ),
    ],
)
def test_document_rejects_bad_segments(segments, message):
    with pytest.raises(ValidationError, match=message):
        Document(id="d", source="t", text="hello", segments=tuple(segments))


def test_document_needs_a_grant():
    with pytest.raises(ValidationError, match="grant"):
        Document(id="d", source="t", text="x", grants=())


def test_ids_are_stable_and_positive():
    assert content_id("A", "text") == content_id("A", "text") != content_id("A")
    assert len(content_id("A")) == 20
    cid = chunk_id("d", 3)
    assert cid == chunk_id("d", 3) and 0 < cid < 2**60 and cid != chunk_id("d", 4)


def test_corpus_batch_slices_segments_and_maps_parents():
    text = "Title\n\nFirst para. Second para."
    d = Document(
        id="doc",
        source="t",
        text=text,
        segments=(
            Segment(ordinal=0, start=0, end=len(text)),
            Segment(ordinal=1, start=7, end=18, parent=0, level=1),
            Segment(ordinal=2, start=19, end=len(text), parent=0, level=1),
        ),
        uri="u",
        observed_at=5,
        grants=("alice", "public"),
        metadata={"k": 1},
    )
    batch = collate.corpus_batch([d])
    assert dict(batch.documents.schema) == DOC_SCHEMA
    assert dict(batch.grants.schema) == GRANT_SCHEMA
    assert dict(batch.chunks.schema) == CHUNK_SCHEMA
    assert batch.documents.row(0) == ("doc", "t", "u", 5, json.dumps({"k": 1}))
    assert batch.grants["principal"].to_list() == ["alice", "public"]
    assert batch.chunks["text"].to_list() == [text, "First para.", "Second para."]
    assert batch.chunks["parent_id"].to_list() == [None, chunk_id("doc", 0), chunk_id("doc", 0)]
    assert batch.chunks["id"].to_list() == d.chunk_ids()
    assert collate.corpus_batch([]).chunks.is_empty()


def test_question_normalises_aliases_and_gold():
    q = Question(id="q", question="?", answer="a", aliases=("b", "a", "b"), gold=(3, 1, 3))
    assert q.aliases == ("a", "b") and q.gold == (1, 3) and q.answerable and q.as_of is None
    frame = collate.questions_frame([q])
    assert dict(frame.schema) == QUESTION_SCHEMA
    assert frame["aliases"][0].to_list() == ["a", "b"] and frame["gold_chunk_ids"][0].to_list() == [
        1,
        3,
    ]
    assert frame["metadata"][0] == "{}"


def test_triples_frame():
    frame = collate.triples_frame([Triple(subject="s", predicate="p", object="o", document_id="d")])
    assert dict(frame.schema) == TRIPLE_SCHEMA
    assert frame.row(0) == (None, "d", "s", "p", "o")
    assert isinstance(frame, pl.DataFrame)


def test_question_accepts_numeric_answers_as_text():
    q = Question(id="q", question="how many?", answer=3, aliases=(3, "three"))  # ty: ignore[invalid-argument-type]
    assert q.answer == "3" and q.aliases == ("3", "three")
