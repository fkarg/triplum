"""HotpotQA-style multi-hop QA sets that ship each question's candidate paragraphs inline: the
official HotpotQA distractor dev set, the 2WikiMultiHopQA dev set (with gold `evidences`
triples), the MuSiQue full dev set with its unanswerable twins, and MoreHopQA (verified split,
with a gold reasoning chain). The corpus is the union of the inline paragraphs, one chunk per
distinct (title, text); gold titles are resolved inside the question's own context, so a title
shared by two different paragraphs cannot be mis-assigned.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import CorpusBatch
from triplum.datasets import base
from triplum.datasets.base import Spec
from triplum.datasets.corpus import CorpusDataset
from triplum.datasets.frames import FrameDataset
from triplum.eval.inputs import ExtractionEvaluation, QAEvaluation

# Twins share MuSiQue's id; the unanswerable one gets this suffix and this abstain string.
UNANSWERABLE = "unanswerable"


def _paragraph_text(sentences: list[str]) -> str:
    return "".join(sentences)


def _add_context(corpus: base.Corpus, context: list) -> dict[str, int]:
    """Add a question's inline paragraphs; return title -> chunk id for gold resolution."""
    by_title: dict[str, int] = {}
    for title, sentences in context:
        by_title[title] = corpus.add(title, _paragraph_text(sentences))
    return by_title


def _resolve(name: str, qid: str, titles: list[str], by_title: dict[str, int]) -> list[int]:
    missing = [t for t in titles if t not in by_title]
    if missing or not titles:
        raise base.GoldMappingError(
            f"{name}: question {qid} gold not in context: {missing or 'none'}"
        )
    return sorted({by_title[t] for t in titles})


def parse_hotpotqa_full(paths: dict[str, Path], n: int | None) -> Benchmark:
    (path,) = paths.values()
    frame = pl.read_parquet(path)
    if n is not None:
        frame = frame.head(n)
    corpus = base.Corpus("hotpotqa_full")
    rows = []
    for q in frame.iter_rows(named=True):
        context = list(zip(q["context"]["title"], q["context"]["sentences"]))
        by_title = _add_context(corpus, context)
        gold = _resolve(
            "hotpotqa_full", q["id"], sorted(set(q["supporting_facts"]["title"])), by_title
        )
        meta = {
            "level": q["level"],
            "supporting_sentences": list(
                zip(q["supporting_facts"]["title"], q["supporting_facts"]["sent_id"])
            ),
            "candidate_chunk_ids": sorted(by_title.values()),
        }
        rows.append(
            base.question_row(
                q["id"], q["question"], q["answer"], [], gold, q["type"], metadata=meta
            )
        )
    return Benchmark(
        corpus=CorpusDataset(CorpusBatch(*corpus.frames())),
        qa=QAEvaluation(FrameDataset(base.questions_frame(rows))),
    )


def _loads(value):
    return json.loads(value) if isinstance(value, str) else value


def parse_twowiki_full(paths: dict[str, Path], n: int | None) -> Benchmark:
    (path,) = paths.values()
    frame = pl.read_parquet(path)
    if n is not None:
        frame = frame.head(n)
    corpus = base.Corpus("twowiki_full")
    rows, triples = [], []
    for q in frame.iter_rows(named=True):
        context = _loads(q["context"])
        supporting = _loads(q["supporting_facts"])
        evidences = _loads(q["evidences"])
        by_title = _add_context(corpus, context)
        gold = _resolve("twowiki_full", q["_id"], sorted({t for t, _ in supporting}), by_title)
        meta = {"evidences": evidences, "candidate_chunk_ids": sorted(by_title.values())}
        rows.append(
            base.question_row(
                q["_id"], q["question"], q["answer"], [], gold, q["type"], metadata=meta
            )
        )
        triples.extend((q["_id"], None, s, p, o) for s, p, o in evidences)
    return Benchmark(
        corpus=CorpusDataset(CorpusBatch(*corpus.frames())),
        qa=QAEvaluation(FrameDataset(base.questions_frame(rows))),
        extraction=ExtractionEvaluation(FrameDataset(base.triples_frame(triples))),
    )


def parse_musique_full(paths: dict[str, Path], n: int | None) -> Benchmark:
    (path,) = paths.values()
    records = base.read_jsonl(path)
    if n is not None:
        records = records[:n]
    corpus = base.Corpus("musique_full")
    rows = []
    for q in records:
        by_idx = {p["idx"]: corpus.add(p["title"], p["paragraph_text"]) for p in q["paragraphs"]}
        supporting = [p["idx"] for p in q["paragraphs"] if p["is_supporting"]]
        meta = {
            "decomposition": q["question_decomposition"],
            "candidate_chunk_ids": sorted(by_idx.values()),
            "supporting_chunk_ids": sorted({by_idx[i] for i in supporting}),
        }
        qtype = q["id"].split("__")[0]
        if q["answerable"]:
            gold = sorted({by_idx[i] for i in supporting})
            if not gold:
                raise base.GoldMappingError(
                    f"musique_full: question {q['id']} has no supporting paragraph"
                )
            rows.append(
                base.question_row(
                    q["id"],
                    q["question"],
                    q["answer"],
                    q["answer_aliases"],
                    gold,
                    qtype,
                    metadata=meta,
                )
            )
        else:
            meta["answer_if_answerable"] = q["answer"]
            rows.append(
                base.question_row(
                    f"{q['id']}__{UNANSWERABLE}",
                    q["question"],
                    UNANSWERABLE,
                    [],
                    [],
                    qtype,
                    answerable=False,
                    metadata=meta,
                )
            )
    return Benchmark(
        corpus=CorpusDataset(CorpusBatch(*corpus.frames())),
        qa=QAEvaluation(FrameDataset(base.questions_frame(rows))),
    )


def parse_morehopqa(paths: dict[str, Path], n: int | None) -> Benchmark:
    (path,) = paths.values()
    records = json.loads(path.read_text(encoding="utf-8"))
    if n is not None:
        records = records[:n]
    corpus = base.Corpus("morehopqa")
    rows = []
    for q in records:
        by_title = _add_context(corpus, q["context"])
        steps = q["question_decomposition"]
        titles = sorted(
            {s["paragraph_support_title"] for s in steps if s["paragraph_support_title"]}
        )
        gold = _resolve("morehopqa", q["_id"], titles, by_title)
        meta = {
            "decomposition": steps,
            "previous_question": q["previous_question"],
            "previous_answer": q["previous_answer"],
            "no_of_hops": q["no_of_hops"],
            "reasoning_type": q["reasoning_type"],
            "answer_type": q["answer_type"],
            "candidate_chunk_ids": sorted(by_title.values()),
        }
        rows.append(
            base.question_row(
                q["_id"],
                q["question"],
                str(q["answer"]),
                [],
                gold,
                q["reasoning_type"],
                metadata=meta,
            )
        )
    return Benchmark(
        corpus=CorpusDataset(CorpusBatch(*corpus.frames())),
        qa=QAEvaluation(FrameDataset(base.questions_frame(rows))),
    )


SPECS = (
    Spec(
        "hotpotqa_full",
        "multihop",
        base.manifest_files("hotpotqa_full"),
        "CC BY-SA 4.0",
        parse_hotpotqa_full,
    ),
    Spec(
        "twowiki_full",
        "multihop",
        base.manifest_files("twowiki_full"),
        "Apache-2.0 (xanhho HF mirror of the official dev split)",
        parse_twowiki_full,
    ),
    Spec(
        "musique_full",
        "abstention",
        base.manifest_files("musique_full"),
        "CC BY 4.0 (bdsaglam HF mirror, no licence tag on the card)",
        parse_musique_full,
    ),
    Spec("morehopqa", "multihop", base.manifest_files("morehopqa"), "CC BY 4.0", parse_morehopqa),
)
