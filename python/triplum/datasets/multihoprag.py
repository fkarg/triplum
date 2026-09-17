"""MultiHop-RAG (Tang and Yang, 2024; ODC-BY): 2,556 questions over 609 news articles, gold by
article URL, with 301 `null_query` questions whose expected answer is abstention. Articles carry a
publication timestamp, which becomes `observed_at`; the URL is the document key and its `uri`.
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

ABSTAIN = "Insufficient information."
META = ("title", "author", "source", "category", "published_at", "url")


def document_id(url: str) -> str:
    return f"multihoprag:{url}"


class Corpus(ListSource[dict, Document]):
    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or manifest_files("multihoprag"), settings)

    def read(self, paths: dict[str, Path]) -> list[dict]:
        return base.read_json(self.path("corpus.json"))

    def record(self, raw: dict, index: int) -> Document:
        a = raw
        return passage(
            document_id(a["url"]),
            "multihoprag",
            a["title"],
            a["body"],
            uri=a["url"],
            observed_at=base.utc_us(a["published_at"]),
            metadata={k: a[k] for k in META},
        )


class Questions(ListSource[dict, Question]):
    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or manifest_files("multihoprag"), settings)

    def read(self, paths: dict[str, Path]) -> list[dict]:
        return base.read_json(self.path("MultiHopRAG.json"))

    def record(self, raw: dict, index: int) -> Question:
        q = raw
        qid = f"multihoprag:{index}"
        meta = {"evidence": q["evidence_list"]}
        if q["question_type"] == "null_query":
            return Question(
                id=qid,
                question=q["query"],
                answer=ABSTAIN,
                qtype=q["question_type"],
                answerable=False,
                metadata=meta,
            )
        urls = [e["url"] for e in q["evidence_list"]]
        if not urls:
            raise GoldMappingError(f"multihoprag: question {qid} has no evidence")
        return Question(
            id=qid,
            question=q["query"],
            answer=q["answer"],
            gold=tuple(chunk_id(document_id(u), 0) for u in urls),
            qtype=q["question_type"],
            metadata=meta,
        )


ENTRIES = (
    Entry(
        name="multihoprag",
        family="abstention",
        licence="ODC-BY",
        build=lambda s: Benchmark(name="multihoprag", corpus=Corpus(s), qa=Questions(s)),
    ),
)
