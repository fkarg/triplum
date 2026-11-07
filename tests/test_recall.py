import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import TypeAdapter, ValidationError

from triplum.datatype import (
    Chunk,
    DocumentEvidence,
    QAQuestion,
    QuestionInput,
    RetrievalHit,
    SpanEvidence,
)
from triplum.evaluation.recall import (
    RecallAtK,
    ResolvedDocument,
    ResolvedEvidence,
    ResolvedSpan,
    resolve_evidence,
    score_recall,
    summarize_recall,
)

COLLECTION = UUID("01900000-0000-7000-8000-000000000001")
A = UUID("01900000-0000-7000-8000-00000000000a")
B = UUID("01900000-0000-7000-8000-00000000000b")
C = UUID("01900000-0000-7000-8000-00000000000c")


def _hit(source_id: UUID, start: int, end: int, ordinal: int = 0) -> RetrievalHit:
    chunk = Chunk(
        collection_id=COLLECTION,
        source_id=source_id,
        origin=str(source_id),
        ordinal=ordinal,
        start=start,
        text="x" * (end - start),
    )
    return RetrievalHit(chunk=chunk, score=None)


def _span(source_id: UUID, start: int, end: int) -> ResolvedSpan:
    return ResolvedSpan(source_id=source_id, start=start, end=end)


def _recall(hits, evidence, k: int = 5) -> RecallAtK:
    return score_recall(hits, evidence, ks=[k])[k]


@pytest.mark.parametrize(
    ("hits", "covered"),
    [
        ([_hit(A, 0, 4), _hit(A, 4, 10, 1)], True),  # adjacent chunks
        ([_hit(A, 2, 8), _hit(A, 0, 6), _hit(A, 5, 12, 1)], True),  # overlapping, unsorted
        ([_hit(A, 0, 4), _hit(A, 5, 10, 1)], False),  # one-character gap at 4
        ([_hit(A, 0, 9)], False),  # one character short of the end
        ([_hit(A, 0, 4), _hit(B, 4, 10)], False),  # the rest is in another source
    ],
    ids=["adjacent", "overlapping", "gap", "short", "other-source"],
)
def test_a_span_counts_only_when_its_source_chunks_cover_all_of_it(hits, covered):
    assert _recall(hits, [[_span(A, 0, 10)]]).recall == (1.0 if covered else 0.0)


def test_document_evidence_needs_any_chunk_of_its_source():
    evidence: list[list[ResolvedEvidence]] = [[ResolvedDocument(source_id=A)]]
    assert _recall([_hit(B, 0, 5), _hit(A, 7, 8)], evidence).recall == 1.0
    assert _recall([_hit(B, 0, 5)], evidence).recall == 0.0


def test_the_best_alternative_set_wins_and_sets_never_pool():
    first = [_span(A, 0, 10), ResolvedDocument(source_id=B), _span(C, 0, 5)]
    second = [ResolvedDocument(source_id=C), _span(A, 20, 30)]
    # first: A and B covered (2/3); second: C covered, A[20,30) not (1/2).
    score = _recall([_hit(A, 0, 10), _hit(B, 0, 1), _hit(C, 7, 9)], [first, second])
    assert score == RecallAtK(recall=2 / 3, all_gold=False, retrieved_characters=13)
    full = _recall([_hit(C, 0, 1), _hit(A, 20, 30)], [first, second])
    assert (full.recall, full.all_gold) == (1.0, True)


def test_only_the_first_k_hits_count():
    hits = [_hit(B, 0, 3), _hit(B, 3, 6, 1), _hit(A, 0, 10)]
    scores = score_recall(hits, [[_span(A, 0, 10)]], ks=[2, 3])
    assert scores == {
        2: RecallAtK(recall=0.0, all_gold=False, retrieved_characters=6),
        3: RecallAtK(recall=1.0, all_gold=True, retrieved_characters=16),
    }


def test_overlapping_hits_count_their_characters_once():
    hits = [_hit(A, 0, 10), _hit(A, 5, 15, 1), _hit(B, 0, 10)]
    assert _recall(hits, []).retrieved_characters == 25


def test_questions_without_gold_have_no_recall_but_characters():
    assert _recall([_hit(A, 0, 4)], []) == RecallAtK(
        recall=None, all_gold=None, retrieved_characters=4
    )


@pytest.mark.parametrize("ks", [[0], [2, -1]])
def test_k_below_one_raises(ks):
    with pytest.raises(ValueError, match="every k must be at least 1"):
        score_recall([], [], ks=ks)


def test_resolve_evidence_maps_keys_and_keeps_kinds():
    question = QAQuestion(
        id="q1",
        input=QuestionInput(text="?"),
        answers=["a"],
        evidence=[
            [SpanEvidence(document="doc-a", start=1, end=3), DocumentEvidence(document="doc-b")]
        ],
        answerable=True,
    )
    assert resolve_evidence(question, {"doc-a": A, "doc-b": B}) == [
        [_span(A, 1, 3), ResolvedDocument(source_id=B)]
    ]
    with pytest.raises(KeyError, match="question 'q1': unknown document key 'doc-b'"):
        resolve_evidence(question, {"doc-a": A})


def test_an_invalid_span_is_rejected_not_read_as_a_document():
    adapter = TypeAdapter(ResolvedEvidence)
    with pytest.raises(ValidationError):
        adapter.validate_python({"source_id": str(A), "start": 3, "end": 3})


def test_summaries_exclude_or_zero_questions_without_gold():
    scores = [
        RecallAtK(recall=1.0, all_gold=True, retrieved_characters=10),
        RecallAtK(recall=0.5, all_gold=False, retrieved_characters=20),
        RecallAtK(recall=None, all_gold=None, retrieved_characters=60),
    ]
    excluded = summarize_recall(scores)
    assert (excluded.recall, excluded.all_gold, excluded.denominator) == (0.75, 0.5, 2)
    zero = summarize_recall(scores, no_gold="zero")
    assert (zero.recall, zero.all_gold, zero.denominator) == (0.5, pytest.approx(1 / 3), 3)
    for summary in (excluded, zero):
        assert (summary.questions, summary.no_gold, summary.retrieved_characters) == (3, 1, 30)


def test_summaries_of_nothing_have_no_means():
    summary = summarize_recall([])
    assert (summary.recall, summary.all_gold, summary.retrieved_characters) == (None, None, None)
    assert (
        summarize_recall([RecallAtK(recall=None, all_gold=None, retrieved_characters=0)]).recall
        is None
    )


def test_bm25_recall_example_on_the_hotpotqa_fixture():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(root / "examples" / "bm25_recall.py"),
            str(root / "tests/fixtures/hotpotqa.json"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.splitlines() == [
        "R@2 0.600  AR@2 0.300  chars 968  (20 of 20 questions with gold)",
        "R@5 0.775  AR@5 0.600  chars 2639  (20 of 20 questions with gold)",
    ]
