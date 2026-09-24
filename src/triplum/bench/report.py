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


METRICS = ("em", "f1", "contain", "judge", "r2", "r5")


def _content(rs: RunStore, key: str, code: str | None, fallback: object) -> object:
    row = rs.artifact_row(key, code) if code else None
    return row["content_hash"] if row is not None else fallback


def _inputs(rs: RunStore, invocation_id: int) -> tuple:
    sig = []
    for inp in rs.invocation_inputs(invocation_id):
        if inp["kind"] == "artifact":
            sig.append(
                (inp["name"], _content(rs, inp["identity"], inp["code"], ("?", invocation_id)))
            )
        else:
            sig.append((inp["name"], inp["identity"]))
    return tuple(sig)


def variance(rs: RunStore, experiment_id: str) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Where the variance between the replicates of an experiment comes from. The first frame
    has one row per logical invocation (stages joined by structural key across replicates):
    whether the inputs' content agreed, whether the outputs' content agreed, the verdict
    (`deterministic`, `adds variance`, `absorbs variance`, `passes variance`), and how many
    replicates executed rather than fetched. The second frame has the mean and standard
    deviation of every metric over the replicates. Both measure variance under the seed policy
    the adapters declared, not all execution variance; a fetched stage was not observed."""
    runs = rs.runs().filter(pl.col("experiment_id") == experiment_id).sort("replicate")
    run_ids = runs["run_id"].to_list()
    groups: dict[str, list[dict]] = {}
    for rid in run_ids:
        for row in rs.invocations(rid).iter_rows(named=True):
            groups.setdefault(row["structural_key"], []).append(row)
    rows = []
    for skey, items in groups.items():
        outs = {_content(rs, it["key"], it["code"], ("?", it["id"])) for it in items}
        ins = {_inputs(rs, it["id"]) for it in items}
        inputs_agree, outputs_agree = len(ins) == 1, len(outs) == 1
        verdict = {
            (True, True): "deterministic",
            (True, False): "adds variance",
            (False, True): "absorbs variance",
            (False, False): "passes variance",
        }[inputs_agree, outputs_agree]
        rows.append(
            {
                "stage": items[0]["stage"].rsplit(":", 1)[-1],
                "structural_key": skey[:12],
                "replicates": len(items),
                "inputs_agree": inputs_agree,
                "outputs_agree": outputs_agree,
                "verdict": verdict,
                "executed": sum(1 for it in items if not it["fetched"]),
            }
        )
    stages = pl.DataFrame(
        rows,
        schema={
            "stage": pl.Utf8,
            "structural_key": pl.Utf8,
            "replicates": pl.Int64,
            "inputs_agree": pl.Boolean,
            "outputs_agree": pl.Boolean,
            "verdict": pl.Utf8,
            "executed": pl.Int64,
        },
    )
    means = {m: [] for m in METRICS}
    for rid in run_ids:
        q = rs.questions(rid)
        for m in METRICS:
            means[m].append(q[m].mean() if q.height else None)
    metric_rows = []
    for m in METRICS:
        series = pl.Series([v for v in means[m] if v is not None], dtype=pl.Float64)
        metric_rows.append(
            {
                "metric": m,
                "replicates": series.len(),
                "mean": series.mean() if series.len() else None,
                "std": series.std() if series.len() > 1 else None,
                "min": series.min() if series.len() else None,
                "max": series.max() if series.len() else None,
            }
        )
    metrics = pl.DataFrame(
        metric_rows,
        schema={
            "metric": pl.Utf8,
            "replicates": pl.Int64,
            "mean": pl.Float64,
            "std": pl.Float64,
            "min": pl.Float64,
            "max": pl.Float64,
        },
    )
    return stages, metrics
