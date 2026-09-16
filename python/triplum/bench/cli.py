"""triplum CLI: data fetch | bench run, sweep, report, show, rerun, inspect, diff, tail.

The command surface is documented in docs/flow.md; `main(argv)` runs it in-process for tests.
"""

import json
import sys
import time
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from triplum.bench.config import (
    EmbedderConfig,
    LLMConfig,
    PipelineConfig,
    RerankerConfig,
    RunConfig,
)

app = typer.Typer(no_args_is_help=True, add_completion=False, pretty_exceptions_enable=False)
data_app = typer.Typer(no_args_is_help=True, help="Fetch and verify the benchmark datasets.")
bench_app = typer.Typer(no_args_is_help=True, help="Run, look up and inspect benchmarks.")
app.add_typer(data_app, name="data")
app.add_typer(bench_app, name="bench")

CLAUDE_ARGV = ("claude", "-p", "--output-format", "json")


class Pipeline(StrEnum):
    closed_book = "closed_book"
    bm25 = "bm25"
    dense = "dense"
    hybrid = "hybrid"
    oracle = "oracle"


class Dataset(StrEnum):
    hotpotqa = "hotpotqa"
    musique = "musique"
    twowiki = "twowiki"


# Options shared by `bench run` and `bench sweep`.
DatasetOpt = Annotated[Dataset, typer.Option(help="Benchmark dataset.")]
NOpt = Annotated[int | None, typer.Option(help="Questions to run (default: the whole protocol).")]
FixtureOpt = Annotated[
    bool, typer.Option("--fixture", help="Use the committed 20-question fixture.")
]
ReaderOpt = Annotated[str, typer.Option(help="Reader LLM: fake | openai | claude-cli.")]
ReaderModelOpt = Annotated[str | None, typer.Option(help="Reader model id (default per kind).")]
BaseUrlOpt = Annotated[str | None, typer.Option(help="OpenAI-compatible base URL.")]
JudgeOpt = Annotated[str | None, typer.Option(help="Judge LLM: fake | openai | claude-cli.")]
JudgeModelOpt = Annotated[str | None, typer.Option(help="Judge model id (default per kind).")]
RerankerOpt = Annotated[str, typer.Option(help="fake | cross_encoder:<model> (hybrid only).")]
TopKOpt = Annotated[int, typer.Option(help="Passages handed to the reader.")]
CandidatesOpt = Annotated[int, typer.Option(help="Fused candidates to rerank (hybrid only).")]
ForceOpt = Annotated[
    bool, typer.Option("--force", help="Recompute even if an identical run exists.")
]
ResumeOpt = Annotated[
    bool, typer.Option("--resume", help="Continue a crashed run with this identity.")
]
CacheRootOpt = Annotated[
    Path | None, typer.Option(help="Cache root (default $TRIPLUM_CACHE or ~/.cache/triplum).")
]
RunstoreOpt = Annotated[Path | None, typer.Option(help="Run store (default <cache root>/runs.db).")]


def _llm(kind: str, model: str | None, base_url: str | None) -> LLMConfig:
    if kind == "fake":
        return LLMConfig(kind="fake")
    if kind == "openai":
        return LLMConfig(kind="openai", model=model or "gpt-5.6-luna", base_url=base_url)
    if kind == "claude-cli":
        return LLMConfig(
            kind="cli", model=model or "claude-cli", argv=CLAUDE_ARGV, json_field="result"
        )
    raise typer.BadParameter(f"unknown LLM kind {kind!r}")


def _embedder(spec: dict | str) -> EmbedderConfig:
    if isinstance(spec, str):
        if spec == "fake":
            return EmbedderConfig(kind="fake", dims=64)
        if spec.startswith("st:"):
            return EmbedderConfig(kind="st", model=spec[3:])
        if spec.startswith("openai:"):
            model = spec[7:]
            return EmbedderConfig(
                kind="openai", model=model, dims=3072 if "large" in model else 1536
            )
        raise typer.BadParameter(f"unknown embedder {spec!r}")
    return EmbedderConfig(**spec)


def build_run_config(
    *,
    pipeline: str,
    dataset: str,
    embedder: dict | str,
    n: int | None,
    fixture: bool,
    reader: str,
    reader_model: str | None,
    base_url: str | None,
    judge: str | None,
    judge_model: str | None,
    reranker: str,
    top_k: int,
    candidates: int,
    force: bool,
    resume: bool,
    cache_root: Path | None,
    runstore: Path | None,
) -> RunConfig:
    rr = (
        RerankerConfig(kind="fake")
        if reranker == "fake"
        else RerankerConfig(kind="cross_encoder", model=reranker.split(":", 1)[1])
    )
    cfg = PipelineConfig(
        name=str(pipeline),
        reader=_llm(reader, reader_model, base_url),
        top_k=top_k,
        candidates=candidates,
        embedder=_embedder(embedder),
        reranker=rr if pipeline == "hybrid" else None,
    )
    return RunConfig(
        dataset=str(dataset),
        pipeline=cfg,
        n=n,
        fixture=fixture,
        judge=_llm(judge, judge_model, base_url) if judge else None,
        force=force,
        resume=resume,
        cache_root=str(cache_root) if cache_root else None,
        runstore_path=str(runstore) if runstore else None,
    )


def _print(df) -> None:
    import polars as pl

    with pl.Config(tbl_cols=-1, tbl_width_chars=220, tbl_rows=100):
        print(df)


def _runstore(path: Path | None):
    from triplum.bench.runstore import RunStore
    from triplum.cache import default_root

    return RunStore(path or default_root() / "runs.db")


@data_app.command()
def fetch(
    dataset: Annotated[str, typer.Option(help="hotpotqa | musique | twowiki | all")] = "all",
) -> None:
    """Download the HippoRAG protocol files and verify their sha256."""
    from triplum.eval.datasets import hipporag as hr

    for name in hr.FILES if dataset == "all" else [dataset]:
        qp, cp = hr.fetch(name)
        print(f"{name}: {qp} {cp} (verified)")


@bench_app.command()
def run(
    pipeline: Annotated[Pipeline, typer.Option(help="Retrieval pipeline.")],
    dataset: DatasetOpt,
    embedder: Annotated[str, typer.Option(help="fake | st:<model> | openai:<model>")] = "fake",
    n: NOpt = None,
    fixture: FixtureOpt = False,
    reader: ReaderOpt = "fake",
    reader_model: ReaderModelOpt = None,
    base_url: BaseUrlOpt = None,
    judge: JudgeOpt = None,
    judge_model: JudgeModelOpt = None,
    reranker: RerankerOpt = "fake",
    top_k: TopKOpt = 5,
    candidates: CandidatesOpt = 20,
    force: ForceOpt = False,
    resume: ResumeOpt = False,
    cache_root: CacheRootOpt = None,
    runstore: RunstoreOpt = None,
) -> None:
    """Run one pipeline; an identical configuration returns the stored run."""
    from triplum.bench.report import summary
    from triplum.bench.runner import run_benchmark, runstore_path

    cfg = build_run_config(
        pipeline=pipeline,
        dataset=dataset,
        embedder=embedder,
        n=n,
        fixture=fixture,
        reader=reader,
        reader_model=reader_model,
        base_url=base_url,
        judge=judge,
        judge_model=judge_model,
        reranker=reranker,
        top_k=top_k,
        candidates=candidates,
        force=force,
        resume=resume,
        cache_root=cache_root,
        runstore=runstore,
    )
    rid = run_benchmark(cfg)
    _print(summary(_runstore(runstore_path(cfg)), [rid]))


@bench_app.command()
def sweep(
    embedders: Annotated[Path, typer.Option(help="JSON file: list of EmbedderConfig dicts.")],
    dataset: DatasetOpt,
    n: NOpt = None,
    fixture: FixtureOpt = False,
    reader: ReaderOpt = "fake",
    reader_model: ReaderModelOpt = None,
    base_url: BaseUrlOpt = None,
    judge: JudgeOpt = None,
    judge_model: JudgeModelOpt = None,
    reranker: RerankerOpt = "fake",
    top_k: TopKOpt = 5,
    candidates: CandidatesOpt = 20,
    force: ForceOpt = False,
    resume: ResumeOpt = False,
    cache_root: CacheRootOpt = None,
    runstore: RunstoreOpt = None,
) -> None:
    """Run the dense pipeline once per embedding spec; failed specs are reported, not fatal."""
    from triplum.bench.report import summary
    from triplum.bench.runner import run_benchmark, runstore_path

    cfgs = [
        build_run_config(
            pipeline=Pipeline.dense,
            dataset=dataset,
            embedder=spec,
            n=n,
            fixture=fixture,
            reader=reader,
            reader_model=reader_model,
            base_url=base_url,
            judge=judge,
            judge_model=judge_model,
            reranker=reranker,
            top_k=top_k,
            candidates=candidates,
            force=force,
            resume=resume,
            cache_root=cache_root,
            runstore=runstore,
        )
        for spec in json.loads(embedders.read_text())
    ]
    ids, failed = [], []
    for c in cfgs:
        try:
            ids.append(run_benchmark(c))
        except Exception as e:  # noqa: BLE001  one bad spec must not stop the sweep
            failed.append((c.pipeline.embedder.model, f"{type(e).__name__}: {e}"))
            print(f"FAILED {failed[-1][0]}: {failed[-1][1]}", file=sys.stderr)
    if ids:
        _print(summary(_runstore(runstore_path(cfgs[0])), ids))
    if failed:
        print(f"{len(failed)} spec(s) failed: " + ", ".join(m for m, _ in failed), file=sys.stderr)
    if failed or not ids:
        raise typer.Exit(1)


@bench_app.command()
def report(runstore: RunstoreOpt = None) -> None:
    """Summary table of every run in the store."""
    from triplum.bench.report import summary

    _print(summary(_runstore(runstore)))


def _row(rs, run_id: str) -> dict:
    row = rs.run(run_id)
    if row is None:
        raise typer.BadParameter(f"no run {run_id}")
    return row


@bench_app.command()
def show(run_id: str, runstore: RunstoreOpt = None) -> None:
    """Print a run's identity fields and its full configuration."""
    row = _row(_runstore(runstore), run_id)
    identity = {k: row[k] for k in row if k != "config_json"}
    print(json.dumps({"identity": identity, "config": json.loads(row["config_json"])}, indent=2))


@bench_app.command()
def rerun(
    run_id: str, force: ForceOpt = False, resume: ResumeOpt = False, runstore: RunstoreOpt = None
) -> None:
    """Run a stored configuration again (lookup unless --force)."""
    from triplum.bench.report import summary
    from triplum.bench.runner import run_benchmark

    rs = _runstore(runstore)
    cfg = RunConfig.from_json(_row(rs, run_id)["config_json"])
    cfg = RunConfig(
        **{**cfg.__dict__, "force": force, "resume": resume, "runstore_path": str(rs.path)}
    )
    rid = run_benchmark(cfg)
    print("reused" if rid == run_id else "new", rid)
    _print(summary(rs, [rid]))


@bench_app.command()
def inspect(
    run_id: str,
    question: Annotated[str | None, typer.Option(help="Only this question id.")] = None,
    json_: Annotated[bool, typer.Option("--json", help="Print the raw view as JSON.")] = False,
    runstore: RunstoreOpt = None,
) -> None:
    """Per-question drill-down: answer, metrics, retrieved passages, model calls."""
    from triplum.bench.inspect import inspect_run

    view = inspect_run(_runstore(runstore), run_id, question)
    if json_:
        print(json.dumps(view, indent=2, default=str))
        return
    i = view["identity"]
    print(
        f"run {i['run_id']}  {i['dataset']}/{i['pipeline']}  status={i['status']}  n={i['n']}"
        f"  reader={i['reader_model']}  judge={i['judge_model']}"
    )
    if not view["store_available"]:
        print("(store artifact not available: passages shown as ids only)")
    for q in view["questions"]:
        m = q["metrics"]
        print(
            f"\n[{q['question_id']}] answer={q['answer']!r}  em={m['em']} f1={m['f1']:.2f}"
            f" contain={m['contain']} judge={m['judge']} r2={m['r2']:.2f} r5={m['r5']:.2f}"
            f" latency={m['latency_s']:.3f}s usd={m['usd']}"
        )
        for r in q["retrieved"]:
            text = (r["text"] or "").replace("\n", " ")[:160]
            print(f"    #{r['chunk_id']}: {text}")
        for e in q["events"]:
            print(
                f"    {e['stage']}: {e['model']} in={e['input_tokens']} out={e['output_tokens']}"
                f" cached={e['cached']} {(e['ended_at'] - e['started_at']) / 1e6:.3f}s"
            )


@bench_app.command()
def diff(run_a: str, run_b: str, runstore: RunstoreOpt = None) -> None:
    """Identity and config fields that differ, metric means, per-question deltas."""
    import polars as pl

    from triplum.bench.inspect import diff_runs

    d = diff_runs(_runstore(runstore), run_a, run_b)
    print("identity:", json.dumps(d["identity_diff"], default=str))
    print("config:", json.dumps(d["config_diff"], default=str))
    for m, (va, vb) in d["means"].items():
        print(f"  {m:8s} {va!s:>10} -> {vb!s:>10}")
    if d["only_in_a"] or d["only_in_b"]:
        print(f"only in a: {len(d['only_in_a'])}  only in b: {len(d['only_in_b'])}")
    changed = (
        (pl.col("d_em") != 0)
        | (pl.col("d_f1") != 0)
        | (pl.col("d_r5") != 0)
        | pl.col("answer_changed")
        | pl.col("retrieval_changed")
    )
    _print(d["per_question"].filter(changed))


@bench_app.command()
def tail(
    run_id: str,
    once: Annotated[bool, typer.Option("--once", help="Print once instead of following.")] = False,
    interval: Annotated[float, typer.Option(help="Seconds between updates.")] = 1.0,
    runstore: RunstoreOpt = None,
) -> None:
    """Progress of a running benchmark: done/total and the latest stage."""
    from triplum.bench.inspect import tail_run

    rs = _runstore(runstore)
    while True:
        t = tail_run(rs, run_id)
        print(
            f"{t['run_id']} {t['status']} {t['done']}/{t['total']} last={t['last_stage']}@{t['last_question']}"
        )
        if once or t["status"] != "running":
            return
        time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    """Run the CLI in-process (tests): returns the exit code instead of calling sys.exit."""
    rv = app(args=argv, standalone_mode=False)
    return rv if isinstance(rv, int) else 0


if __name__ == "__main__":
    app()
