"""Long-tail single-hop controls with no corpus: PopQA (14,267 questions, entity popularity per
question, no licence declared) and EntityQuestions (test split, 24 Wikidata relations, MIT). Only
the closed-book pipeline applies; they are the canonical case for whether a graph helps on rare
entities once a shared Wikipedia corpus exists.
"""

from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

from triplum.eval.datasets import base
from triplum.eval.datasets.base import Frames, Spec


def _no_corpus(rows: list[tuple]) -> Frames:
    return Frames(
        base.questions_frame(rows),
        base.empty(base.DOC_SCHEMA),
        base.empty(base.GRANT_SCHEMA),
        base.empty(base.CHUNK_SCHEMA),
        base.empty(base.TRIPLE_SCHEMA),
    )


def parse_popqa(paths: dict[str, Path], n: int | None) -> Frames:
    (path,) = paths.values()
    rows = []
    with path.open(encoding="utf-8", newline="") as f:
        for q in csv.DictReader(f, delimiter="\t"):
            answers = json.loads(q["possible_answers"])
            meta = {
                k: q[k]
                for k in (
                    "subj",
                    "prop",
                    "obj",
                    "subj_id",
                    "prop_id",
                    "obj_id",
                    "s_uri",
                    "o_uri",
                    "s_pop",
                    "o_pop",
                )
            }
            rows.append(
                base.question_row(
                    q["id"], q["question"], answers[0], answers[1:], [], q["prop"], metadata=meta
                )
            )
            if n is not None and len(rows) >= n:
                break
    return _no_corpus(rows)


def parse_entityquestions(paths: dict[str, Path], n: int | None) -> Frames:
    (path,) = paths.values()
    rows = []
    with zipfile.ZipFile(path) as zf:
        members = sorted(
            m for m in zf.namelist() if m.startswith("dataset/test/") and m.endswith(".test.json")
        )
        for member in members:
            relation = member.rsplit("/", 1)[1].split(".")[0]
            for i, q in enumerate(json.loads(zf.read(member).decode("utf-8"))):
                answers = q["answers"]
                rows.append(
                    base.question_row(
                        f"{relation}:{i}", q["question"], answers[0], answers[1:], [], relation
                    )
                )
    if n is not None:
        rows = rows[:n]
    return _no_corpus(rows)


SPECS = (
    Spec("popqa", "control", base.manifest_files("popqa"), "none declared", parse_popqa),
    Spec(
        "entityquestions",
        "control",
        base.manifest_files("entityquestions"),
        "MIT",
        parse_entityquestions,
    ),
)
