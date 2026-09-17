"""TEMPO (CC BY 4.0): 1,730 temporal questions with per-hop gold document ids over a frozen
1.65M-document corpus in 13 domains, 2.4 GB of parquet, so it fetches only when named. One
document per row, keyed by the upstream id and streamed one parquet row group at a time. Gold
answers are long HTML passages, so EM and F1 are not meaningful here and Judge-Acc is the answer
metric; the per-step retrieval plan and time-scope annotations from `steps/` ride in `metadata`
for a later per-hop recall.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import Document, chunk_id
from triplum.datasets import base
from triplum.datasets.base import Entry, ListSource, Pinned, passage
from triplum.datasets.files import File, manifest_files
from triplum.eval.inputs import GoldMappingError, Question
from triplum.settings import Settings
from triplum.utils.data import IterableDataset

DOMAINS = (
    "bitcoin", "cardano", "economics", "genealogy", "history", "hsm", "iota", "law", "monero", "politics",
    "quant", "travel", "workplace",
)  # fmt: skip


def document_id(doc_id: str) -> str:
    return f"tempo:{doc_id}"


class Corpus(Pinned, IterableDataset[Document]):
    """Streams every domain's documents parquet by row group."""

    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or manifest_files("tempo"), settings)

    def __iter__(self) -> Iterator[Document]:
        for domain in DOMAINS:
            path = self.path(f"documents/{domain}.parquet")
            for row in base.parquet_rows(path, ["id", "content"]):
                yield passage(
                    document_id(row["id"]), "tempo", "", row["content"], metadata={"domain": domain}
                )


class Questions(ListSource[tuple[str, dict, dict], Question]):
    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or manifest_files("tempo"), settings)

    def read(self, paths: dict[str, Path]) -> list[tuple[str, dict, dict]]:
        rows = []
        for domain in DOMAINS:
            steps = {s["id"]: s for s in base.parquet_rows(self.path(f"steps/{domain}.parquet"))}
            for q in base.parquet_rows(self.path(f"examples/{domain}.parquet")):
                rows.append((domain, q, steps.get(q["id"], {})))
        return rows

    def record(self, raw: tuple[str, dict, dict], index: int) -> Question:
        domain, q, step = raw
        gold_ids = list(q["gold_ids"])
        if not gold_ids:
            raise GoldMappingError(f"tempo: question {q['id']} has no gold documents")
        meta = {
            "domain": domain,
            "negative_ids": list(q["negative_ids"]),
            "query_guidance": step.get("query_guidance"),
            "gold_passage_annotations": step.get("gold_passage_annotations"),
        }
        answers = list(q["gold_answers"])
        return Question(
            id=q["id"],
            question=q["query"],
            answer=answers[0],
            aliases=tuple(answers[1:]),
            gold=tuple(chunk_id(document_id(d), 0) for d in gold_ids),
            qtype=domain,
            metadata=meta,
        )


ENTRIES = (
    Entry(
        name="tempo",
        family="temporal",
        licence="CC BY 4.0",
        fixture=False,
        build=lambda s: Benchmark(name="tempo", corpus=Corpus(s), qa=Questions(s)),
    ),
)
