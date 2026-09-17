import polars as pl
from triplum.eval import triples
from triplum.eval.datasets.base import CHUNK_SCHEMA, DOC_SCHEMA, QUESTION_SCHEMA, TRIPLE_SCHEMA
from triplum.extract import extract
from triplum.extract.fake import FakeExtractor


def test_exact_and_partial_matching():
    gold = [triples.normalise_triple("JoAnn", "works for", "New York Times")]
    assert (
        triples.match(
            [triples.normalise_triple("JoAnn", "work_for", "the New York Times")], gold, "exact"
        )
        == 0
    )
    assert (
        triples.match(
            [triples.normalise_triple("JoAnn", "work_for", "the New York Times")], gold, "partial"
        )
        == 1
    )
    # the peer review's false positive: a different predicate over overlapping arguments
    assert (
        triples.match([triples.normalise_triple("Ann", "work_against", "York")], gold, "partial")
        == 0
    )
    assert (
        triples.match(
            [triples.normalise_triple("JoAnn", "work_against", "New York Times")], gold, "partial"
        )
        == 0
    )
    # inflection is forgiven, auxiliaries are ignored
    assert (
        triples.match(
            [("acme corp", "found in", "1999")],
            [("acme corp", "was founded in", "1999")],
            "partial",
        )
        == 1
    )


def test_one_to_one_and_duplicates_count_once():
    gold = [("a", "r", "b"), ("a", "r", "c")]
    pred = [("a", "r", "b"), ("a", "r", "b"), ("a", "r", "b")]
    assert triples.match(pred, gold, "exact") == 1
    assert triples.match(pred, gold, "partial") == 1
    assert triples.prf(1, 1, 2) == (1.0, 0.5, 2 / 3)


DOCS = pl.DataFrame(
    [("d1", "t", None, 0, None), ("d2", "t", None, 0, '{"entities": [{"text": "Bob"}]}')],
    schema=DOC_SCHEMA,
    orient="row",
)
CHUNKS = pl.DataFrame(
    [
        (1, "d1", None, 0, 0, 30, "Alice founded Acme in 1999."),
        (2, "d2", None, 0, 0, 20, "Acme hired Bob."),
    ],
    schema=CHUNK_SCHEMA,
    orient="row",
)
SPANS = [
    (1, 0, 5, "Alice", "PERSON", "entity", None, None),
    (1, 14, 18, "Acme", "ORG", "entity", None, None),
    (1, 22, 26, "1999", "DATE", "literal", "date", "1999-01-01"),
    (2, 0, 4, "Acme", "ORG", "entity", None, None),
    (2, 11, 14, "Bob", "PERSON", "entity", None, None),
]
CLAIMS = [
    (1, 0, 27, 0, 5, "found", 14, 18, "accepted", "active"),
    (1, 0, 27, 0, 5, "found_in", 22, 26, "accepted", "prep"),
    (2, 0, 15, 0, 4, "hire", 11, 14, "accepted", "active"),
]


def test_predicted_triples_and_document_scoring():
    ex = extract(CHUNKS, DOCS, FakeExtractor(SPANS, CLAIMS), 1)
    pred = triples.predicted(ex, CHUNKS)
    assert set(pred.rows()) == {
        ("d1", "Alice", "found", "Acme"),
        ("d1", "Alice", "found_in", "1999-01-01"),
        ("d2", "Acme", "hire", "Bob"),
    }
    gold = pl.DataFrame(
        [
            (None, "d1", "Alice", "founded", "Acme"),
            (None, "d1", "Alice", "founded in", "1999"),
            (None, "d2", "Acme", "employs", "Bob"),
            (None, "d2", "Bob", "works for", "Acme"),
        ],
        schema=TRIPLE_SCHEMA,
        orient="row",
    )
    s = triples.score(pred, gold, CHUNKS, pl.DataFrame(schema=QUESTION_SCHEMA))
    assert s["n_pred"] == 3 and s["n_gold"] == 4 and s["duplicate_rate"] == 0.0
    assert s["exact_recall"] == 0.0 and s["exact_precision"] == 0.0  # founded != found
    assert s["partial_recall"] == 0.5 and s["partial_precision"] == 2 / 3  # employs != hire
    assert triples.span_score(triples.predicted_spans(ex, CHUNKS), triples.gold_spans(DOCS)) == (
        1 / 4,
        1.0,
        0.4,
    )


def test_per_question_gold_scores_recall_only():
    ex = extract(CHUNKS, DOCS, FakeExtractor(SPANS, CLAIMS), 1)
    pred = triples.predicted(ex, CHUNKS)
    gold = pl.DataFrame(
        [("q1", None, "Acme", "hired", "Bob"), ("q1", None, "Alice", "born in", "Paris")],
        schema=TRIPLE_SCHEMA,
        orient="row",
    )
    questions = pl.DataFrame(
        [("q1", "?", "a", ["a"], [2], None, True, None, None)], schema=QUESTION_SCHEMA, orient="row"
    )
    s = triples.score(pred, gold, CHUNKS, questions)
    assert s["partial_recall"] == 0.5 and s["exact_recall"] == 0.0
    assert s["partial_precision"] is None and s["exact_f1"] is None


def test_review_regressions_in_scoring():
    # a false prediction in a document without gold counts against precision
    pred = pl.DataFrame(
        [("d1", "Alice", "founded", "Acme"), ("d9", "Bob", "founded", "Globex")],
        schema={
            "document_id": pl.Utf8,
            "subject": pl.Utf8,
            "predicate": pl.Utf8,
            "object": pl.Utf8,
        },
        orient="row",
    )
    gold = pl.DataFrame(
        [(None, "d1", "Alice", "founded", "Acme"), (None, "d1", "Alice", "founded", "Acme")],
        schema=TRIPLE_SCHEMA,
        orient="row",
    )
    s = triples.score(pred, gold, CHUNKS, pl.DataFrame(schema=QUESTION_SCHEMA))
    assert s["exact_precision"] == 0.5 and s["partial_precision"] == 0.5
    # duplicated gold counts once in both matchers
    assert s["exact_recall"] == 1.0 and s["partial_recall"] == 1.0
    assert (
        triples.match(
            [("alice", "like", "bob"), ("alice smith", "like", "bob")],
            [("alice", "likes", "bob")] * 2,
            "partial",
        )
        == 1
    )
    # two copulas are the same predicate
    assert (
        triples.match([("alice", "be", "chemist")], [("alice", "is a", "chemist")], "partial") == 1
    )
    assert (
        triples.match([("alice", "be", "chemist")], [("alice", "founded", "chemist")], "partial")
        == 0
    )
