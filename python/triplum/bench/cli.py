"""triplum CLI: data fetch | bench run, sweep, report, show, rerun, inspect, diff, tail.

The command surface is documented in docs/flow.md; `main(argv)` runs it in-process for tests.
"""

import json
import shutil
import sqlite3
import sys
import time
from contextlib import closing
from dataclasses import replace
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
from triplum.bench.selection import SelectionGroup, adapter, no_input_callback, resolve

app = typer.Typer(
    cls=SelectionGroup, no_args_is_help=True, add_completion=False, pretty_exceptions_enable=False
)
data_app = typer.Typer(
    cls=SelectionGroup, no_args_is_help=False, help="List, fetch and verify the benchmark datasets."
)
bench_app = typer.Typer(
    cls=SelectionGroup, no_args_is_help=False, help="Run, look up and inspect benchmarks."
)
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
DatasetOpt = Annotated[str | None, typer.Option(help="Benchmark dataset: " + ", ".join(Dataset))]
RunIdArg = Annotated[str | None, typer.Argument(help="Run id or unique prefix.")]
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


NoInputOpt = Annotated[
    bool,
    typer.Option(
        "--no-input",
        is_eager=True,
        callback=no_input_callback,
        help="Never prompt; unresolved choices are usage errors.",
    ),
]


@app.callback()
def root(no_input: NoInputOpt = False) -> None:
    """Composable knowledge-graph benchmarks."""


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


def _print_summary(df) -> None:
    from triplum.bench.report import format_summary

    print(format_summary(df, width=shutil.get_terminal_size().columns))


def _runstore(path: Path | None):
    from triplum.bench.runstore import RunStore
    from triplum.cache import default_root

    return RunStore(path or default_root() / "runs.db")


@data_app.callback(invoke_without_command=True)
def data(ctx: typer.Context, no_input: NoInputOpt = False) -> None:
    """List supported datasets and the state of their local protocol files."""
    if ctx.invoked_subcommand is not None:
        return
    from triplum.eval.datasets import hipporag as hr

    states = [hr.status(name) for name in hr.FILES]
    print(f"data root: {states[0].questions_path.parent}")
    for state in states:
        print(f"{state.name}: {state.state}")
    print("States: verified = local files match pinned SHA-256; partial = one local file;")
    print("        not downloaded = no local files; invalid = one or both local hashes mismatch.")
    print(
        "Fetch: downloads missing files, then verifies both; it does not overwrite invalid files."
    )
    if any(state.state != "verified" for state in states):
        print("Run `triplum data fetch` to download missing datasets; remove invalid files first.")
    print()
    print(ctx.get_help())


@data_app.command()
def fetch(
    ctx: typer.Context,
    no_input: NoInputOpt = False,
    dataset: Annotated[str, typer.Option(help="hotpotqa | musique | twowiki | all")] = "all",
) -> None:
    """Download the HippoRAG protocol files and verify their sha256."""
    from triplum.eval.datasets import hipporag as hr

    dataset = resolve(dataset, [*hr.FILES, "all"], "dataset", ctx=ctx)
    for name in hr.FILES if dataset == "all" else [dataset]:
        qp, cp = hr.fetch(name)
        print(f"{name}: {qp} {cp} (verified)")


@bench_app.callback(invoke_without_command=True)
def bench(
    ctx: typer.Context,
    no_input: NoInputOpt = False,
    runstore: Annotated[Path | None, typer.Option(help="Run store for this overview only.")] = None,
) -> None:
    """Show recent local runs, explain their states, and list available commands."""
    if ctx.invoked_subcommand is not None:
        return
    from triplum.cache import default_root

    path = runstore or default_root() / "runs.db"
    print(f"run store: {path}")
    print("Pipelines: " + ", ".join(Pipeline))
    rows = []
    if path.exists():
        # RunStore initialization creates tables and migrates; an overview only reads.
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            rows = conn.execute(
                "SELECT run_id, dataset, pipeline, n, status FROM runs"
                " ORDER BY created_at DESC, run_id DESC LIMIT 10"
            ).fetchall()
    if rows:
        print("Recent local runs (up to 10, newest first):")
        for run_id, dataset, pipeline, n, status in rows:
            print(f"{run_id}: {dataset}/{pipeline}  n={n}  status={status}")
    else:
        print("No local benchmark runs recorded.")
    print("States: ok = completed; failed = ended with an error;")
    print("        running = no completion recorded, possibly interrupted.")
    print("run: executes a benchmark or reuses identical completed runs.")
    print("report: reads saved metrics; rerun: reuses a run's configuration,")
    print("        --resume continues unfinished work, --force recomputes it.")
    print()
    print(ctx.get_help())


@bench_app.command()
def run(
    ctx: typer.Context,
    pipeline: Annotated[
        str | None, typer.Option(help="Retrieval pipeline: " + ", ".join(Pipeline))
    ] = None,
    dataset: DatasetOpt = None,
    no_input: NoInputOpt = False,
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

    pipeline = resolve(pipeline, Pipeline, "pipeline", ctx=ctx)
    dataset = resolve(dataset, Dataset, "dataset", ctx=ctx)
    reader = resolve(reader, ["fake", "openai", "claude-cli"], "reader", ctx=ctx)
    if judge is not None:
        judge = resolve(judge, ["fake", "openai", "claude-cli"], "judge", ctx=ctx)
    embedder = adapter(embedder, ["fake", "st", "openai"], "embedder", ctx)
    reranker = adapter(reranker, ["fake", "cross_encoder"], "reranker", ctx)
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
    _print_summary(summary(_runstore(runstore_path(cfg)), [rid]))


@bench_app.command()
def sweep(
    ctx: typer.Context,
    embedders: Annotated[Path, typer.Option(help="JSON file: list of EmbedderConfig dicts.")],
    dataset: DatasetOpt = None,
    no_input: NoInputOpt = False,
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

    dataset = resolve(dataset, Dataset, "dataset", ctx=ctx)
    reader = resolve(reader, ["fake", "openai", "claude-cli"], "reader", ctx=ctx)
    if judge is not None:
        judge = resolve(judge, ["fake", "openai", "claude-cli"], "judge", ctx=ctx)
    reranker = adapter(reranker, ["fake", "cross_encoder"], "reranker", ctx)
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
        assert c.pipeline.embedder is not None  # Every sweep config has an embedding spec.
        try:
            ids.append(run_benchmark(c))
        except Exception as e:  # noqa: BLE001  one bad spec must not stop the sweep
            failed.append((c.pipeline.embedder.model, f"{type(e).__name__}: {e}"))
            print(f"FAILED {failed[-1][0]}: {failed[-1][1]}", file=sys.stderr)
    if ids:
        _print_summary(summary(_runstore(runstore_path(cfgs[0])), ids))
    if failed:
        print(f"{len(failed)} spec(s) failed: " + ", ".join(m for m, _ in failed), file=sys.stderr)
    if failed or not ids:
        raise typer.Exit(1)


@bench_app.command()
def report(runstore: RunstoreOpt = None, no_input: NoInputOpt = False) -> None:
    """Summary of every run, wrapped to fit the terminal."""
    from triplum.bench.report import summary

    _print_summary(summary(_runstore(runstore)))


def _existing_runstore(path: Path | None):
    from triplum.cache import default_root

    path = path or default_root() / "runs.db"
    if not path.exists():
        raise typer.BadParameter(f"No runs recorded at {path}. Run `triplum bench run` first.")
    return _runstore(path)


def _run_id(rs, value: str | None, ctx: typer.Context, label: str = "run") -> str:
    rows = rs.conn.execute(
        "SELECT run_id, dataset, pipeline, status, n, reader_model, embedding_spec "
        "FROM runs ORDER BY created_at DESC, run_id"
    ).fetchall()
    return resolve(
        value,
        [r[0] for r in rows],
        label,
        ctx=ctx,
        descriptions={
            r[0]: f"{r[1]}/{r[2]}  {r[3]}  n={r[4]} reader={r[5]} embedding={r[6]}" for r in rows
        },
    )


@bench_app.command()
def show(
    ctx: typer.Context,
    run_id: RunIdArg = None,
    runstore: RunstoreOpt = None,
    no_input: NoInputOpt = False,
) -> None:
    """Print a run's identity fields and its full configuration."""
    rs = _existing_runstore(runstore)
    with closing(rs.conn):
        row = rs.run(_run_id(rs, run_id, ctx))
        identity = {k: row[k] for k in row if k != "config_json"}
        print(
            json.dumps({"identity": identity, "config": json.loads(row["config_json"])}, indent=2)
        )


@bench_app.command()
def rerun(
    ctx: typer.Context,
    run_id: RunIdArg = None,
    force: ForceOpt = False,
    resume: ResumeOpt = False,
    runstore: RunstoreOpt = None,
    no_input: NoInputOpt = False,
) -> None:
    """Run a stored configuration again (lookup unless --force)."""
    from triplum.bench.report import summary
    from triplum.bench.runner import run_benchmark

    rs = _existing_runstore(runstore)
    with closing(rs.conn):
        run_id = _run_id(rs, run_id, ctx)
        cfg = RunConfig.from_json(rs.run(run_id)["config_json"])
        cfg = replace(cfg, force=force, resume=resume, runstore_path=str(rs.path))
        rid = run_benchmark(cfg)
        print("reused" if rid == run_id else "new", rid)
        _print_summary(summary(rs, [rid]))


@bench_app.command()
def inspect(
    ctx: typer.Context,
    run_id: RunIdArg = None,
    no_input: NoInputOpt = False,
    question: Annotated[str | None, typer.Option(help="Only this question id.")] = None,
    json_: Annotated[bool, typer.Option("--json", help="Print the raw view as JSON.")] = False,
    runstore: RunstoreOpt = None,
) -> None:
    """Per-question drill-down: answer, metrics, retrieved passages, model calls."""
    from triplum.bench.inspect import inspect_run

    rs = _existing_runstore(runstore)
    with closing(rs.conn):
        run_id = _run_id(rs, run_id, ctx)
        if question is not None:
            ids = [
                r[0]
                for r in rs.conn.execute(
                    "SELECT question_id FROM run_questions WHERE run_id = ? ORDER BY question_id",
                    (run_id,),
                )
            ]
            question = resolve(question, ids, "question", ctx=ctx)
        view = inspect_run(rs, run_id, question)
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
def diff(
    ctx: typer.Context,
    run_a: RunIdArg = None,
    run_b: RunIdArg = None,
    runstore: RunstoreOpt = None,
    no_input: NoInputOpt = False,
) -> None:
    """Identity and config fields that differ, metric means, per-question deltas."""
    import polars as pl

    from triplum.bench.inspect import diff_runs

    rs = _existing_runstore(runstore)
    with closing(rs.conn):
        run_a = _run_id(rs, run_a, ctx, "first run")
        run_b = _run_id(rs, run_b, ctx, "second run")
        d = diff_runs(rs, run_a, run_b)
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
    ctx: typer.Context,
    run_id: RunIdArg = None,
    no_input: NoInputOpt = False,
    once: Annotated[bool, typer.Option("--once", help="Print once instead of following.")] = False,
    interval: Annotated[float, typer.Option(help="Seconds between updates.")] = 1.0,
    runstore: RunstoreOpt = None,
) -> None:
    """Progress of a running benchmark: done/total and the latest stage."""
    from triplum.bench.inspect import tail_run

    rs = _existing_runstore(runstore)
    with closing(rs.conn):
        run_id = _run_id(rs, run_id, ctx)
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
