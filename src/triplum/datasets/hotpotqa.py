"""HotpotQA (Yang et al., 2018; CC BY-SA 4.0) as sampled by HippoRAG (MIT): 1,000 questions over
9,811 passages, the protocol of IRCoT and HippoRAG's published retrieval results."""

from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, TypeAdapter

from triplum.datasets.benchmark import QABenchmark
from triplum.datasets.files import datasets_home, fetch
from triplum.datatype import Source
from triplum.datatype.question import QAQuestion, QuestionInput, SpanEvidence
from triplum.utils.data import RecordDataset

BASE = "https://raw.githubusercontent.com/OSU-NLP-Group/HippoRAG/191f281122e2437743daf1dd2dae23059a14c088/reproduce/dataset/"
FILES = {
    "hotpotqa.json": "3ad9c0bcbf93f41d7004ca6007049c904d2605046b314a2f7ecfb379c64cba6d",
    "hotpotqa_corpus.json": "9333647b922382776cd2cb02893b390d77984df85a91bfa8be411284978aca7d",
}


class _Passage(BaseModel):
    title: str
    text: str


class _Question(BaseModel):
    id: str = Field(alias="_id")
    question: str
    answer: str
    supporting_facts: list[tuple[str, int]]
    context: list[tuple[str, list[str]]]
    type: str
    level: str


def download(root: Path | None = None) -> Path:
    """Fetch both pinned files into `root/hotpotqa` unless verified copies exist; return it.

    `root` defaults to `datasets_home()`.
    """
    root = datasets_home() if root is None else root
    folder = root / "hotpotqa"
    for name, sha256 in FILES.items():
        fetch(BASE + name, folder / name, sha256)
    return folder


class HotpotQA(QABenchmark):
    """The HippoRAG HotpotQA files, downloaded into `root` on first use (`download`).

    Each passage becomes a Source with text `title\\ntext` (HippoRAG's passage format); `origin`
    and `external_id` are its Wikipedia title, unique in this corpus. Evidence is one set per
    question: with `gold="sentence"` (HotpotQA's native supporting facts) one span per
    supporting sentence; with `gold="passage"` one span per supporting passage, covering its
    whole text, which is the gold HippoRAG's passage recall counts.

    Both files are verified, parsed and checked at construction. Raises `ValueError` if a
    download does not match its pinned hash, or a supporting fact names no passage or sentence.
    """

    def __init__(
        self, root: Path | None = None, *, gold: Literal["sentence", "passage"] = "sentence"
    ) -> None:
        folder = download(root)
        self._passages = TypeAdapter(list[_Passage]).validate_json(
            (folder / "hotpotqa_corpus.json").read_bytes()
        )
        texts = {p.title: p.text for p in self._passages}
        questions = TypeAdapter(list[_Question]).validate_json(
            (folder / "hotpotqa.json").read_bytes()
        )
        self._questions = RecordDataset([_convert(q, texts, gold) for q in questions])

    def corpus(self, collection_id: UUID, /) -> RecordDataset[Source]:
        return RecordDataset(
            [
                Source(
                    collection_id=collection_id,
                    origin=p.title,
                    text=f"{p.title}\n{p.text}",
                    external_id=p.title,
                )
                for p in self._passages
            ]
        )

    def questions(self) -> RecordDataset[QAQuestion]:
        return self._questions


def _convert(
    question: _Question, texts: dict[str, str], gold: Literal["sentence", "passage"]
) -> QAQuestion:
    sentences = dict(question.context)
    evidence: list[SpanEvidence] = []
    for title, index in question.supporting_facts:
        if title not in texts or not 0 <= index < len(sentences.get(title, [])):
            raise ValueError(f"question {question.id}: no passage sentence {title!r} #{index}")
        if "".join(sentences[title]) != texts[title]:
            raise ValueError(f"question {question.id}: sentences of {title!r} differ from corpus")
        offset = len(title) + 1  # Source text is title, newline, passage text
        if gold == "passage":
            span = SpanEvidence(document=title, start=0, end=offset + len(texts[title]))
        else:
            start = offset + sum(len(s) for s in sentences[title][:index])
            span = SpanEvidence(
                document=title, start=start, end=start + len(sentences[title][index])
            )
        if span not in evidence:
            evidence.append(span)
    return QAQuestion(
        id=question.id,
        input=QuestionInput(text=question.question),
        answers=[question.answer],
        evidence=[evidence],
        answerable=True,
        metadata={"type": question.type, "level": question.level},
    )
