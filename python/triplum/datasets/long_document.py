"""Question sets over long documents. QuALITY v1.0.1 dev (CC BY 4.0 annotations; each article
carries its own licence field, mostly Project Gutenberg): 115 articles of 2,000-8,000 words, one
chunk each (230 article sets share them), and 2,086 four-option questions scored on the gold option's text with its 1-based
number as an alias. QASPER v0.3 test (CC BY 4.0): 416 NLP papers, chunked into abstract,
paragraphs and figure or table captions, and 1,451 questions whose gold chunks are the annotated
evidence paragraphs. 78 QASPER questions whose evidence is only table content or a partial
highlight match no chunk and are not loaded; the answer is the first answerable annotation's,
with the other annotations' answers as aliases.
"""

from __future__ import annotations

import json
import tarfile
import zipfile
from pathlib import Path

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import CorpusBatch
from triplum.datasets import base
from triplum.datasets.base import Spec
from triplum.datasets.corpus import CorpusDataset
from triplum.datasets.frames import FrameDataset
from triplum.eval.inputs import QAEvaluation

UNANSWERABLE = "unanswerable"
QUALITY_MEMBER = "QuALITY.v1.0.1.htmlstripped.dev"
QASPER_MEMBER = "qasper-test-v0.3.json"


def parse_quality(paths: dict[str, Path], n: int | None) -> Benchmark:
    (path,) = paths.values()
    with zipfile.ZipFile(path) as zf:
        articles = [json.loads(line) for line in zf.read(QUALITY_MEMBER).decode().splitlines()]
    corpus = base.Corpus("quality")
    rows = []
    for a in articles:
        meta = {
            k: a[k] for k in ("title", "article_id", "source", "year", "author", "topic", "license")
        }
        cid = corpus.add(a["title"], a["article"], meta=meta)
        for q in a["questions"]:
            gold = q["gold_label"]
            rows.append(
                base.question_row(
                    q["question_unique_id"],
                    q["question"],
                    q["options"][gold - 1],
                    [str(gold)],
                    [cid],
                    "hard" if q["difficult"] else "easy",
                    metadata={"options": q["options"], "gold_label": gold},
                )
            )
    if n is not None:
        rows = rows[:n]
    return Benchmark(
        corpus=CorpusDataset(CorpusBatch(*corpus.frames())),
        qa=QAEvaluation(FrameDataset(base.questions_frame(rows))),
    )


def _qasper_answer(answer: dict) -> str:
    if answer["yes_no"] is not None:
        return "yes" if answer["yes_no"] else "no"
    if answer["extractive_spans"]:
        return ", ".join(s.strip() for s in answer["extractive_spans"])
    return answer["free_form_answer"].strip()


def parse_qasper(paths: dict[str, Path], n: int | None) -> Benchmark:
    (path,) = paths.values()
    with tarfile.open(path) as tf:
        member = tf.extractfile(QASPER_MEMBER)
        assert member is not None
        papers = json.load(member)
    docs, rows = [], []
    next_cid = 1
    for pid, p in papers.items():
        texts = [f"{p['title']}\n{p['abstract']}"]
        by_text = {p["abstract"]: next_cid}
        for section in p["full_text"]:
            for para in section["paragraphs"]:
                by_text.setdefault(para, next_cid + len(texts))
                texts.append(f"{section['section_name']}\n{para}")
        for fig in p["figures_and_tables"]:
            by_text.setdefault(fig["caption"], next_cid + len(texts))
            texts.append(fig["caption"])
        docs.append((f"qasper:{pid}", texts, 0, {"title": p["title"]}))
        next_cid += len(texts)
        for qa in p["qas"]:
            answers = [a["answer"] for a in qa["answers"]]
            answerable = [a for a in answers if not a["unanswerable"]]
            gold = sorted({by_text[e] for a in answers for e in a["evidence"] if e in by_text})
            meta = {"answers": answers, "candidate_chunk_ids": [by_text[p["abstract"]]]}
            if not answerable:
                rows.append(
                    base.question_row(
                        qa["question_id"],
                        qa["question"],
                        UNANSWERABLE,
                        [],
                        gold,
                        "unanswerable",
                        answerable=False,
                        metadata=meta,
                    )
                )
            elif gold:
                first, *others = (_qasper_answer(a) for a in answerable)
                rows.append(
                    base.question_row(
                        qa["question_id"],
                        qa["question"],
                        first,
                        others + [s.strip() for s in answerable[0]["extractive_spans"]],
                        gold,
                        "yes_no" if answerable[0]["yes_no"] is not None else "free_form",
                        metadata=meta,
                    )
                )
    if n is not None:
        rows = rows[:n]
    return Benchmark(
        corpus=CorpusDataset(CorpusBatch(*base.document_frames("qasper", docs))),
        qa=QAEvaluation(FrameDataset(base.questions_frame(rows))),
    )


SPECS = (
    Spec(
        "quality",
        "long_context",
        base.manifest_files("quality"),
        "CC BY 4.0 (annotations; per-article licence in document metadata)",
        parse_quality,
    ),
    Spec("qasper", "long_context", base.manifest_files("qasper"), "CC BY 4.0", parse_qasper),
)
