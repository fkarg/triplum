"""Pure projections over the run store for human-facing tooling: inspect, diff, tail.
No printing here; the CLI renders. Passage text is resolved from the run's store artifact when it
still exists at the recorded path."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import polars as pl

from triplum.bench.runstore import RunStore
from triplum.data.viewer import Viewer

METRICS = [
    "em",
    "f1",
    "contain",
    "judge",
    "r2",
    "r5",
    "latency_s",
    "usd",
    "input_tokens",
    "output_tokens",
]


@dataclass(frozen=True)
class QuestionView:
    question_id: str
    answer: str
    metrics: dict
    retrieved: list[dict]  # {chunk_id, text|None}
    events: list[dict]


def _store_for(rs: RunStore, run_id: str):
    artifact = rs.artifact(run_id, "store")
    if artifact is None or not Path(artifact[0]).exists():
        return None
    from triplum.store.sqlite.store import SqliteStore

    return SqliteStore(artifact[0])


def inspect_run(rs: RunStore, run_id: str, question_id: str | None = None) -> dict:
    run = rs.run(run_id)
    if run is None:
        raise KeyError(run_id)
    qs = rs.questions(run_id)
    if question_id is not None:
        qs = qs.filter(pl.col("question_id") == question_id)
    ev = rs.events(run_id)
    store = _store_for(rs, run_id)
    principals = json.loads(run["viewer_json"])
    viewer = Viewer(principals=frozenset(principals)) if principals else None
    views = []
    for q in qs.iter_rows(named=True):
        ids = json.loads(q["retrieved_json"])
        texts: dict[int, str] = {}
        if store is not None and ids and viewer is not None:
            chunks = store.get_chunks(ids, viewer)
            texts = dict(zip(chunks["id"].to_list(), chunks["text"].to_list()))
        views.append(
            QuestionView(
                question_id=q["question_id"],
                answer=q["answer"],
                metrics={m: q[m] for m in METRICS},
                retrieved=[{"chunk_id": c, "text": texts.get(c)} for c in ids],
                events=ev.filter(pl.col("question_id") == q["question_id"]).to_dicts(),
            )
        )
    if store is not None:
        store.close()
    identity = {k: v for k, v in run.items() if k != "config_json"}
    return {
        "identity": identity,
        "config": json.loads(run["config_json"]),
        "questions": [asdict(v) for v in views],
        "store_available": store is not None,
    }


def _flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def diff_runs(rs: RunStore, run_a: str, run_b: str) -> dict:
    a, b = rs.run(run_a), rs.run(run_b)
    if a is None or b is None:
        raise KeyError(run_a if a is None else run_b)
    fa, fb = _flatten(json.loads(a["config_json"])), _flatten(json.loads(b["config_json"]))
    config_diff = {
        k: (fa.get(k), fb.get(k)) for k in sorted(set(fa) | set(fb)) if fa.get(k) != fb.get(k)
    }
    id_fields = [
        "dataset",
        "pipeline",
        "config_hash",
        "code_hash",
        "code_version",
        "dirty",
        "corpus_hash",
        "questions_hash",
        "n",
        "embedding_spec",
        "reranker_spec",
        "reader_model",
        "judge_model",
        "seed",
        "reader_prompt_hash",
        "judge_prompt_hash",
    ]
    identity_diff = {k: (a[k], b[k]) for k in id_fields if a[k] != b[k]}
    qa, qb = rs.questions(run_a), rs.questions(run_b)
    joined = qa.join(qb, on="question_id", how="full", suffix="_b", coalesce=True)
    only_a = joined.filter(pl.col("answer_b").is_null())["question_id"].to_list()
    only_b = joined.filter(pl.col("answer").is_null())["question_id"].to_list()
    both = joined.filter(pl.col("answer").is_not_null() & pl.col("answer_b").is_not_null())
    deltas = both.select(
        "question_id",
        *[
            (pl.col(f"{m}_b") - pl.col(m)).alias(f"d_{m}")
            for m in ("em", "f1", "contain", "r2", "r5")
        ],
        (pl.col("answer") != pl.col("answer_b")).alias("answer_changed"),
        (pl.col("retrieved_json") != pl.col("retrieved_json_b")).alias("retrieval_changed"),
    )
    means = {m: (qa[m].mean(), qb[m].mean()) for m in ("em", "f1", "contain", "judge", "r2", "r5")}
    return {
        "identity_diff": identity_diff,
        "config_diff": config_diff,
        "means": means,
        "only_in_a": only_a,
        "only_in_b": only_b,
        "per_question": deltas,
    }


def tail_run(rs: RunStore, run_id: str) -> dict:
    run = rs.run(run_id)
    if run is None:
        raise KeyError(run_id)
    done, last = rs.progress(run_id)
    return {
        "run_id": run_id,
        "status": run["status"],
        "done": done,
        "total": run["n"],
        "last_stage": last[0] if last else None,
        "last_question": last[1] if last else None,
        "last_event_at": last[2] if last else None,
        "created_at": run["created_at"],
    }
