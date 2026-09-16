"""triplum CLI: data fetch | bench run | bench sweep | bench report."""

from __future__ import annotations

import argparse
import json
import sys

from triplum.bench.config import (
    EmbedderConfig,
    LLMConfig,
    PipelineConfig,
    RerankerConfig,
    RunConfig,
)

PIPELINES = ["closed_book", "bm25", "dense", "hybrid", "oracle"]
DATASETS = ["hotpotqa", "musique", "twowiki"]
CLAUDE_ARGV = ("claude", "-p", "--output-format", "json")


def _llm(kind: str, model: str | None, base_url: str | None) -> LLMConfig:
    if kind == "fake":
        return LLMConfig(kind="fake")
    if kind == "openai":
        return LLMConfig(kind="openai", model=model or "gpt-5.6-luna", base_url=base_url)
    if kind == "claude-cli":
        return LLMConfig(
            kind="cli", model=model or "claude-cli", argv=CLAUDE_ARGV, json_field="result"
        )
    raise SystemExit(f"unknown reader kind {kind}")


def _embedder(spec: dict | str) -> EmbedderConfig:
    if isinstance(spec, str):
        if spec == "fake":
            return EmbedderConfig(kind="fake", dims=64)
        if spec.startswith("st:"):
            return EmbedderConfig(kind="st", model=spec[3:])
        if spec.startswith("openai:"):
            model = spec[7:]
            return EmbedderConfig(kind="openai", model=model, dims=3072 if "large" in model else 1536)
        raise SystemExit(f"unknown embedder {spec}")
    return EmbedderConfig(**spec)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="triplum")
    sub = p.add_subparsers(dest="cmd", required=True)
    data = sub.add_parser("data").add_subparsers(dest="data_cmd", required=True)
    data.add_parser("fetch").add_argument("--dataset", choices=[*DATASETS, "all"], default="all")
    bench = sub.add_parser("bench").add_subparsers(dest="bench_cmd", required=True)
    for name in ("run", "sweep"):
        b = bench.add_parser(name)
        if name == "run":
            b.add_argument("--pipeline", required=True, choices=PIPELINES)
            b.add_argument("--embedder", default="fake", help="fake | st:<model> | openai:<model>")
        else:
            b.add_argument("--embedders", required=True, help="JSON file: list of EmbedderConfig dicts")
        b.add_argument("--dataset", required=True, choices=DATASETS)
        b.add_argument("--n", type=int, default=None)
        b.add_argument("--fixture", action="store_true")
        b.add_argument("--reader", default="fake", help="fake | openai | claude-cli")
        b.add_argument("--reader-model", default=None)
        b.add_argument("--base-url", default=None)
        b.add_argument("--judge", default=None, help="fake | openai")
        b.add_argument("--judge-model", default=None)
        b.add_argument("--reranker", default="fake", help="fake | cross_encoder:<model>")
        b.add_argument("--top-k", type=int, default=5)
        b.add_argument("--candidates", type=int, default=20)
        b.add_argument("--force", action="store_true")
        b.add_argument("--resume", action="store_true")
        b.add_argument("--cache-root", default=None)
        b.add_argument("--runstore", default=None)
    rep = bench.add_parser("report")
    rep.add_argument("--runstore", default=None)
    show = bench.add_parser("show", help="print a run's exact configuration and identity")
    show.add_argument("run_id")
    show.add_argument("--runstore", default=None)
    rerun = bench.add_parser("rerun", help="run a stored configuration again (lookup unless --force)")
    rerun.add_argument("run_id")
    rerun.add_argument("--force", action="store_true")
    rerun.add_argument("--resume", action="store_true")
    rerun.add_argument("--runstore", default=None)
    insp = bench.add_parser("inspect", help="per-question drill-down: answer, metrics, passages, calls")
    insp.add_argument("run_id")
    insp.add_argument("--question", default=None)
    insp.add_argument("--json", action="store_true")
    insp.add_argument("--runstore", default=None)
    dif = bench.add_parser("diff", help="config, identity and per-question metric deltas of two runs")
    dif.add_argument("run_a")
    dif.add_argument("run_b")
    dif.add_argument("--runstore", default=None)
    tl = bench.add_parser("tail", help="progress of a running benchmark")
    tl.add_argument("run_id")
    tl.add_argument("--once", action="store_true")
    tl.add_argument("--interval", type=float, default=1.0)
    tl.add_argument("--runstore", default=None)
    return p.parse_args(argv)


def build_run_config(ns: argparse.Namespace, embedder: dict | str | None = None) -> RunConfig:
    reader = _llm(ns.reader, ns.reader_model, ns.base_url)
    judge = _llm(ns.judge, ns.judge_model, ns.base_url) if ns.judge else None
    rr = ns.reranker
    reranker = (
        RerankerConfig(kind="fake")
        if rr == "fake"
        else RerankerConfig(kind="cross_encoder", model=rr.split(":", 1)[1])
    )
    pipeline_name = getattr(ns, "pipeline", "dense")
    emb = _embedder(embedder if embedder is not None else getattr(ns, "embedder", "fake"))
    pipeline = PipelineConfig(
        name=pipeline_name,
        reader=reader,
        top_k=ns.top_k,
        candidates=ns.candidates,
        embedder=emb,
        reranker=reranker if pipeline_name == "hybrid" else None,
    )
    return RunConfig(
        dataset=ns.dataset,
        pipeline=pipeline,
        n=ns.n,
        fixture=ns.fixture,
        judge=judge,
        force=ns.force,
        resume=ns.resume,
        cache_root=ns.cache_root,
        runstore_path=ns.runstore,
    )


def _print(df) -> None:
    import polars as pl

    with pl.Config(tbl_cols=-1, tbl_width_chars=220, tbl_rows=100):
        print(df)


def _tooling(ns: argparse.Namespace) -> int:
    import time

    from triplum.bench.inspect import diff_runs, inspect_run, tail_run
    from triplum.bench.runstore import RunStore
    from triplum.cache import default_root

    rs = RunStore(ns.runstore or default_root() / "runs.db")
    if ns.bench_cmd == "inspect":
        view = inspect_run(rs, ns.run_id, ns.question)
        if ns.json:
            print(json.dumps(view, indent=2, default=str))
            return 0
        i = view["identity"]
        print(f"run {i['run_id']}  {i['dataset']}/{i['pipeline']}  status={i['status']}  n={i['n']}"
              f"  reader={i['reader_model']}  judge={i['judge_model']}")
        if not view["store_available"]:
            print("(store artifact not available: passages shown as ids only)")
        for q in view["questions"]:
            m = q["metrics"]
            print(f"\n[{q['question_id']}] answer={q['answer']!r}  em={m['em']} f1={m['f1']:.2f}"
                  f" contain={m['contain']} judge={m['judge']} r2={m['r2']:.2f} r5={m['r5']:.2f}"
                  f" latency={m['latency_s']:.3f}s usd={m['usd']}")
            for r in q["retrieved"]:
                text = (r["text"] or "").replace("\n", " ")[:160]
                print(f"    #{r['chunk_id']}: {text}")
            for e in q["events"]:
                print(f"    {e['stage']}: {e['model']} in={e['input_tokens']} out={e['output_tokens']}"
                      f" cached={e['cached']} {(e['ended_at'] - e['started_at']) / 1e6:.3f}s")
        return 0
    if ns.bench_cmd == "diff":
        d = diff_runs(rs, ns.run_a, ns.run_b)
        print("identity:", json.dumps(d["identity_diff"], default=str))
        print("config:", json.dumps(d["config_diff"], default=str))
        for m, (va, vb) in d["means"].items():
            print(f"  {m:8s} {va!s:>10} -> {vb!s:>10}")
        if d["only_in_a"] or d["only_in_b"]:
            print(f"only in a: {len(d['only_in_a'])}  only in b: {len(d['only_in_b'])}")
        changed = d["per_question"].filter(pl_any_change())
        _print(changed)
        return 0
    while True:
        t = tail_run(rs, ns.run_id)
        print(f"{t['run_id']} {t['status']} {t['done']}/{t['total']} last={t['last_stage']}@{t['last_question']}")
        if ns.once or t["status"] != "running":
            return 0
        time.sleep(ns.interval)


def pl_any_change():
    import polars as pl

    return (
        (pl.col("d_em") != 0) | (pl.col("d_f1") != 0) | (pl.col("d_r5") != 0)
        | pl.col("answer_changed") | pl.col("retrieval_changed")
    )


def main(argv: list[str] | None = None) -> int:
    ns = parse_args(sys.argv[1:] if argv is None else argv)
    if ns.cmd == "data":
        from triplum.eval.datasets import hipporag as hr

        for name in hr.FILES if ns.dataset == "all" else [ns.dataset]:
            qp, cp = hr.fetch(name)
            print(f"{name}: {qp} {cp} (verified)")
        return 0
    from triplum.bench.report import summary
    from triplum.bench.runner import run_benchmark, runstore_path
    from triplum.bench.runstore import RunStore
    from triplum.cache import default_root

    if ns.bench_cmd == "report":
        _print(summary(RunStore(ns.runstore or default_root() / "runs.db")))
        return 0
    if ns.bench_cmd in ("inspect", "diff", "tail"):
        return _tooling(ns)
    if ns.bench_cmd in ("show", "rerun"):
        rs = RunStore(ns.runstore or default_root() / "runs.db")
        row = rs.run(ns.run_id)
        if row is None:
            raise SystemExit(f"no run {ns.run_id}")
        if ns.bench_cmd == "show":
            identity = {k: row[k] for k in row if k not in ("config_json",)}
            print(json.dumps({"identity": identity, "config": json.loads(row["config_json"])}, indent=2))
            return 0
        cfg = RunConfig.from_json(row["config_json"])
        cfg = RunConfig(**{**cfg.__dict__, "force": ns.force, "resume": ns.resume, "runstore_path": str(rs.path)})
        rid = run_benchmark(cfg)
        print("reused" if rid == ns.run_id else "new", rid)
        _print(summary(rs, [rid]))
        return 0
    if ns.bench_cmd == "run":
        cfgs = [build_run_config(ns)]
    else:
        with open(ns.embedders) as f:
            cfgs = [build_run_config(ns, embedder=e) for e in json.load(f)]
    ids, failed = [], []
    for c in cfgs:
        try:
            ids.append(run_benchmark(c))
        except Exception as e:
            if ns.bench_cmd == "run":
                raise
            failed.append((c.pipeline.embedder.model if c.pipeline.embedder else "?", f"{type(e).__name__}: {e}"))
            print(f"FAILED {failed[-1][0]}: {failed[-1][1]}", file=sys.stderr)
    rs = RunStore(runstore_path(cfgs[0]))
    if ids:
        _print(summary(rs, ids))
    if failed:
        print(f"{len(failed)} spec(s) failed: " + ", ".join(m for m, _ in failed), file=sys.stderr)
    return 0 if ids and not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
