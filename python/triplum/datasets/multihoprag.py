"""MultiHop-RAG (Tang and Yang, 2024; ODC-BY): 2,556 questions over 609 news articles, gold by
article URL, with 301 `null_query` questions whose expected answer is abstention. Articles carry a
publication timestamp, which becomes `observed_at`.
"""

from __future__ import annotations

import json
from pathlib import Path

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import CorpusBatch
from triplum.datasets import base
from triplum.datasets.base import Spec
from triplum.datasets.corpus import CorpusDataset
from triplum.datasets.frames import FrameDataset
from triplum.eval.inputs import QAEvaluation

ABSTAIN = "Insufficient information."


def parse(paths: dict[str, Path], n: int | None) -> Benchmark:
    questions_path = next(p for name, p in paths.items() if name.endswith("MultiHopRAG.json"))
    corpus_path = next(p for name, p in paths.items() if name.endswith("corpus.json"))
    articles = json.loads(corpus_path.read_text(encoding="utf-8"))
    by_url: dict[str, int] = {}
    passages = []
    for i, a in enumerate(articles):
        if a["url"] in by_url:
            raise base.GoldMappingError(f"multihoprag: duplicate article url {a['url']}")
        by_url[a["url"]] = i + 1
        meta = {k: a[k] for k in ("title", "author", "source", "category", "published_at", "url")}
        passages.append(
            (f"multihoprag:{i}", a["title"], a["body"], base.utc_us(a["published_at"]), meta)
        )
    documents, grants, chunks = base.corpus_frames("multihoprag", passages)
    documents = documents.with_columns(uri=documents["metadata"].str.json_path_match("$.url"))
    records = json.loads(questions_path.read_text(encoding="utf-8"))
    if n is not None:
        records = records[:n]
    rows = []
    for i, q in enumerate(records):
        qid = f"multihoprag:{i}"
        meta = {"evidence": q["evidence_list"]}
        if q["question_type"] == "null_query":
            rows.append(
                base.question_row(
                    qid,
                    q["query"],
                    ABSTAIN,
                    [],
                    [],
                    q["question_type"],
                    answerable=False,
                    metadata=meta,
                )
            )
            continue
        gold = base.resolve_gold("multihoprag", qid, [e["url"] for e in q["evidence_list"]], by_url)
        rows.append(
            base.question_row(
                qid, q["query"], q["answer"], [], gold, q["question_type"], metadata=meta
            )
        )
    return Benchmark(
        corpus=CorpusDataset(CorpusBatch(documents, grants, chunks)),
        qa=QAEvaluation(FrameDataset(base.questions_frame(rows))),
    )


SPECS = (Spec("multihoprag", "abstention", base.manifest_files("multihoprag"), "ODC-BY", parse),)
