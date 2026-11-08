import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from triplum.datasets.fixture import LegacyFixture, legacy_chunk_id
from triplum.datatype.question import DocumentEvidence, QAQuestion, QuestionInput, SpanEvidence

FIXTURES = Path(__file__).parent / "fixtures"
COLLECTION = UUID("01900000-0000-7000-8000-000000000001")
OTHER = UUID("01900000-0000-7000-8000-000000000002")


def question(**fields) -> QAQuestion:
    return QAQuestion.model_validate(
        {
            "id": "q",
            "input": {"text": "Who?"},
            "answers": ["A"],
            "evidence": [],
            "answerable": True,
        }
        | fields
    )


def legacy_file(tmp_path: Path, *, documents, questions) -> Path:
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps({"documents": documents, "questions": questions}))
    return path


def legacy_question(**fields) -> dict:
    return {
        "id": "q1",
        "question": "Who?",
        "answer": "Ann",
        "aliases": [],
        "gold": [],
        "qtype": "bridge",
        "answerable": True,
        "as_of": None,
        "metadata": {},
    } | fields


def test_question_input_carries_no_gold():
    # Guard: adding a field to the public input must be a deliberate change to this rule.
    assert set(QuestionInput.model_fields) == {"text"}


def test_evidence_union_keeps_valid_spans_and_documents():
    parsed = question(
        evidence=[[{"document": "d", "start": 3, "end": 4}], [{"document": "e"}]]
    ).evidence
    assert parsed == [
        [SpanEvidence(document="d", start=3, end=4)],
        [DocumentEvidence(document="e")],
    ]


@pytest.mark.parametrize(
    "span",
    [
        {"document": "d", "start": 3, "end": 3},
        {"document": "d", "start": 5, "end": 3},
        {"document": "d", "start": -1, "end": 2},
        {"document": "d", "start": 3},
    ],
)
def test_invalid_span_is_rejected_not_read_as_document_evidence(span):
    # An invalid span used to validate as DocumentEvidence through the union, losing its offsets.
    with pytest.raises(ValidationError):
        question(evidence=[[span]])


def test_empty_evidence_set_is_rejected():
    # [[]] would be satisfied by retrieving nothing; [] (no gold) remains valid.
    with pytest.raises(ValidationError, match="empty evidence set"):
        question(evidence=[[{"document": "d"}], []])
    assert question(evidence=[]).evidence == []


def test_all_fixture_gold_decodes_to_spans_inside_documents():
    questions = evidence = 0
    for path in sorted(FIXTURES.glob("*.json")):
        fixture = LegacyFixture(path)
        texts = {source.origin: source.text for source in fixture.corpus(COLLECTION)}
        for item in fixture.questions():
            questions += 1
            for alternative in item.evidence:
                for span in alternative:
                    evidence += 1
                    assert isinstance(span, SpanEvidence)
                    assert span.end <= len(texts[span.document])
    assert (questions, evidence) == (540, 704)


def test_hotpotqa_question_maps_to_one_set_of_two_paragraphs():
    fixture = LegacyFixture(FIXTURES / "hotpotqa.json")
    first = fixture.questions()[0]
    assert first.input == QuestionInput(text="what is one of the stars of  The Newcomers known for")
    assert first.evidence == [
        [
            SpanEvidence(document="8a9695ac21cfb24cc673", start=0, end=293),
            SpanEvidence(document="4c30d3dbd568c7c2f81a", start=0, end=396),
        ]
    ]
    corpus = list(fixture.corpus(COLLECTION))
    assert len(corpus) == 234
    assert all(source.external_id == source.origin for source in corpus)


def test_gold_names_the_stored_ordinal_not_the_list_position(tmp_path):
    documents = [
        {
            "id": "doc",
            "text": "first. second.",
            "segments": [
                {"ordinal": 1, "start": 7, "end": 14},
                {"ordinal": 0, "start": 0, "end": 6},
            ],
        }
    ]
    path = legacy_file(
        tmp_path,
        documents=documents,
        questions=[legacy_question(gold=[legacy_chunk_id("doc", 1)])],
    )
    assert LegacyFixture(path).questions()[0].evidence == [
        [SpanEvidence(document="doc", start=7, end=14)]
    ]


def test_question_fields_are_converted(tmp_path):
    raw = legacy_question(
        aliases=["Anne", "Ann", "Anne"], as_of=5, metadata={"choices": ["x"]}, answerable=False
    )
    path = legacy_file(tmp_path, documents=[], questions=[raw, legacy_question(id="q2")])
    first, second = LegacyFixture(path).questions()
    assert first == QAQuestion(
        id="q1",
        input=QuestionInput(text="Who?"),
        answers=["Ann", "Anne"],
        evidence=[],
        answerable=False,
        metadata={"choices": ["x"], "qtype": "bridge", "as_of": 5},
    )
    assert "as_of" not in second.metadata


@pytest.mark.parametrize(
    ("documents", "questions", "message"),
    [
        ([], [legacy_question(gold=[7])], "unresolved gold"),
        ([], [legacy_question(), legacy_question()], "duplicate question ids"),
        (
            [{"id": "d", "text": "abc", "segments": [{"ordinal": 0, "start": 0, "end": 4}]}],
            [],
            "ends past document",
        ),
        (
            [
                {
                    "id": "d",
                    "text": "abc",
                    "segments": [
                        {"ordinal": 0, "start": 0, "end": 1},
                        {"ordinal": 0, "start": 1, "end": 2},
                    ],
                }
            ],
            [],
            "duplicate segment id",
        ),
        (
            [
                {"id": "d", "text": "abc", "segments": []},
                {"id": "d", "text": "xyz", "segments": []},
            ],
            [],
            "duplicate document ids",
        ),
    ],
)
def test_inconsistent_fixtures_raise(tmp_path, documents, questions, message):
    path = legacy_file(tmp_path, documents=documents, questions=questions)
    with pytest.raises(ValueError, match=message):
        LegacyFixture(path)


def test_fingerprints_follow_content_and_collection(tmp_path):
    documents = [{"id": "d", "text": "abc", "segments": [{"ordinal": 0, "start": 0, "end": 3}]}]
    gold = [legacy_chunk_id("d", 0)]
    path = legacy_file(tmp_path, documents=documents, questions=[legacy_question(gold=gold)])
    fixture = LegacyFixture(path)
    # Formatting-only edits keep identity: it follows the decoded records, not the file bytes.
    path.write_text(json.dumps(json.loads(path.read_text()), indent=2))
    reformatted = LegacyFixture(path)
    assert reformatted.questions().fingerprint() == fixture.questions().fingerprint()
    assert reformatted.corpus(COLLECTION).fingerprint() == fixture.corpus(COLLECTION).fingerprint()
    assert fixture.corpus(OTHER).fingerprint() != fixture.corpus(COLLECTION).fingerprint()

    without_gold = legacy_file(tmp_path, documents=documents, questions=[legacy_question()])
    assert (
        LegacyFixture(without_gold).questions().fingerprint() != fixture.questions().fingerprint()
    )
