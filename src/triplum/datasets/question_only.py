"""Question-only sets: no corpus ships with them, so only the closed-book pipeline applies until a
shared Wikipedia corpus exists. Long-tail controls PopQA (14,267 questions with entity popularity,
no licence declared) and EntityQuestions (test split, 24 Wikidata relations, MIT); NQ-Open
validation (3,610, CC BY-SA 3.0); AmbigQA dev (2,002, CC BY-SA 3.0) whose disambiguated
answers are unioned into aliases and kept whole in `metadata`; Bamboogle (125 compositional
questions, MIT); FreshQA (600 questions whose answers change over time, Apache-2.0; the sheet is
live, so the pinned hash tracks one dated export); and the two AI2 ARC science exam test splits
(CC BY-SA 4.0), scored on the gold option's text with its letter as an alias. Every source is an
indexed list decoded on first use.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections.abc import Callable
from pathlib import Path

from triplum.bench.inputs import Benchmark
from triplum.datasets import base
from triplum.datasets.base import Entry, ListSource
from triplum.datasets.files import File, manifest_files
from triplum.eval.inputs import Question
from triplum.settings import Settings

FRESHQA_PREAMBLE = 2  # rows above the header in the published sheet
POPQA_META = ("subj", "prop", "obj", "subj_id", "prop_id", "obj_id", "s_uri", "o_uri", "s_pop", "o_pop")  # fmt: skip


def _popqa(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _popqa_q(q: dict, i: int) -> Question:
    answers = json.loads(q["possible_answers"])
    return Question(
        id=q["id"],
        question=q["question"],
        answer=answers[0],
        aliases=tuple(answers[1:]),
        qtype=q["prop"],
        metadata={k: q[k] for k in POPQA_META},
    )


def _entityquestions(path: Path) -> list[dict]:
    rows = []
    with zipfile.ZipFile(path) as zf:
        members = sorted(
            m for m in zf.namelist() if m.startswith("dataset/test/") and m.endswith(".test.json")
        )
        for member in members:
            relation = member.rsplit("/", 1)[1].split(".")[0]
            for i, q in enumerate(json.loads(zf.read(member).decode("utf-8"))):
                rows.append({**q, "id": f"{relation}:{i}", "relation": relation})
    return rows


def _entityquestions_q(q: dict, i: int) -> Question:
    answers = q["answers"]
    return Question(
        id=q["id"],
        question=q["question"],
        answer=answers[0],
        aliases=tuple(answers[1:]),
        qtype=q["relation"],
    )


def _parquet(path: Path) -> list[dict]:
    return list(base.parquet_rows(path))


def _nq_open_q(q: dict, i: int) -> Question:
    return Question(
        id=f"nq_open:{i}",
        question=q["question"],
        answer=q["answer"][0],
        aliases=tuple(q["answer"][1:]),
    )


def _ambigqa(path: Path) -> list[dict]:
    with zipfile.ZipFile(path) as zf:
        return json.loads(zf.read("dev_light.json").decode("utf-8"))


def _ambigqa_q(q: dict, i: int) -> Question:
    answers: list[str] = []
    for ann in q["annotations"]:
        if ann["type"] == "singleAnswer":
            answers.extend(ann["answer"])
        else:
            for pair in ann["qaPairs"]:
                answers.extend(pair["answer"])
    qtype = (
        "multipleQAs"
        if any(a["type"] == "multipleQAs" for a in q["annotations"])
        else "singleAnswer"
    )
    return Question(
        id=q["id"],
        question=q["question"],
        answer=answers[0],
        aliases=tuple(answers[1:]),
        qtype=qtype,
        metadata={"annotations": q["annotations"]},
    )


def _bamboogle_q(q: dict, i: int) -> Question:
    return Question(
        id=f"bamboogle:{i}", question=q["Question"], answer=q["Answer"], qtype="multihop"
    )


def _freshqa(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()[FRESHQA_PREAMBLE:]
    return list(csv.DictReader(io.StringIO("\n".join(lines))))


def _freshqa_q(q: dict, i: int) -> Question:
    answers = [q[f"answer_{i}"] for i in range(10) if q[f"answer_{i}"]]
    meta = {
        "split": q["split"],
        "effective_year": q["effective_year"],
        "next_review": q["next_review"],
        "false_premise": q["false_premise"] == "TRUE",
        "num_hops": q["num_hops"],
        "source": q["source"],
        "note": q["note"],
    }
    return Question(
        id=f"freshqa:{q['id']}",
        question=q["question"],
        answer=answers[0],
        aliases=tuple(answers[1:]),
        qtype=q["fact_type"],
        metadata=meta,
    )


def _arc_q(q: dict, i: int) -> Question:
    choices = dict(zip(q["choices"]["label"], q["choices"]["text"]))
    return Question(
        id=q["id"],
        question=q["question"],
        answer=choices[q["answerKey"]],
        aliases=(q["answerKey"],),
        qtype="multiple_choice",
        metadata={"choices": choices},
    )


_READ: dict[str, Callable[[Path], list[dict]]] = {
    "popqa": _popqa,
    "entityquestions": _entityquestions,
    "nq_open": _parquet,
    "ambigqa": _ambigqa,
    "bamboogle": _parquet,
    "freshqa": _freshqa,
    "arc_easy": _parquet,
    "arc_challenge": _parquet,
}
_QUESTION: dict[str, Callable[[dict, int], Question]] = {
    "popqa": _popqa_q,
    "entityquestions": _entityquestions_q,
    "nq_open": _nq_open_q,
    "ambigqa": _ambigqa_q,
    "bamboogle": _bamboogle_q,
    "freshqa": _freshqa_q,
    "arc_easy": _arc_q,
    "arc_challenge": _arc_q,
}


class Questions(ListSource[dict, Question]):
    def __init__(
        self, name: str, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        self.name = name
        super().__init__(files or manifest_files(name), settings, {"name": name})

    def read(self, paths: dict[str, Path]) -> list[dict]:
        (path,) = paths.values()
        return _READ[self.name](path)

    def record(self, raw: dict, index: int) -> Question:
        return _QUESTION[self.name](raw, index)


def _entry(name: str, family: str, licence: str) -> Entry:
    return Entry(
        name=name,
        family=family,
        licence=licence,
        build=lambda s: Benchmark(name=name, qa=Questions(name, s)),
    )


ENTRIES = (
    _entry("popqa", "control", "none declared"),
    _entry("entityquestions", "control", "MIT"),
    _entry("nq_open", "control", "CC BY-SA 3.0"),
    _entry("ambigqa", "ambiguity", "CC BY-SA 3.0"),
    _entry("bamboogle", "multihop", "MIT"),
    _entry("freshqa", "temporal", "Apache-2.0 (repository licence; sheet export of 2026-04-21)"),
    _entry("arc_easy", "control", "CC BY-SA 4.0"),
    _entry("arc_challenge", "control", "CC BY-SA 4.0"),
)
