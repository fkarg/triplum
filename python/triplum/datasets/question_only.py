"""Question-only sets: no corpus ships with them, so only the closed-book pipeline applies until a
shared Wikipedia corpus exists. Long-tail controls PopQA (14,267 questions with entity popularity,
no licence declared) and EntityQuestions (test split, 24 Wikidata relations, MIT); NQ-Open
validation (3,610, CC BY-SA 3.0); AmbigQA dev (2,002, CC BY-SA 3.0) whose disambiguated
answers are unioned into aliases and kept whole in `metadata`; Bamboogle (125 compositional
questions, MIT); FreshQA (600 questions whose answers change over time, Apache-2.0; the sheet is
live, so the pinned hash tracks one dated export); and the two AI2 ARC science exam test splits
(CC BY-SA 4.0), scored on the gold option's text with its letter as an alias.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

import polars as pl

from triplum.bench.inputs import Benchmark
from triplum.datasets import base
from triplum.datasets.base import Spec
from triplum.datasets.frames import FrameDataset
from triplum.eval.inputs import QAEvaluation


def _no_corpus(rows: list[tuple]) -> Benchmark:
    return Benchmark(qa=QAEvaluation(FrameDataset(base.questions_frame(rows))))


def _parquet(paths: dict[str, Path], n: int | None) -> pl.DataFrame:
    (path,) = paths.values()
    frame = pl.read_parquet(path)
    return frame.head(n) if n is not None else frame


def parse_popqa(paths: dict[str, Path], n: int | None) -> Benchmark:
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


def parse_entityquestions(paths: dict[str, Path], n: int | None) -> Benchmark:
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


def parse_nq_open(paths: dict[str, Path], n: int | None) -> Benchmark:
    rows = [
        base.question_row(f"nq_open:{i}", q["question"], q["answer"][0], q["answer"][1:], [])
        for i, q in enumerate(_parquet(paths, n).iter_rows(named=True))
    ]
    return _no_corpus(rows)


def parse_ambigqa(paths: dict[str, Path], n: int | None) -> Benchmark:
    (path,) = paths.values()
    with zipfile.ZipFile(path) as zf:
        records = json.loads(zf.read("dev_light.json").decode("utf-8"))
    if n is not None:
        records = records[:n]
    rows = []
    for q in records:
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
            else ("singleAnswer")
        )
        rows.append(
            base.question_row(
                q["id"],
                q["question"],
                answers[0],
                answers[1:],
                [],
                qtype,
                metadata={"annotations": q["annotations"]},
            )
        )
    return _no_corpus(rows)


def parse_bamboogle(paths: dict[str, Path], n: int | None) -> Benchmark:
    rows = [
        base.question_row(f"bamboogle:{i}", q["Question"], q["Answer"], [], [], "multihop")
        for i, q in enumerate(_parquet(paths, n).iter_rows(named=True))
    ]
    return _no_corpus(rows)


FRESHQA_PREAMBLE = 2  # rows above the header in the published sheet


def parse_freshqa(paths: dict[str, Path], n: int | None) -> Benchmark:
    (path,) = paths.values()
    lines = path.read_text(encoding="utf-8").splitlines()[FRESHQA_PREAMBLE:]
    rows = []
    for q in csv.DictReader(io.StringIO("\n".join(lines))):
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
        rows.append(
            base.question_row(
                f"freshqa:{q['id']}",
                q["question"],
                answers[0],
                answers[1:],
                [],
                q["fact_type"],
                metadata=meta,
            )
        )
        if n is not None and len(rows) >= n:
            break
    return _no_corpus(rows)


def parse_arc(paths: dict[str, Path], n: int | None) -> Benchmark:
    rows = []
    for q in _parquet(paths, n).iter_rows(named=True):
        choices = dict(zip(q["choices"]["label"], q["choices"]["text"]))
        rows.append(
            base.question_row(
                q["id"],
                q["question"],
                choices[q["answerKey"]],
                [q["answerKey"]],
                [],
                "multiple_choice",
                metadata={"choices": choices},
            )
        )
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
    Spec("nq_open", "control", base.manifest_files("nq_open"), "CC BY-SA 3.0", parse_nq_open),
    Spec("ambigqa", "ambiguity", base.manifest_files("ambigqa"), "CC BY-SA 3.0", parse_ambigqa),
    Spec("bamboogle", "multihop", base.manifest_files("bamboogle"), "MIT", parse_bamboogle),
    Spec(
        "freshqa",
        "temporal",
        base.manifest_files("freshqa"),
        "Apache-2.0 (repository licence; sheet export of 2026-04-21)",
        parse_freshqa,
    ),
    Spec("arc_easy", "control", base.manifest_files("arc_easy"), "CC BY-SA 4.0", parse_arc),
    Spec(
        "arc_challenge",
        "control",
        base.manifest_files("arc_challenge"),
        "CC BY-SA 4.0",
        parse_arc,
    ),
)
