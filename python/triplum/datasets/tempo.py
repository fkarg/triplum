"""TEMPO (CC BY 4.0): 1,730 temporal questions with per-hop gold document ids over a frozen
1.65M-document corpus in 13 domains, 2.4 GB of parquet, so it fetches only when named. One document
is one chunk. Gold answers are long HTML passages, so EM and F1 are not meaningful here and Judge-Acc
is the answer metric; the per-step retrieval plan and time-scope annotations from `steps/` ride in
`metadata` for a later per-hop recall.
"""

from __future__ import annotations

import polars as pl

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import CorpusBatch
from triplum.datasets import base
from triplum.datasets.base import Spec
from triplum.datasets.corpus import CorpusDataset
from triplum.datasets.frames import FrameDataset
from triplum.eval.inputs import QAEvaluation

DOMAINS = (
    "bitcoin", "cardano", "economics", "genealogy", "history", "hsm", "iota", "law", "monero", "politics",
    "quant", "travel", "workplace",
)  # fmt: skip


def parse(paths, n: int | None) -> Benchmark:
    def path(kind: str, domain: str):
        return paths[f"tempo/{kind}/{domain}.parquet"]

    by_doc: dict[str, int] = {}
    passages = []
    for domain in DOMAINS:
        docs = pl.read_parquet(path("documents", domain), columns=["id", "content"])
        for doc_id, content in docs.iter_rows():
            if doc_id in by_doc:
                raise base.GoldMappingError(f"tempo: duplicate document id {doc_id}")
            by_doc[doc_id] = len(passages) + 1
            passages.append((f"tempo:{doc_id}", "", content, 0, {"domain": domain}))
    rows = []
    for domain in DOMAINS:
        steps = {s["id"]: s for s in pl.read_parquet(path("steps", domain)).iter_rows(named=True)}
        for q in pl.read_parquet(path("examples", domain)).iter_rows(named=True):
            gold = base.resolve_gold("tempo", q["id"], list(q["gold_ids"]), by_doc)
            step = steps.get(q["id"], {})
            meta = {
                "domain": domain,
                "negative_ids": list(q["negative_ids"]),
                "query_guidance": step.get("query_guidance"),
                "gold_passage_annotations": step.get("gold_passage_annotations"),
            }
            answers = list(q["gold_answers"])
            rows.append(
                base.question_row(
                    q["id"], q["query"], answers[0], answers[1:], gold, domain, metadata=meta
                )
            )
    if n is not None:
        rows = rows[:n]
    return Benchmark(
        corpus=CorpusDataset(CorpusBatch(*base.corpus_frames("tempo", passages))),
        qa=QAEvaluation(FrameDataset(base.questions_frame(rows))),
    )


SPECS = (
    Spec("tempo", "temporal", base.manifest_files("tempo"), "CC BY 4.0", parse, fixture=False),
)
