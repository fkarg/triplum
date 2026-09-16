"""Summary frames over the run store."""

from __future__ import annotations

import polars as pl

from triplum.bench.runstore import RunStore


def summary(rs: RunStore, run_ids: list[str] | None = None) -> pl.DataFrame:
    runs = rs.runs()
    if run_ids:
        runs = runs.filter(pl.col("run_id").is_in(run_ids))
    rows = []
    for r in runs.iter_rows(named=True):
        q = rs.questions(r["run_id"])
        ev = rs.events(r["run_id"])
        idx = ev.filter(pl.col("stage").str.starts_with("index."))
        rows.append(
            {
                "run_id": r["run_id"],
                "dataset": r["dataset"],
                "pipeline": r["pipeline"],
                "n": q.height,
                "reader_model": r["reader_model"],
                "embedding_spec": r["embedding_spec"],
                "em": q["em"].mean(),
                "f1": q["f1"].mean(),
                "contain": q["contain"].mean(),
                "judge": q["judge"].mean(),
                "r2": q["r2"].mean(),
                "r5": q["r5"].mean(),
                "n_passages": q["n_passages"].mean(),
                "latency_s": q["latency_s"].mean(),
                "usd_per_q": q["usd"].mean(),
                "usd_total": q["usd"].sum(),
                "usd_spent": ev.filter(pl.col("cached") == 0)["usd"].sum(),
                "indexing_s": float((idx["ended_at"] - idx["started_at"]).sum() or 0) / 1e6,
                "cache_hits": r["cache_hits"],
                "cache_misses": r["cache_misses"],
                "wall_s": r["wall_s"],
            }
        )
    return pl.DataFrame(rows)
