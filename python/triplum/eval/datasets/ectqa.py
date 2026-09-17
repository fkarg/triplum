"""ECT-QA (MIT): 480 earnings-call transcripts (384 for 2020-2023 under `old`, 96 for 2024 under
`new`) and 1,005 local questions with gold transcripts, 261 of them unanswerable. The 100 global
questions ship no gold answer and are not loaded. A transcript is one document and one chunk; its
reporting quarter is a period, not an instant, so `observed_at` stays 0 and the year, quarter and
old/new split live in `documents.metadata` for an explicit ingestion protocol.
"""

from __future__ import annotations

import json
from pathlib import Path

from triplum.eval.datasets import base
from triplum.eval.datasets.base import Frames, Spec

UNANSWERABLE = "unanswerable"


def parse(paths: dict[str, Path], n: int | None) -> Frames:
    by_file: dict[str, int] = {}
    passages = []
    transcripts = sorted(name for name in paths if "/data/" in name)
    for i, name in enumerate(transcripts):
        split, filename = name.split("/")[-2:]
        t = json.loads(paths[name].read_text(encoding="utf-8"))
        by_file[filename] = i + 1
        meta = {
            k: t[k]
            for k in ("company_name", "stock_code", "sector", "year", "quarter", "token_count")
        }
        meta["split"] = split
        title = f"{t['company_name']} {t['year']} {t['quarter'].upper()} earnings call"
        passages.append((f"ectqa:{filename}", title, t["cleaned_content"], 0, meta))
    documents, grants, chunks = base.corpus_frames("ectqa", passages)
    rows = []
    for split in ("old", "new"):
        name = next(k for k in paths if k.endswith(f"local_questions_{split}.json"))
        for i, q in enumerate(json.loads(paths[name].read_text(encoding="utf-8"))):
            qid = f"ectqa:{split}:{i}"
            meta = {
                "split": split,
                "reasoning_type": q["reasoning_type"],
                "num_hops": q["num_hops"],
                "evidence": q["evidence_list"],
            }
            if q["answer"] == UNANSWERABLE:
                rows.append(
                    base.question_row(
                        qid,
                        q["question"],
                        UNANSWERABLE,
                        [],
                        [],
                        q["question_type"],
                        answerable=False,
                        metadata=meta,
                    )
                )
                continue
            gold = base.resolve_gold(
                "ectqa", qid, [e["ect_filename"] for e in q["evidence_list"]], by_file
            )
            rows.append(
                base.question_row(
                    qid, q["question"], q["answer"], [], gold, q["question_type"], metadata=meta
                )
            )
    if n is not None:
        rows = rows[:n]
    return Frames(
        base.questions_frame(rows), documents, grants, chunks, base.empty(base.TRIPLE_SCHEMA)
    )


SPECS = (Spec("ectqa", "temporal", base.manifest_files("ectqa"), "MIT", parse),)
