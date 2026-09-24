"""Question sets over long documents. QuALITY v1.0.1 dev (CC BY 4.0 annotations; each article
carries its own licence field, mostly Project Gutenberg): 115 articles of 2,000-8,000 words, one
document each (230 article sets share them), and 2,086 four-option questions scored on the gold
option's text with its 1-based number as an alias. QASPER v0.3 test (CC BY 4.0): 416 NLP papers,
each one document whose segments are the abstract, the paragraphs and the figure or table
captions, and 1,451 questions whose gold chunks are the annotated evidence paragraphs. The paper
layout is one function shared by the corpus and the question source, so a question locates its
evidence in its own paper. 78 QASPER questions whose evidence is only table content or a partial
highlight match no segment and are not loaded; the answer is the first answerable annotation's,
with the other annotations' answers as aliases.
"""

from __future__ import annotations

import json
import tarfile
import zipfile
from collections.abc import Iterable
from pathlib import Path

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import Document, Segment, chunk_id, content_id
from triplum.datasets.base import Entry, InlineCorpus, ListSource, passage, titled
from triplum.datasets.files import File, manifest_files
from triplum.eval.inputs import Question
from triplum.settings import Settings

UNANSWERABLE = "unanswerable"
QUALITY_MEMBER = "QuALITY.v1.0.1.htmlstripped.dev"
QASPER_MEMBER = "qasper-test-v0.3.json"


def _quality_articles(path: Path) -> list[dict]:
    with zipfile.ZipFile(path) as zf:
        return [json.loads(line) for line in zf.read(QUALITY_MEMBER).decode().splitlines()]


def _quality_id(a: dict) -> str:
    return content_id(a["title"], a["article"])


class QualityCorpus(InlineCorpus[dict]):
    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or manifest_files("quality"), settings)

    def records(self, paths: dict[str, Path]) -> Iterable[dict]:
        (path,) = paths.values()
        return _quality_articles(path)

    def documents(self, raw: dict) -> Iterable[Document]:
        a = raw
        meta = {
            k: a[k] for k in ("title", "article_id", "source", "year", "author", "topic", "license")
        }
        yield passage(_quality_id(a), "quality", a["title"], a["article"], metadata=meta)


class QualityQuestions(ListSource[tuple[dict, dict], Question]):
    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or manifest_files("quality"), settings)

    def read(self, paths: dict[str, Path]) -> list[tuple[dict, dict]]:
        (path,) = paths.values()
        return [(a, q) for a in _quality_articles(path) for q in a["questions"]]

    def record(self, raw: tuple[dict, dict], index: int) -> Question:
        a, q = raw
        gold = q["gold_label"]
        return Question(
            id=q["question_unique_id"],
            question=q["question"],
            answer=q["options"][gold - 1],
            aliases=(str(gold),),
            gold=(chunk_id(_quality_id(a), 0),),
            qtype="hard" if q["difficult"] else "easy",
            metadata={"options": q["options"], "gold_label": gold},
        )


def _qasper_papers(path: Path) -> dict[str, dict]:
    with tarfile.open(path) as tf:
        member = tf.extractfile(QASPER_MEMBER)
        assert member is not None
        return json.load(member)


def qasper_layout(paper: dict) -> tuple[str, tuple[Segment, ...], dict[str, int]]:
    """The document text and segments of a paper, and evidence text -> segment ordinal (first
    match for repeated text). Shared by the corpus and the questions."""
    texts = [titled(paper["title"], paper["abstract"])]
    by_text = {paper["abstract"]: 0}
    for section in paper["full_text"]:
        for para in section["paragraphs"]:
            by_text.setdefault(para, len(texts))
            texts.append(titled(section["section_name"], para))
    for fig in paper["figures_and_tables"]:
        by_text.setdefault(fig["caption"], len(texts))
        texts.append(fig["caption"])
    segments, offset = [], 0
    for i, t in enumerate(texts):
        segments.append(Segment(ordinal=i, start=offset, end=offset + len(t)))
        offset += len(t) + 2
    return "\n\n".join(texts), tuple(segments), by_text


class QasperCorpus(ListSource[tuple[str, dict], Document]):
    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or manifest_files("qasper"), settings)

    def read(self, paths: dict[str, Path]) -> list[tuple[str, dict]]:
        (path,) = paths.values()
        return list(_qasper_papers(path).items())

    def record(self, raw: tuple[str, dict], index: int) -> Document:
        pid, p = raw
        text, segments, _ = qasper_layout(p)
        return Document(
            id=f"qasper:{pid}",
            source="qasper",
            text=text,
            segments=segments,
            metadata={"title": p["title"]},
        )


def _qasper_answer(answer: dict) -> str:
    if answer["yes_no"] is not None:
        return "yes" if answer["yes_no"] else "no"
    if answer["extractive_spans"]:
        return ", ".join(s.strip() for s in answer["extractive_spans"])
    return answer["free_form_answer"].strip()


class QasperQuestions(ListSource[Question, Question]):
    """Questions are built at read time because a question needs its paper's layout and the
    unmatched-evidence policy drops some; the list holds finished records."""

    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or manifest_files("qasper"), settings)

    def read(self, paths: dict[str, Path]) -> list[Question]:
        (path,) = paths.values()
        rows = []
        for pid, p in _qasper_papers(path).items():
            did = f"qasper:{pid}"
            _, _, by_text = qasper_layout(p)
            for qa in p["qas"]:
                answers = [a["answer"] for a in qa["answers"]]
                answerable = [a for a in answers if not a["unanswerable"]]
                gold = tuple(
                    sorted(
                        {
                            chunk_id(did, by_text[e])
                            for a in answers
                            for e in a["evidence"]
                            if e in by_text
                        }
                    )
                )
                meta = {"answers": answers, "candidate_chunk_ids": [chunk_id(did, 0)]}
                if not answerable:
                    rows.append(
                        Question(
                            id=qa["question_id"],
                            question=qa["question"],
                            answer=UNANSWERABLE,
                            gold=gold,
                            qtype="unanswerable",
                            answerable=False,
                            metadata=meta,
                        )
                    )
                elif gold:
                    first, *others = (_qasper_answer(a) for a in answerable)
                    rows.append(
                        Question(
                            id=qa["question_id"],
                            question=qa["question"],
                            answer=first,
                            aliases=tuple(
                                others + [s.strip() for s in answerable[0]["extractive_spans"]]
                            ),
                            gold=gold,
                            qtype="yes_no" if answerable[0]["yes_no"] is not None else "free_form",
                            metadata=meta,
                        )
                    )
        return rows

    def record(self, raw: Question, index: int) -> Question:
        return raw


ENTRIES = (
    Entry(
        name="quality",
        family="long_context",
        licence="CC BY 4.0 (annotations; per-article licence in document metadata)",
        build=lambda s: Benchmark(name="quality", corpus=QualityCorpus(s), qa=QualityQuestions(s)),
    ),
    Entry(
        name="qasper",
        family="long_context",
        licence="CC BY 4.0",
        build=lambda s: Benchmark(name="qasper", corpus=QasperCorpus(s), qa=QasperQuestions(s)),
    ),
)
