"""Reading comprehension with the passage inline: SQuAD 1.1 and 2.0 validation (CC BY-SA 4.0)
and BoolQ validation (CC BY-SA 3.0). The corpus is the set of distinct passages, one chunk each;
the gold chunk is the question's own passage, so retrieval here measures finding a paragraph among
a few thousand siblings from the same articles. SQuAD 2.0 questions without an answer are
unanswerable and keep their passage in `metadata.candidate_chunk_ids`; BoolQ answers are `yes`
or `no`.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import CorpusBatch
from triplum.datasets import base
from triplum.datasets.base import Spec
from triplum.datasets.corpus import CorpusDataset
from triplum.datasets.frames import FrameDataset
from triplum.eval.inputs import QAEvaluation

UNANSWERABLE = "unanswerable"


def _squad(name: str, paths: dict[str, Path], n: int | None) -> Benchmark:
    (path,) = paths.values()
    frame = pl.read_parquet(path)
    if n is not None:
        frame = frame.head(n)
    corpus = base.Corpus(name)
    rows = []
    for q in frame.iter_rows(named=True):
        cid = corpus.add(q["title"].replace("_", " "), q["context"])
        texts = list(dict.fromkeys(q["answers"]["text"]))
        meta = {"candidate_chunk_ids": [cid]}
        if texts:
            rows.append(
                base.question_row(
                    q["id"], q["question"], texts[0], texts[1:], [cid], "span", metadata=meta
                )
            )
        else:
            rows.append(
                base.question_row(
                    q["id"],
                    q["question"],
                    UNANSWERABLE,
                    [],
                    [],
                    "span",
                    answerable=False,
                    metadata=meta,
                )
            )
    return Benchmark(
        corpus=CorpusDataset(CorpusBatch(*corpus.frames())),
        qa=QAEvaluation(FrameDataset(base.questions_frame(rows))),
    )


def parse_squad(paths: dict[str, Path], n: int | None) -> Benchmark:
    return _squad("squad", paths, n)


def parse_squad_v2(paths: dict[str, Path], n: int | None) -> Benchmark:
    return _squad("squad_v2", paths, n)


def parse_boolq(paths: dict[str, Path], n: int | None) -> Benchmark:
    (path,) = paths.values()
    frame = pl.read_parquet(path)
    if n is not None:
        frame = frame.head(n)
    corpus = base.Corpus("boolq")
    rows = []
    for i, q in enumerate(frame.iter_rows(named=True)):
        cid = corpus.add("", q["passage"])
        rows.append(
            base.question_row(
                f"boolq:{i}",
                q["question"],
                "yes" if q["answer"] else "no",
                [],
                [cid],
                "boolean",
                metadata={"candidate_chunk_ids": [cid]},
            )
        )
    return Benchmark(
        corpus=CorpusDataset(CorpusBatch(*corpus.frames())),
        qa=QAEvaluation(FrameDataset(base.questions_frame(rows))),
    )


SPECS = (
    Spec("squad", "reading", base.manifest_files("squad"), "CC BY-SA 4.0", parse_squad),
    Spec(
        "squad_v2",
        "abstention",
        base.manifest_files("squad_v2"),
        "CC BY-SA 4.0",
        parse_squad_v2,
    ),
    Spec("boolq", "reading", base.manifest_files("boolq"), "CC BY-SA 3.0", parse_boolq),
)
