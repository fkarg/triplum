"""LongMemEval-cleaned, `s` variant (MIT): 500 questions, each with its own haystack of about 48
dated chat sessions and the sessions that answer it; 30 `_abs` questions expect abstention. A
session is one document and one chunk, namespaced by question because haystacks overlap by session
id without being the same corpus; the session date (no zone, read as UTC) is `observed_at` and the
question date is `as_of`. The store indexes every haystack at once, so the dataset is declared
`needs` until the runner scopes the corpus per question.
"""

from __future__ import annotations

import json
from pathlib import Path

from triplum.eval.datasets import base
from triplum.eval.datasets.base import Frames, Spec

DATE_FMT = "%Y/%m/%d (%a) %H:%M"
NEEDS = "a corpus scoped per question (each question has its own haystack)"


def parse(paths: dict[str, Path], n: int | None) -> Frames:
    (path,) = paths.values()
    records = json.loads(path.read_text(encoding="utf-8"))
    if n is not None:
        records = records[:n]
    passages, rows = [], []
    for q in records:
        qid = q["question_id"]
        gold = []
        for i, (sid, date, turns) in enumerate(
            zip(q["haystack_session_ids"], q["haystack_dates"], q["haystack_sessions"])
        ):
            cid = len(passages) + 1
            text = "\n".join(f"{t['role']}: {t['content']}" for t in turns)
            meta = {
                "question_id": qid,
                "session_id": sid,
                "date": date,
                "answer_turns": [j for j, t in enumerate(turns) if t.get("has_answer")],
            }
            passages.append(
                (f"longmemeval_s:{qid}/{i}", sid, text, base.utc_us(date, DATE_FMT), meta)
            )
            if sid in q["answer_session_ids"]:
                gold.append(cid)
        answerable = not qid.endswith("_abs")
        if answerable and not gold:
            raise base.GoldMappingError(
                f"longmemeval_s: question {qid} answer sessions not in haystack"
            )
        rows.append(
            base.question_row(
                qid,
                q["question"],
                q["answer"],
                [],
                gold if answerable else [],
                q["question_type"],
                answerable=answerable,
                as_of=base.utc_us(q["question_date"], DATE_FMT),
                metadata={
                    "question_date": q["question_date"],
                    "answer_session_ids": q["answer_session_ids"],
                },
            )
        )
    return Frames(
        base.questions_frame(rows),
        *base.corpus_frames("longmemeval_s", passages),
        base.empty(base.TRIPLE_SCHEMA),
    )


SPECS = (
    Spec(
        "longmemeval_s", "memory", base.manifest_files("longmemeval_s"), "MIT", parse, needs=NEEDS
    ),
)
