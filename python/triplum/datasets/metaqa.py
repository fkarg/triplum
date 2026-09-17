"""MetaQA (CC BY 3.0): a movie knowledge base of 134,741 triples over nine relations and the
vanilla 1-, 2- and 3-hop test questions (39,093, interleaved by hop so any prefix mixes hops).
The KB is the source, so it is loaded two ways at once: as `triples` with `document_id` set,
for direct ingestion into the graph tables, and verbalised into one document and chunk per
entity (its outgoing triples as sentences, then its incoming ones inverted), for the text
pipelines. The verbalisation is synthetic text: extraction scores over it measure the templates
as much as the extractor. The bracketed topic entity is stripped from the question and kept in
`metadata.topic`; gold chunks are the topic's and the answers' entity chunks, which contain the
full path for 1 and 2 hops and omit the middle entity of a 3-hop chain.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import CorpusBatch
from triplum.datasets import base
from triplum.datasets.base import Spec
from triplum.datasets.corpus import CorpusDataset
from triplum.datasets.frames import FrameDataset
from triplum.eval.inputs import ExtractionEvaluation, QAEvaluation

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


def parse(paths: dict[str, Path], n: int | None) -> Benchmark:
    kb = next(p for name, p in paths.items() if name.endswith("kb.txt"))
    kb_rows = [line.split("|") for line in kb.read_text(encoding="utf-8").splitlines() if line]
    sentences: dict[str, list[str]] = defaultdict(list)
    for s, p, o in kb_rows:
        out, inc = TEMPLATES[p]
        sentences[s].append(out.format(s=s, o=o))
        if o != s:
            sentences[o].append(inc.format(s=s, o=o))
    entities = list(sentences)
    passages = [(f"metaqa:{e}", e, " ".join(sentences[e]), 0, {"entity": e}) for e in entities]
    documents, grants, chunks = base.corpus_frames("metaqa", passages)
    by_entity = {e: i + 1 for i, e in enumerate(entities)}
    triples = [(None, f"metaqa:{s}", s, p, o) for s, p, o in kb_rows]
    per_hop = []
    for hop in HOPS:
        path = next(p for name, p in paths.items() if name.endswith(f"{hop}_qa_test.txt"))
        per_hop.append(
            [line.split("\t") for line in path.read_text(encoding="utf-8").splitlines() if line]
        )
    rows = []
    for i in range(max(len(h) for h in per_hop)):
        for hop, lines in zip(HOPS, per_hop):
            if i >= len(lines):
                continue
            question, answers = lines[i]
            topic = question[question.index("[") + 1 : question.index("]")]
            answer_list = answers.split("|")
            qid = f"metaqa:{hop}:{i}"
            gold = base.resolve_gold("metaqa", qid, [topic, *answer_list], by_entity)
            rows.append(
                base.question_row(
                    qid,
                    question.replace("[", "").replace("]", ""),
                    answer_list[0],
                    answer_list[1:],
                    gold,
                    hop,
                    metadata={"topic": topic, "answers": answer_list},
                )
            )
    if n is not None:
        rows = rows[:n]
    return Benchmark(
        corpus=CorpusDataset(CorpusBatch(documents, grants, chunks)),
        qa=QAEvaluation(FrameDataset(base.questions_frame(rows))),
        extraction=ExtractionEvaluation(FrameDataset(base.triples_frame(triples))),
    )


SPECS = (Spec("metaqa", "kgqa", base.manifest_files("metaqa"), "CC BY 3.0", parse),)
