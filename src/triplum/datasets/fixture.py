"""Legacy `tests/fixtures/<name>.json` files as `QABenchmark`s, read in place."""

from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, JsonValue

from triplum.datasets.benchmark import QABenchmark
from triplum.datatype import Source
from triplum.datatype.question import QAQuestion, QuestionInput, SpanEvidence
from triplum.utils.cache import content_key
from triplum.utils.data import RecordDataset


class _Segment(BaseModel):
    ordinal: int
    start: int
    end: int


class _Document(BaseModel):
    id: str
    text: str
    segments: list[_Segment]


class _Question(BaseModel):
    id: str
    question: str
    answer: str
    aliases: list[str]
    gold: list[int]
    qtype: str | None
    answerable: bool
    as_of: int | None
    metadata: dict[str, JsonValue]


class _File(BaseModel):
    documents: list[_Document] = []
    questions: list[_Question] = []


def legacy_chunk_id(document_id: str, ordinal: int) -> int:
    """The integer id the legacy fixtures use as gold for a document segment."""
    return int(content_key("chunk", [document_id, ordinal])[:15], 16)


class LegacyFixture(QABenchmark):
    """A legacy fixture file, with gold decoded to the paragraph spans it names.

    The file is parsed once at construction; later edits need a new instance. Each document
    becomes a Source whose `origin` and `external_id` are the legacy document id. Each legacy
    gold id names a stored segment (by its stored ordinal, not its list position) and becomes that
    segment's `SpanEvidence`; all of a question's gold forms one evidence set. Grants, `observed_at` and
    per-question candidate restrictions are not carried; the latter stay in `metadata`.

    Raises `ValueError` for duplicate ids, unresolved gold or spans outside their document.
    """

    def __init__(self, path: Path) -> None:
        data = _File.model_validate_json(path.read_bytes())
        self._documents = data.documents
        if len({document.id for document in self._documents}) != len(self._documents):
            raise ValueError(f"{path}: duplicate document ids")
        spans: dict[int, SpanEvidence] = {}
        for document in self._documents:
            for segment in document.segments:
                key = legacy_chunk_id(document.id, segment.ordinal)
                if key in spans:
                    raise ValueError(f"{path}: duplicate segment id {key}")
                if segment.end > len(document.text):
                    raise ValueError(f"{path}: segment {key} ends past document {document.id}")
                spans[key] = SpanEvidence(
                    document=document.id, start=segment.start, end=segment.end
                )
        questions = [_convert(question, spans, path) for question in data.questions]
        if len({question.id for question in questions}) != len(questions):
            raise ValueError(f"{path}: duplicate question ids")
        self._questions = RecordDataset(questions)

    def corpus(self, collection_id: UUID, /) -> RecordDataset[Source]:
        return RecordDataset(
            [
                Source(
                    collection_id=collection_id,
                    origin=document.id,
                    text=document.text,
                    external_id=document.id,
                )
                for document in self._documents
            ]
        )

    def questions(self) -> RecordDataset[QAQuestion]:
        return self._questions


def _convert(question: _Question, spans: dict[int, SpanEvidence], path: Path) -> QAQuestion:
    missing = [gold for gold in question.gold if gold not in spans]
    if missing:
        raise ValueError(f"{path}: question {question.id} has unresolved gold {missing}")
    metadata: dict[str, JsonValue] = {**question.metadata, "qtype": question.qtype}
    if question.as_of is not None:
        metadata["as_of"] = question.as_of
    return QAQuestion(
        id=question.id,
        input=QuestionInput(text=question.question),
        answers=list(dict.fromkeys([question.answer, *question.aliases])),
        evidence=[[spans[gold] for gold in question.gold]] if question.gold else [],
        answerable=question.answerable,
        metadata=metadata,
    )
