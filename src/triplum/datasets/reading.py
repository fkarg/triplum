"""Reading comprehension with the passage inline: SQuAD 1.1 and 2.0 validation (CC BY-SA 4.0)
and BoolQ validation (CC BY-SA 3.0). The corpus is the set of distinct passages, one document
each, streamed from the question rows; the gold chunk is the question's own passage, so
retrieval here measures finding a paragraph among a few thousand siblings from the same
articles. SQuAD 2.0 questions without an answer are unanswerable and keep their passage in
`metadata.candidate_chunk_ids`; BoolQ answers are `yes` or `no`.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import Document, chunk_id, content_id
from triplum.datasets import base
from triplum.datasets.base import Entry, InlineCorpus, ListSource, passage
from triplum.datasets.files import File, manifest_files
from triplum.eval.inputs import Question
from triplum.settings import Settings

UNANSWERABLE = "unanswerable"


def _passage(name: str, q: dict) -> tuple[str, str]:
    if name == "boolq":
        return "", q["passage"]
    return q["title"].replace("_", " "), q["context"]


class Corpus(InlineCorpus[dict]):
    def __init__(
        self, name: str, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        self.name = name
        super().__init__(files or manifest_files(name), settings, {"name": name})

    def records(self, paths: dict[str, Path]) -> Iterable[dict]:
        (path,) = paths.values()
        return base.parquet_rows(path)

    def documents(self, raw: dict) -> Iterable[Document]:
        title, text = _passage(self.name, raw)
        yield passage(content_id(title, text), self.name, title, text)


class Questions(ListSource[dict, Question]):
    def __init__(
        self, name: str, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        self.name = name
        super().__init__(files or manifest_files(name), settings, {"name": name})

    def read(self, paths: dict[str, Path]) -> list[dict]:
        (path,) = paths.values()
        return list(base.parquet_rows(path))

    def record(self, raw: dict, index: int) -> Question:
        q = raw
        cid = chunk_id(content_id(*_passage(self.name, q)), 0)
        meta = {"candidate_chunk_ids": [cid]}
        if self.name == "boolq":
            return Question(
                id=f"boolq:{index}",
                question=q["question"],
                answer="yes" if q["answer"] else "no",
                gold=(cid,),
                qtype="boolean",
                metadata=meta,
            )
        texts = list(dict.fromkeys(q["answers"]["text"]))
        if texts:
            return Question(
                id=q["id"],
                question=q["question"],
                answer=texts[0],
                aliases=tuple(texts[1:]),
                gold=(cid,),
                qtype="span",
                metadata=meta,
            )
        return Question(
            id=q["id"],
            question=q["question"],
            answer=UNANSWERABLE,
            qtype="span",
            answerable=False,
            metadata=meta,
        )


def _benchmark(name: str, settings: Settings) -> Benchmark:
    return Benchmark(name=name, corpus=Corpus(name, settings), qa=Questions(name, settings))


ENTRIES = (
    Entry(name="squad", family="reading", licence="CC BY-SA 4.0", build=lambda s: _benchmark("squad", s)),
    Entry(name="squad_v2", family="abstention", licence="CC BY-SA 4.0", build=lambda s: _benchmark("squad_v2", s)),
    Entry(name="boolq", family="reading", licence="CC BY-SA 3.0", build=lambda s: _benchmark("boolq", s)),
)  # fmt: skip
