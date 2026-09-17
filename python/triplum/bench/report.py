"""Summary frames over the run store."""

from __future__ import annotations

import json
import textwrap

import polars as pl

from triplum.bench.runstore import RunStore


def format_summary(frame: pl.DataFrame, width: int = 80) -> str:
    """Render all summary fields as wrapped per-run blocks, without truncating identifiers."""
    if frame.is_empty():
        return "No benchmark runs recorded."
    blocks = []
    for row in frame.iter_rows(named=True):
        header = textwrap.fill(f"Run {row['run_id']}", width=width)
        fields = []
        for key, value in row.items():
            if key == "run_id":
                continue
            value = (
                "n/a"
                if value is None
                else f"{value:.6g}"
                if isinstance(value, float)
                else str(value)
            )
            fields.append(f"{key}={value}")
        body = textwrap.fill(
            "  ".join(fields),
            width=width,
            initial_indent="  ",
            subsequent_indent="  ",
            break_on_hyphens=False,
        )
        blocks.append(f"{header}\n{body}")
    return "\n\n".join(blocks)


def summary(rs: RunStore, run_ids: list[str] | None = None) -> pl.DataFrame:
    """One row per QA run; extraction runs are summarised by `extraction_summary`."""
    runs = rs.runs().filter(pl.col("kind") == "qa")
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
                "n_chunks": q["n_chunks"].mean(),
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


def extraction_summary(rs: RunStore, run_ids: list[str] | None = None) -> pl.DataFrame:
    """One row per extraction run: identity, the intrinsic scores and the graph counts."""
    runs = rs.runs().filter(pl.col("kind") == "extract")
    if run_ids:
        runs = runs.filter(pl.col("run_id").is_in(run_ids))
    rows = []
    for r in runs.iter_rows(named=True):
        x = rs.extraction(r["run_id"]) or {}
        cfg = json.loads(r["config_json"])
        rows.append(
            {
                "run_id": r["run_id"],
                "dataset": r["dataset"],
                "extractor": cfg["extractor"]["kind"],
                "resolver": cfg["resolver"]["name"],
                "n_chunks": r["n"],
                **{k: v for k, v in x.items() if k != "run_id"},
                "wall_s": r["wall_s"],
            }
        )
    return pl.DataFrame(rows)
