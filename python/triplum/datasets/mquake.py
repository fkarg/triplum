"""MQuAKE (MIT): multi-hop questions whose answer changes after a labelled fact edit. CF-3k-v2 has
3,000 counterfactual cases, T has 1,868 real temporal updates. Each case loads as one question
(the first of its three paraphrases) with the pre-edit answer; the pre-edit labelled triples are
the gold triples, question-linked, and the edit, the post-edit answer and the post-edit triples
sit in `metadata`. There is no corpus. The runner cannot yet ingest the edit and re-ask, so both
are declared `needs` and refuse to run until it can.
"""

from __future__ import annotations

from pathlib import Path

from triplum.bench.inputs import Benchmark
from triplum.datasets import base
from triplum.datasets.base import Entry, ListSource
from triplum.datasets.files import File, manifest_files
from triplum.eval.inputs import Question, Triple
from triplum.settings import Settings

NEEDS = "fact invalidation: ingest the labelled edit, then re-ask and score the post-edit answer"
FILENAMES = {"mquake_cf": "MQuAKE-CF-3k-v2.json", "mquake_t": "MQuAKE-T.json"}


def pinned(name: str) -> tuple[File, ...]:
    return tuple(f for f in manifest_files("mquake") if f.name.endswith(FILENAMES[name]))


class Questions(ListSource[dict, Question]):
    def __init__(
        self, name: str, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        self.name = name
        super().__init__(files or pinned(name), settings, {"name": name})

    def read(self, paths: dict[str, Path]) -> list[dict]:
        (path,) = paths.values()
        return base.read_json(path)

    def record(self, raw: dict, index: int) -> Question:
        c = raw
        meta = {
            "paraphrases": c["questions"],
            "requested_rewrite": c["requested_rewrite"],
            "new_answer": c["new_answer"],
            "new_answer_alias": c["new_answer_alias"],
            "new_triples_labeled": c["orig"]["new_triples_labeled"],
            "single_hops": c["single_hops"],
            "new_single_hops": c["new_single_hops"],
        }
        return Question(
            id=f"{self.name}:{c['case_id']}",
            question=c["questions"][0],
            answer=c["answer"],
            aliases=tuple(c["answer_alias"]),
            qtype=str(len(c["single_hops"])) + "-hop",
            metadata=meta,
        )


class Triples(ListSource[tuple, Triple]):
    def __init__(
        self, name: str, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        self.name = name
        super().__init__(files or pinned(name), settings, {"name": name})

    def read(self, paths: dict[str, Path]) -> list[tuple]:
        (path,) = paths.values()
        return [
            (f"{self.name}:{c['case_id']}", s, p, o)
            for c in base.read_json(path)
            for s, p, o in c["orig"]["triples_labeled"]
        ]

    def record(self, raw: tuple, index: int) -> Triple:
        qid, s, p, o = raw
        return Triple(subject=s, predicate=p, object=o, question_id=qid)


def _entry(name: str) -> Entry:
    return Entry(
        name=name,
        family="temporal",
        licence="MIT",
        needs=NEEDS,
        build=lambda s: Benchmark(name=name, qa=Questions(name, s), extraction=Triples(name, s)),
    )


ENTRIES = (_entry("mquake_cf"), _entry("mquake_t"))
