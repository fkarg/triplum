"""MetaQA (CC BY 3.0): a movie knowledge base of 134,741 triples over nine relations and the
vanilla 1-, 2- and 3-hop test questions (39,093, interleaved by hop so any prefix mixes hops).
The KB is the source, so it is loaded two ways at once: as gold triples with `document_id` set,
for direct ingestion into the graph tables, and verbalised into one document per entity (its
outgoing triples as sentences, then its incoming ones inverted), for the text pipelines. The
corpus is eager by declaration: an entity's document aggregates the whole KB, so the first
access reads it. The verbalisation is synthetic text: extraction scores over it measure the
templates as much as the extractor. The bracketed topic entity is stripped from the question and
kept in `metadata.topic`; gold chunks are the topic's and the answers' entity documents, which
contain the full path for 1 and 2 hops and omit the middle entity of a 3-hop chain.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import Document, chunk_id
from triplum.datasets.base import Entry, ListSource, passage
from triplum.datasets.files import File, manifest_files
from triplum.eval.inputs import Question, Triple
from triplum.settings import Settings

VERBALISER_VERSION = 1
# relation -> (sentence from the subject's side, sentence from the object's side)
TEMPLATES = {
    "directed_by": ("{s} was directed by {o}.", "{o} directed {s}."),
    "written_by": ("{s} was written by {o}.", "{o} wrote {s}."),
    "starred_actors": ("{s} starred {o}.", "{o} starred in {s}."),
    "release_year": ("{s} was released in {o}.", "{s} was released in {o}."),
    "in_language": ("{s} is in {o}.", "{o} is the language of {s}."),
    "has_tags": ("{s} is tagged {o}.", "{o} is a tag of {s}."),
    "has_genre": ("{s} is a {o} film.", "{o} is the genre of {s}."),
    "has_imdb_votes": ("{s} has {o} IMDb votes.", "{s} has {o} IMDb votes."),
    "has_imdb_rating": ("{s} has an IMDb rating of {o}.", "{s} has an IMDb rating of {o}."),
}
HOPS = ("1hop", "2hop", "3hop")


def document_id(entity: str) -> str:
    return f"metaqa:{entity}"


def _kb(path: Path) -> list[list[str]]:
    return [line.split("|") for line in path.read_text(encoding="utf-8").splitlines() if line]


class Corpus(ListSource[tuple[str, str], Document]):
    version = VERBALISER_VERSION

    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or manifest_files("metaqa"), settings)

    def read(self, paths: dict[str, Path]) -> list[tuple[str, str]]:
        sentences: dict[str, list[str]] = defaultdict(list)
        for s, p, o in _kb(self.path("kb.txt")):
            out, inc = TEMPLATES[p]
            sentences[s].append(out.format(s=s, o=o))
            if o != s:
                sentences[o].append(inc.format(s=s, o=o))
        return [(e, " ".join(lines)) for e, lines in sentences.items()]

    def record(self, raw: tuple[str, str], index: int) -> Document:
        entity, text = raw
        return passage(document_id(entity), "metaqa", entity, text, metadata={"entity": entity})


class Triples(ListSource[list[str], Triple]):
    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or manifest_files("metaqa"), settings)

    def read(self, paths: dict[str, Path]) -> list[list[str]]:
        return _kb(self.path("kb.txt"))

    def record(self, raw: list[str], index: int) -> Triple:
        s, p, o = raw
        return Triple(subject=s, predicate=p, object=o, document_id=document_id(s))


class Questions(ListSource[tuple[str, int, list[str]], Question]):
    """The three hop files interleaved: any prefix mixes hops."""

    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or manifest_files("metaqa"), settings)

    def read(self, paths: dict[str, Path]) -> list[tuple[str, int, list[str]]]:
        per_hop = [
            [
                line.split("\t")
                for line in self.path(f"{hop}_qa_test.txt").read_text(encoding="utf-8").splitlines()
                if line
            ]
            for hop in HOPS
        ]
        rows = []
        for i in range(max(len(h) for h in per_hop)):
            for hop, lines in zip(HOPS, per_hop):
                if i < len(lines):
                    rows.append((hop, i, lines[i]))
        return rows

    def record(self, raw: tuple[str, int, list[str]], index: int) -> Question:
        hop, i, (question, answers) = raw
        topic = question[question.index("[") + 1 : question.index("]")]
        answer_list = answers.split("|")
        return Question(
            id=f"metaqa:{hop}:{i}",
            question=question.replace("[", "").replace("]", ""),
            answer=answer_list[0],
            aliases=tuple(answer_list[1:]),
            gold=tuple(chunk_id(document_id(e), 0) for e in (topic, *answer_list)),
            qtype=hop,
            metadata={"topic": topic, "answers": answer_list},
        )


ENTRIES = (
    Entry(
        name="metaqa",
        family="kgqa",
        licence="CC BY 3.0",
        build=lambda s: Benchmark(
            name="metaqa", corpus=Corpus(s), qa=Questions(s), extraction=Triples(s)
        ),
    ),
)
