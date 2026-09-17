"""The HippoRAG / IRCoT 1000-question protocol for HotpotQA, MuSiQue and 2WikiMultiHopQA.

Source of truth: `reproduce/dataset/*.json` in github.com/OSU-NLP-Group/HippoRAG (MIT), content
under the upstream datasets' licences (HotpotQA CC BY-SA 4.0, MuSiQue CC BY 4.0, 2Wiki Apache-2.0).
Both files are JSON lists, so the corpus and the questions are indexed and decode on first use.
Document keys: titles are unique in the HotpotQA and 2Wiki corpora and 2Wiki's question-side
paragraph text does not reproduce the corpus text, so those key by title; MuSiQue repeats titles
and keys by title and text (measured on the pinned files, 2026-09-17).
"""

from __future__ import annotations

from functools import partial
from pathlib import Path

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import Document, chunk_id, content_id
from triplum.datasets.base import Entry, ListSource, passage, read_json
from triplum.datasets.files import File
from triplum.eval.inputs import GoldMappingError, Question, Triple
from triplum.settings import Settings

RAW_BASE = "https://raw.githubusercontent.com/OSU-NLP-Group/HippoRAG/main/reproduce/dataset/"

# sha256 of the files as fetched on 2026-09-16 (HippoRAG 2 generation; HotpotQA corpus = 9,811).
_FILES = {
    "hotpotqa": (
        ("hotpotqa.json", "3ad9c0bcbf93f41d7004ca6007049c904d2605046b314a2f7ecfb379c64cba6d"),
        (
            "hotpotqa_corpus.json",
            "9333647b922382776cd2cb02893b390d77984df85a91bfa8be411284978aca7d",
        ),
    ),
    "musique": (
        ("musique.json", "98ed4e21d3076532f6388d42320fb809599c63a0d8dffca8ece5e41922be6b46"),
        ("musique_corpus.json", "73157a03ce3f0b1a5673dd5dc12bb970c24976dbffc688af9eecdd758c97ffcb"),
    ),
    "twowiki": (
        (
            "2wikimultihopqa.json",
            "895cba294064df0c3302c76847b1fc08d99b5619f7663dfaa3b65cd780f1cac4",
        ),
        (
            "2wikimultihopqa_corpus.json",
            "9d6e352952aafb18dab22bf8195039461321a44a949df902ae83bce134ad238a",
        ),
    ),
}
_LICENCE = {
    "hotpotqa": "CC BY-SA 4.0 (HippoRAG files MIT)",
    "musique": "CC BY 4.0 (HippoRAG files MIT)",
    "twowiki": "Apache-2.0 (HippoRAG files MIT)",
}
NAMES = tuple(_FILES)


def pinned(name: str) -> tuple[File, ...]:
    (qfile, qhash), (cfile, chash) = _FILES[name]
    return (
        File(url=RAW_BASE + qfile, name=f"hipporag/{qfile}", sha256=qhash),
        File(url=RAW_BASE + cfile, name=f"hipporag/{cfile}", sha256=chash),
    )


def document_id(name: str, title: str, text: str = "") -> str:
    """The per-set logical key (module docstring); `text` is ignored outside MuSiQue."""
    return content_id(title, text) if name == "musique" else content_id(title)


class HippoRAGCorpus(ListSource[dict, Document]):
    """One passage per corpus entry, text `title\\ntext`."""

    def __init__(
        self, name: str, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        self.name = name
        super().__init__(files or pinned(name), settings, {"name": name})

    def read(self, paths: dict[str, Path]) -> list[dict]:
        return read_json(self.path(_FILES[self.name][1][0]))

    def record(self, raw: dict, index: int) -> Document:
        return passage(
            document_id(self.name, raw["title"], raw["text"]),
            f"hipporag/{self.name}",
            raw["title"],
            raw["text"],
        )


class HippoRAGQuestions(ListSource[dict, Question]):
    """The protocol's questions; gold and candidate chunk ids come from the question's own
    supporting facts and context, so no corpus pass is needed."""

    def __init__(
        self, name: str, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        self.name = name
        super().__init__(files or pinned(name), settings, {"name": name})

    def read(self, paths: dict[str, Path]) -> list[dict]:
        return read_json(self.path(_FILES[self.name][0][0]))

    def record(self, raw: dict, index: int) -> Question:
        q = raw
        name = self.name
        if name == "musique":
            qid, answer = q["id"], q["answer"]
            aliases = q.get("answer_aliases", [])
            gold = [
                (p["title"], p["paragraph_text"]) for p in q["paragraphs"] if p["is_supporting"]
            ]
            candidates = [(p["title"], p["paragraph_text"]) for p in q["paragraphs"]]
            qtype = q["id"].split("__")[0]
            meta: dict = {"decomposition": q.get("question_decomposition", [])}
        else:
            qid, answer = q["_id"], q["answer"]
            aliases = []
            gold = sorted({(t, "") for t, _ in q["supporting_facts"]})
            candidates = [(t, "") for t, _ in q["context"]]
            qtype = q.get("type", "")
            meta = {"evidences": q["evidences"]} if name == "twowiki" else {}
        if not gold:
            raise GoldMappingError(f"{name}: question {qid} has no supporting passage")
        meta["candidate_chunk_ids"] = sorted(
            {chunk_id(document_id(name, t, txt), 0) for t, txt in candidates}
        )
        return Question(
            id=qid,
            question=q["question"],
            answer=answer,
            aliases=tuple(aliases),
            gold=tuple(chunk_id(document_id(name, t, txt), 0) for t, txt in gold),
            qtype=qtype,
            metadata=meta,
        )


class TwoWikiTriples(ListSource[tuple, Triple]):
    """2Wiki's gold `evidences`, one triple per question-linked evidence."""

    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or pinned("twowiki"), settings)

    def read(self, paths: dict[str, Path]) -> list[tuple]:
        questions = read_json(self.path(_FILES["twowiki"][0][0]))
        return [(q["_id"], s, p, o) for q in questions for s, p, o in q["evidences"]]

    def record(self, raw: tuple, index: int) -> Triple:
        qid, s, p, o = raw
        return Triple(subject=s, predicate=p, object=o, question_id=qid)


def benchmark(name: str, settings: Settings) -> Benchmark:
    return Benchmark(
        name=name,
        corpus=HippoRAGCorpus(name, settings),
        qa=HippoRAGQuestions(name, settings),
        extraction=TwoWikiTriples(settings) if name == "twowiki" else None,
    )


ENTRIES = tuple(
    Entry(
        name=name,
        family="multihop",
        licence=_LICENCE[name],
        default=True,
        build=partial(benchmark, name),
    )
    for name in NAMES
)
