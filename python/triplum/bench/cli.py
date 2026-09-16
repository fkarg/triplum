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
    rerun.add_argument("--runstore", default=None)
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
        cache_root=ns.cache_root,
        runstore_path=ns.runstore,
    )


def _print(df) -> None:
    import polars as pl

    with pl.Config(tbl_cols=-1, tbl_width_chars=220, tbl_rows=100):
        print(df)


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
        cfg = RunConfig(**{**cfg.__dict__, "force": ns.force, "runstore_path": str(rs.path)})
        rid = run_benchmark(cfg)
        print("reused" if rid == ns.run_id else "new", rid)
        _print(summary(rs, [rid]))
        return 0
    if ns.bench_cmd == "run":
        cfgs = [build_run_config(ns)]
    else:
        with open(ns.embedders) as f:
            cfgs = [build_run_config(ns, embedder=e) for e in json.load(f)]
    ids = [run_benchmark(c) for c in cfgs]
    rs = RunStore(runstore_path(cfgs[0]))
    _print(summary(rs, ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
