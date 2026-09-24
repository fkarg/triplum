"""HotpotQA-style multi-hop QA sets that ship each question's candidate paragraphs inline: the
official HotpotQA distractor dev set, the 2WikiMultiHopQA dev set (with gold `evidences`
triples), the MuSiQue full dev set with its unanswerable twins, and MoreHopQA (verified split,
with a gold reasoning chain). The corpus is the union of the inline paragraphs, one document per
distinct (title, text), streamed from the question records with a set of ids as the only state;
gold titles are resolved inside the question's own context, so a title shared by two different
paragraphs cannot be mis-assigned. The question sources are indexed and decode the same file
on their own first use.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import Document, chunk_id, content_id
from triplum.datasets import base
from triplum.datasets.base import Entry, InlineCorpus, ListSource, passage
from triplum.datasets.files import File, manifest_files
from triplum.eval.inputs import GoldMappingError, Question, Triple
from triplum.settings import Settings

# Twins share MuSiQue's id; the unanswerable one gets this suffix and this abstain string.
UNANSWERABLE = "unanswerable"


def _paragraph_text(sentences: list[str]) -> str:
    return "".join(sentences)


def _loads(value):
    return json.loads(value) if isinstance(value, str) else value


def _context(name: str, q: dict) -> list[tuple[str, str]]:
    """The question's inline paragraphs as (title, text)."""
    if name == "hotpotqa_full":
        return list(zip(q["context"]["title"], map(_paragraph_text, q["context"]["sentences"])))
    if name == "musique_full":
        return [(p["title"], p["paragraph_text"]) for p in q["paragraphs"]]
    return [(t, _paragraph_text(s)) for t, s in _loads(q["context"])]


def _by_title(context: list[tuple[str, str]]) -> dict[str, int]:
    """title -> chunk id for gold resolution inside one question's context."""
    return {t: chunk_id(content_id(t, txt), 0) for t, txt in context}


def _resolve(name: str, qid: str, titles: list[str], by_title: dict[str, int]) -> tuple[int, ...]:
    missing = [t for t in titles if t not in by_title]
    if missing or not titles:
        raise GoldMappingError(f"{name}: question {qid} gold not in context: {missing or 'none'}")
    return tuple(sorted({by_title[t] for t in titles}))


def _records(name: str, paths: dict[str, Path]) -> Iterable[dict]:
    """The question records of one set, read incrementally where the format allows."""
    (path,) = paths.values()
    if name == "musique_full":
        return base.jsonl_rows(path)
    if name == "morehopqa":
        return base.read_json(path)
    return base.parquet_rows(path)


class Corpus(InlineCorpus[dict]):
    """The union of inline paragraphs of one set, in first-seen order."""

    def __init__(
        self, name: str, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        self.name = name
        super().__init__(files or manifest_files(name), settings, {"name": name})

    def records(self, paths: dict[str, Path]) -> Iterable[dict]:
        return _records(self.name, paths)

    def documents(self, raw: dict) -> Iterable[Document]:
        for title, text in _context(self.name, raw):
            yield passage(content_id(title, text), self.name, title, text)


class Questions(ListSource[dict, Question]):
    def __init__(
        self, name: str, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        self.name = name
        super().__init__(files or manifest_files(name), settings, {"name": name})

    def read(self, paths: dict[str, Path]) -> list[dict]:
        return list(_records(self.name, paths))

    def record(self, raw: dict, index: int) -> Question:
        q = raw
        return _QUESTION[self.name](q)


def _hotpotqa_full(q: dict) -> Question:
    by_title = _by_title(_context("hotpotqa_full", q))
    gold = _resolve("hotpotqa_full", q["id"], sorted(set(q["supporting_facts"]["title"])), by_title)
    meta = {
        "level": q["level"],
        "supporting_sentences": list(
            zip(q["supporting_facts"]["title"], q["supporting_facts"]["sent_id"])
        ),
        "candidate_chunk_ids": sorted(by_title.values()),
    }
    return Question(
        id=q["id"],
        question=q["question"],
        answer=q["answer"],
        gold=gold,
        qtype=q["type"],
        metadata=meta,
    )


def _twowiki_full(q: dict) -> Question:
    by_title = _by_title(_context("twowiki_full", q))
    supporting = _loads(q["supporting_facts"])
    gold = _resolve("twowiki_full", q["_id"], sorted({t for t, _ in supporting}), by_title)
    meta = {"evidences": _loads(q["evidences"]), "candidate_chunk_ids": sorted(by_title.values())}
    return Question(
        id=q["_id"],
        question=q["question"],
        answer=q["answer"],
        gold=gold,
        qtype=q["type"],
        metadata=meta,
    )


def _musique_full(q: dict) -> Question:
    by_idx = {
        p["idx"]: chunk_id(content_id(p["title"], p["paragraph_text"]), 0) for p in q["paragraphs"]
    }
    supporting = sorted({by_idx[p["idx"]] for p in q["paragraphs"] if p["is_supporting"]})
    meta: dict[str, Any] = {
        "decomposition": q["question_decomposition"],
        "candidate_chunk_ids": sorted(by_idx.values()),
        "supporting_chunk_ids": supporting,
    }
    qtype = q["id"].split("__")[0]
    if q["answerable"]:
        if not supporting:
            raise GoldMappingError(f"musique_full: question {q['id']} has no supporting paragraph")
        return Question(
            id=q["id"],
            question=q["question"],
            answer=q["answer"],
            aliases=tuple(q["answer_aliases"]),
            gold=tuple(supporting),
            qtype=qtype,
            metadata=meta,
        )
    meta["answer_if_answerable"] = q["answer"]
    return Question(
        id=f"{q['id']}__{UNANSWERABLE}",
        question=q["question"],
        answer=UNANSWERABLE,
        qtype=qtype,
        answerable=False,
        metadata=meta,
    )


def _morehopqa(q: dict) -> Question:
    by_title = _by_title(_context("morehopqa", q))
    steps = q["question_decomposition"]
    titles = sorted({s["paragraph_support_title"] for s in steps if s["paragraph_support_title"]})
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
    return Question(
        id=q["_id"],
        question=q["question"],
        answer=str(q["answer"]),
        gold=gold,
        qtype=q["reasoning_type"],
        metadata=meta,
    )


_QUESTION = {
    "hotpotqa_full": _hotpotqa_full,
    "twowiki_full": _twowiki_full,
    "musique_full": _musique_full,
    "morehopqa": _morehopqa,
}


class TwoWikiFullTriples(ListSource[tuple, Triple]):
    """2Wiki's gold `evidences`, one question-linked triple each."""

    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or manifest_files("twowiki_full"), settings)

    def read(self, paths: dict[str, Path]) -> list[tuple]:
        (path,) = paths.values()
        return [
            (q["_id"], s, p, o)
            for q in base.parquet_rows(path)
            for s, p, o in _loads(q["evidences"])
        ]

    def record(self, raw: tuple, index: int) -> Triple:
        qid, s, p, o = raw
        return Triple(subject=s, predicate=p, object=o, question_id=qid)


def _benchmark(name: str, settings: Settings) -> Benchmark:
    return Benchmark(
        name=name,
        corpus=Corpus(name, settings),
        qa=Questions(name, settings),
        extraction=TwoWikiFullTriples(settings) if name == "twowiki_full" else None,
    )


ENTRIES = (
    Entry(name="hotpotqa_full", family="multihop", licence="CC BY-SA 4.0", build=lambda s: _benchmark("hotpotqa_full", s)),
    Entry(
        name="twowiki_full",
        family="multihop",
        licence="Apache-2.0 (xanhho HF mirror of the official dev split)",
        build=lambda s: _benchmark("twowiki_full", s),
    ),
    Entry(
        name="musique_full",
        family="abstention",
        licence="CC BY 4.0 (bdsaglam HF mirror, no licence tag on the card)",
        build=lambda s: _benchmark("musique_full", s),
    ),
    Entry(name="morehopqa", family="multihop", licence="CC BY 4.0", build=lambda s: _benchmark("morehopqa", s)),
)  # fmt: skip
