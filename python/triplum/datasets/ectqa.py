"""ECT-QA (MIT): 480 earnings-call transcripts (384 for 2020-2023 under `old`, 96 for 2024 under
`new`) and 1,005 local questions with gold transcripts, 261 of them unanswerable. The 100 global
questions ship no gold answer and are not loaded. A transcript is one document, keyed by its
file name and read on access; its reporting quarter is a period, not an instant, so `observed_at`
stays 0 and the year, quarter and old/new split live in `documents.metadata` for an explicit
ingestion protocol.
"""

from __future__ import annotations

from pathlib import Path

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import Document, chunk_id
from triplum.datasets import base
from triplum.datasets.base import Entry, ListSource, passage
from triplum.datasets.files import File, manifest_files
from triplum.eval.inputs import GoldMappingError, Question
from triplum.settings import Settings

UNANSWERABLE = "unanswerable"
META = ("company_name", "stock_code", "sector", "year", "quarter", "token_count")


def document_id(filename: str) -> str:
    return f"ectqa:{filename}"


class Corpus(ListSource[tuple[str, Path], Document]):
    """One transcript file per record, decoded on access."""

    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or manifest_files("ectqa"), settings)

    def read(self, paths: dict[str, Path]) -> list[tuple[str, Path]]:
        return sorted((name, p) for name, p in paths.items() if "/data/" in name)

    def record(self, raw: tuple[str, Path], index: int) -> Document:
        name, path = raw
        split, filename = name.split("/")[-2:]
        t = base.read_json(path)
        meta = {k: t[k] for k in META}
        meta["split"] = split
        title = f"{t['company_name']} {t['year']} {t['quarter'].upper()} earnings call"
        return passage(document_id(filename), "ectqa", title, t["cleaned_content"], metadata=meta)


class Questions(ListSource[tuple[str, dict], Question]):
    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or manifest_files("ectqa"), settings)

    def read(self, paths: dict[str, Path]) -> list[tuple[str, dict]]:
        rows = []
        for split in ("old", "new"):
            for i, q in enumerate(base.read_json(self.path(f"local_questions_{split}.json"))):
                rows.append((f"ectqa:{split}:{i}", {**q, "split": split}))
        return rows

    def record(self, raw: tuple[str, dict], index: int) -> Question:
        qid, q = raw
        meta = {
            "split": q["split"],
            "reasoning_type": q["reasoning_type"],
            "num_hops": q["num_hops"],
            "evidence": q["evidence_list"],
        }
        if q["answer"] == UNANSWERABLE:
            return Question(
                id=qid,
                question=q["question"],
                answer=UNANSWERABLE,
                qtype=q["question_type"],
                answerable=False,
                metadata=meta,
            )
        names = [e["ect_filename"] for e in q["evidence_list"]]
        if not names:
            raise GoldMappingError(f"ectqa: question {qid} has no evidence")
        return Question(
            id=qid,
            question=q["question"],
            answer=q["answer"],
            gold=tuple(chunk_id(document_id(n), 0) for n in names),
            qtype=q["question_type"],
            metadata=meta,
        )


ENTRIES = (
    Entry(
        name="ectqa",
        family="temporal",
        licence="MIT",
        build=lambda s: Benchmark(name="ectqa", corpus=Corpus(s), qa=Questions(s)),
    ),
)
