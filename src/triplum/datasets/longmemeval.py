"""LongMemEval-cleaned, `s` variant (MIT): 500 questions, each with its own haystack of about 48
dated chat sessions and the sessions that answer it; 30 `_abs` questions expect abstention. A
session is one document, keyed by question and haystack index because haystacks overlap by
session id without being the same corpus; the session date (no zone, read as UTC) is
`observed_at` and the question date is `as_of`. The file is one 277 MB JSON list, so the corpus
stream and the question source each decode it once on first use; when the runner can scope a
corpus per question this source streams instead. The store indexes every haystack at once, so the
dataset is declared `needs` until the runner scopes the corpus per question.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import Document, chunk_id
from triplum.datasets import base
from triplum.datasets.base import Entry, InlineCorpus, ListSource, passage
from triplum.datasets.files import File, manifest_files
from triplum.eval.inputs import GoldMappingError, Question
from triplum.settings import Settings

DATE_FMT = "%Y/%m/%d (%a) %H:%M"
NEEDS = "a corpus scoped per question (each question has its own haystack)"


def document_id(question_id: str, index: int) -> str:
    return f"longmemeval_s:{question_id}/{index}"


class Corpus(InlineCorpus[dict]):
    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or manifest_files("longmemeval_s"), settings)

    def records(self, paths: dict[str, Path]) -> Iterable[dict]:
        (path,) = paths.values()
        return base.read_json(path)

    def documents(self, raw: dict) -> Iterable[Document]:
        q = raw
        qid = q["question_id"]
        for i, (sid, date, turns) in enumerate(
            zip(q["haystack_session_ids"], q["haystack_dates"], q["haystack_sessions"])
        ):
            meta = {
                "question_id": qid,
                "session_id": sid,
                "date": date,
                "answer_turns": [j for j, t in enumerate(turns) if t.get("has_answer")],
            }
            yield passage(
                document_id(qid, i),
                "longmemeval_s",
                sid,
                "\n".join(f"{t['role']}: {t['content']}" for t in turns),
                observed_at=base.utc_us(date, DATE_FMT),
                metadata=meta,
            )


class Questions(ListSource[dict, Question]):
    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or manifest_files("longmemeval_s"), settings)

    def read(self, paths: dict[str, Path]) -> list[dict]:
        (path,) = paths.values()
        return base.read_json(path)

    def record(self, raw: dict, index: int) -> Question:
        q = raw
        qid = q["question_id"]
        answerable = not qid.endswith("_abs")
        gold = tuple(
            chunk_id(document_id(qid, i), 0)
            for i, sid in enumerate(q["haystack_session_ids"])
            if sid in q["answer_session_ids"]
        )
        if answerable and not gold:
            raise GoldMappingError(f"longmemeval_s: question {qid} answer sessions not in haystack")
        return Question(
            id=qid,
            question=q["question"],
            answer=q["answer"],
            gold=gold if answerable else (),
            qtype=q["question_type"],
            answerable=answerable,
            as_of=base.utc_us(q["question_date"], DATE_FMT),
            metadata={
                "question_date": q["question_date"],
                "answer_session_ids": q["answer_session_ids"],
            },
        )


ENTRIES = (
    Entry(
        name="longmemeval_s",
        family="memory",
        licence="MIT",
        needs=NEEDS,
        build=lambda s: Benchmark(name="longmemeval_s", corpus=Corpus(s), qa=Questions(s)),
    ),
)
