"""Compose stages from a RunConfig, record everything, return the run id."""

from __future__ import annotations

import json
import platform
import subprocess
import time
from pathlib import Path

import polars as pl

from triplum.bench import factories, fingerprint
from triplum.bench.config import RunConfig
from triplum.bench.index import ensure_documents, ensure_embeddings
from triplum.bench.runstore import RunStore
from triplum.cache import default_root
from triplum.data.viewer import Viewer
from triplum.eval import judge as judge_mod
from triplum.eval import metrics
from triplum.eval.datasets import hipporag as hr
from triplum.generate import reader as reader_mod
from triplum.generate.reader import read
from triplum.retrieve import stages
from triplum.store.sqlite.store import SqliteStore


def code_version() -> tuple[str, int]:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        porcelain = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        ).stdout.strip()
        return sha, int(porcelain != "")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown", 1


def _retrieve(cfg: RunConfig, ds, store, embedder, reranker, viewer):
    p = cfg.pipeline
    if p.name == "closed_book":
        return stages.none(ds.questions)
    if p.name == "oracle":
        return stages.oracle(ds.questions, p.top_k)
    if p.name == "bm25":
        return stages.bm25(ds.questions, store, p.top_k, viewer)
    if p.name == "dense":
        return stages.dense(ds.questions, store, embedder, p.top_k, viewer)
    if p.name == "hybrid":
        return stages.hybrid(ds.questions, store, embedder, reranker, p.top_k, p.candidates, viewer)
    raise ValueError(f"unknown pipeline {p.name}")


def cache_root(cfg: RunConfig) -> Path:
    return Path(cfg.cache_root) if cfg.cache_root else default_root()


def runstore_path(cfg: RunConfig) -> Path:
    return Path(cfg.runstore_path) if cfg.runstore_path else cache_root(cfg) / "runs.db"


def run_benchmark(cfg: RunConfig) -> str:
    t_start = time.perf_counter()
    root = cache_root(cfg)
    ds = hr.load_fixture(cfg.dataset, cfg.n) if cfg.fixture else hr.load(cfg.dataset, cfg.n)
    p = cfg.pipeline
    needs_embed = p.name in ("dense", "hybrid")
    embedder = factories.make_embedder(p.embedder, root) if needs_embed and p.embedder else None
    real_models = cfg.judge is not None and cfg.judge.kind != "fake" and p.reader.kind != "fake"
    if real_models and factories.model_family(cfg.judge.model) == factories.model_family(
        p.reader.model
    ):
        raise ValueError(
            f"judge {cfg.judge.model} and reader {p.reader.model} are the same model family"
        )
    reranker = factories.make_reranker(p.reranker, root) if p.name == "hybrid" else None
    reader = factories.make_llm(p.reader, root)
    judge = factories.make_llm(cfg.judge, root) if cfg.judge else None
    viewer = Viewer(principals=frozenset(cfg.principals))
    sha, dirty = code_version()
    rs = RunStore(runstore_path(cfg))
    meta = {
        "dataset": ds.name,
        "pipeline": p.name,
        "config_hash": p.hash(),
        "config_json": cfg.to_json(),
        "code_version": sha,
        "dirty": dirty,
        "code_hash": fingerprint.code_hash(p.name),
        "corpus_hash": ds.corpus_hash,
        "questions_hash": ds.questions_hash,
        "n": ds.questions.height,
        "embedding_spec": embedder.spec.hash() if embedder else None,
        "reranker_spec": reranker.spec.hash() if reranker else None,
        "reader_model": p.reader.model,
        "judge_model": cfg.judge.model if cfg.judge else None,
        "seed": cfg.seed,
        "viewer_json": json.dumps(sorted(viewer.principals)),
        "host": platform.node(),
        "reader_prompt_hash": reader_mod.PROMPT_HASH,
        "judge_prompt_hash": judge_mod.PROMPT_HASH if cfg.judge else None,
    }
    identity = rs.identity_hash(meta)
    done: set[str] = set()
    run_id = None
    if not cfg.force:
        existing = rs.find_run(identity)
        if existing:
            return existing
        if cfg.resume:
            run_id = rs.find_run(identity, status="running") or rs.find_run(
                identity, status="failed"
            )
            if run_id:
                done = rs.completed_questions(run_id)
                rs.conn.execute("UPDATE runs SET status = 'running' WHERE run_id = ?", (run_id,))
    if run_id is None:
        run_id = rs.start_run(meta)
        rs.snapshot_prices(
            run_id,
            [
                model
                for model in (
                    p.reader.model,
                    cfg.judge.model if cfg.judge else None,
                    embedder.spec.model if embedder else None,
                )
                if model is not None
            ],
        )
    rec = rs.recorder(run_id)
    store_path = (
        Path(cfg.store_path)
        if cfg.store_path
        else root / "stores" / f"{ds.name}-{ds.corpus_hash[:8]}.sqlite"
    )
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store = SqliteStore(store_path)
    status = "failed"
    try:
        ensure_documents(store, ds, rec)
        if embedder is not None:
            ensure_embeddings(store, ds, embedder, rec)
        with rec.stage(
            "retrieve",
            model=reranker.spec.model if reranker else None,
            provider=reranker.spec.runtime if reranker else None,
        ) as ev:
            retrieved = _retrieve(cfg, ds, store, embedder, reranker, viewer)
            if reranker is not None:
                ev.usage(reranker.calls, 0, cached=reranker.calls == 0)
        todo = ds.questions.filter(~pl.col("id").is_in(list(done))) if done else ds.questions
        params = factories.gen_params(p.reader, cfg.seed)
        for q in todo.iter_rows(named=True):
            with rs.question_unit():
                one = todo.filter(pl.col("id") == q["id"])
                a = read(one, retrieved, store, reader, viewer, params).row(0, named=True)
                with rec.stage(
                    "read", question_id=q["id"], provider=p.reader.kind, model=p.reader.model
                ) as ev:
                    ev.usage(a["input_tokens"], a["output_tokens"], cached=a["cached"])
                ids = (
                    retrieved.filter(pl.col("question_id") == q["id"])
                    .sort("rank")["chunk_id"]
                    .to_list()
                )
                jud = None
                if judge is not None:
                    assert cfg.judge is not None  # The adapter is built from this config above.
                    with rec.stage(
                        "judge", question_id=q["id"], provider=cfg.judge.kind, model=cfg.judge.model
                    ) as ev:
                        ok, jc = judge_mod.judge_correct(
                            judge,
                            q["question"],
                            q["aliases"],
                            a["answer"],
                            factories.gen_params(cfg.judge, cfg.seed),
                        )
                        ev.usage(
                            jc.usage.input_tokens,
                            jc.usage.output_tokens,
                            jc.usage.cached_input_tokens,
                            jc.cached,
                        )
                        jud = float(ok)
                rs.add_question(
                    run_id,
                    {
                        "question_id": q["id"],
                        "retrieved_json": json.dumps(ids),
                        "answer": a["answer"],
                        "em": metrics.exact_match(a["answer"], q["aliases"]),
                        "f1": metrics.f1(a["answer"], q["aliases"]),
                        "contain": metrics.contain(a["answer"], q["aliases"]),
                        "judge": jud,
                        "r2": metrics.recall_at_k(q["gold_chunk_ids"], ids, 2),
                        "r5": metrics.recall_at_k(q["gold_chunk_ids"], ids, 5),
                        "input_tokens": a["input_tokens"],
                        "output_tokens": a["output_tokens"],
                        "usd": rec.cost(p.reader.model, a["input_tokens"], a["output_tokens"], 0),
                        "cached": int(a["cached"]),
                        "latency_s": a["latency_s"],
                        "n_passages": a["n_passages"],
                    },
                )
        rs.add_artifact(run_id, "store", str(store_path), hr.sha256_file(store_path))
        status = "ok"
    finally:
        store.close()
        rs.finish_run(
            run_id,
            status=status,
            wall_s=time.perf_counter() - t_start,
            cache_hits=rec.cache_hits,
            cache_misses=rec.cache_misses,
        )
    return run_id
