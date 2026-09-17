"""Committed fixtures: a benchmark's records as one JSON file under `tests/fixtures`, read back
as in-memory `RecordDataset` parts whose identity is their content. `subset` keeps the first
`n` questions, every chunk they need and a seeded fill of distractors, at chunk granularity: a
selected document keeps its full text and only the selected segments, with their original
ordinals, so chunk ids are the same in the fixture and the full corpus."""

from __future__ import annotations

import json
import random
from pathlib import Path

from triplum.bench.inputs import Benchmark, materialize
from triplum.data.corpus import Document, chunk_id
from triplum.eval.inputs import Question, Triple
from triplum.utils.data import RecordDataset

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
FIXTURE_N = 20


def path(name: str) -> Path:
    return FIXTURE_DIR / f"{name}.json"


def write(name: str, benchmark: Benchmark, target: Path | None = None) -> Path:
    """Serialise every part's records; runs the integrity checks first."""
    materialize(benchmark)
    payload: dict[str, list] = {}
    if benchmark.corpus is not None:
        payload["documents"] = [d.model_dump(mode="json") for d in benchmark.corpus]
    if benchmark.qa is not None:
        payload["questions"] = [q.model_dump(mode="json") for q in benchmark.qa]
    if benchmark.extraction is not None:
        payload["triples"] = [t.model_dump(mode="json") for t in benchmark.extraction]
    target = target or path(name)
    target.write_text(json.dumps(payload, ensure_ascii=False))
    return target


def read(name: str, n: int | None = None, source: Path | None = None) -> Benchmark:
    payload = json.loads((source or path(name)).read_text())
    questions = [Question.model_validate(q) for q in payload.get("questions", [])]
    return Benchmark(
        name=name,
        corpus=RecordDataset([Document.model_validate(d) for d in payload["documents"]])
        if "documents" in payload
        else None,
        qa=RecordDataset(questions[:n] if n is not None else questions)
        if "questions" in payload
        else None,
        extraction=RecordDataset([Triple.model_validate(t) for t in payload["triples"]])
        if "triples" in payload
        else None,
        needs=None,
    )


def subset(
    benchmark: Benchmark, n: int = FIXTURE_N, distractors: int = 40, seed: int = 0
) -> Benchmark:
    """The first `n` questions, every chunk they need (gold, and candidate ids from `metadata`),
    and up to `distractors` further chunks chosen with a fixed seed; without questions, the first
    `distractors` chunks. Triples of the kept documents and questions come along."""
    documents = list(benchmark.corpus) if benchmark.corpus is not None else []
    questions = list(benchmark.qa)[:n] if benchmark.qa is not None else []
    all_ids = [cid for d in documents for cid in d.chunk_ids()]
    keep: set[int] = set()
    for q in questions:
        keep.update(q.gold)
        keep.update(q.metadata.get("candidate_chunk_ids", []))
    keep &= set(all_ids)  # candidate ids are hints; a context paragraph may be absent upstream
    rest = [c for c in all_ids if c not in keep]
    if not questions:
        keep.update(rest[:distractors])
    else:
        keep.update(random.Random(seed).sample(rest, min(distractors, len(rest))))
    kept_docs = []
    for d in documents:
        segments = tuple(s for s in d.segments if chunk_id(d.id, s.ordinal) in keep)
        if segments:
            kept_docs.append(d.model_copy(update={"segments": segments}))
    doc_ids = {d.id for d in kept_docs}
    qids = {q.id for q in questions}
    triples = (
        [
            t
            for t in benchmark.extraction
            if t.document_id in doc_ids or (t.question_id is not None and t.question_id in qids)
        ]
        if benchmark.extraction is not None
        else None
    )
    return Benchmark(
        name=benchmark.name,
        corpus=RecordDataset(kept_docs) if benchmark.corpus is not None else None,
        qa=RecordDataset(questions) if benchmark.qa is not None else None,
        extraction=RecordDataset(triples) if triples is not None else None,
        needs=benchmark.needs,
    )
