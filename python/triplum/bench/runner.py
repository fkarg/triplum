"""Compose stages from a RunConfig or an ExtractConfig, record everything, return the run id."""

from __future__ import annotations

import json
import platform
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import polars as pl

from triplum.bench import factories, fingerprint
from triplum.bench.config import ExtractConfig, RunConfig
from triplum.bench.index import ensure_documents, ensure_embeddings, ensure_graph, graph_identity
from triplum.bench.runstore import RunStore
from triplum.cache import default_root
from triplum.data.schema import now_us
from triplum.data.viewer import Viewer
from triplum.embed.protocol import Embedder
from triplum.eval import judge as judge_mod
from triplum.eval import metrics, triples
from triplum.eval.datasets import base
from triplum.eval.datasets import registry as datasets
from triplum.eval.datasets.base import Dataset
from triplum.extract import stages as extract_stages
from triplum.generate import reader as reader_mod
from triplum.generate.reader import read
from triplum.rerank.protocol import Reranker
from triplum.retrieve import pipelines, stages
from triplum.store.protocol import Store
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


def _retrieve(
    cfg: RunConfig,
    ds: Dataset,
    store: Store,
    embedder: Embedder | None,
    reranker: Reranker | None,
    viewer: Viewer,
) -> pl.DataFrame:
    """Run the pipeline's retrieval stage; the result has exactly `stages.SCHEMA`."""
    p = cfg.pipeline
    pipe = pipelines.get(p.name)
    if pipe.needs_embedder and embedder is None:
        raise ValueError(f"pipeline {p.name} needs an embedder")
    if pipe.needs_reranker and reranker is None:
        raise ValueError(f"pipeline {p.name} needs a reranker")
    out = pipe.run(
        ds.questions,
        store,
        viewer,
        k=p.top_k,
        candidates=p.candidates,
        embedder=embedder,
        reranker=reranker,
    )
    if dict(out.schema) != stages.SCHEMA:
        raise TypeError(f"retrieval stage {p.name} returned {out.schema}, expected {stages.SCHEMA}")
    return out


def cache_root(cfg: RunConfig | ExtractConfig) -> Path:
    return Path(cfg.cache_root) if cfg.cache_root else default_root()


def runstore_path(cfg: RunConfig | ExtractConfig) -> Path:
    return Path(cfg.runstore_path) if cfg.runstore_path else cache_root(cfg) / "runs.db"


def store_path(cfg: RunConfig | ExtractConfig, ds: Dataset) -> Path:
    """One SQLite file per corpus, shared by QA and extraction runs over the same dataset."""
    path = (
        Path(cfg.store_path)
        if cfg.store_path
        else cache_root(cfg) / "stores" / f"{ds.name}-{ds.corpus_hash[:8]}.sqlite"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load(cfg: RunConfig | ExtractConfig) -> Dataset:
    return (
        datasets.load_fixture(cfg.dataset, cfg.n)
        if cfg.fixture
        else datasets.load(cfg.dataset, cfg.n)
    )


def run_benchmark(cfg: RunConfig) -> str:
    t_start = time.perf_counter()
    root = cache_root(cfg)
    spec = datasets.get(cfg.dataset)
    ds = _load(cfg)
    p = cfg.pipeline
    if ds.questions.height == 0:
        raise ValueError(
            f"dataset {spec.name} has no questions (extraction-only); it cannot be run"
        )
    if spec.needs:
        raise ValueError(f"dataset {spec.name} cannot be run yet: it needs {spec.needs}")
    if ds.chunks.height == 0 and p.name != "closed_book":
        raise ValueError(
            f"dataset {spec.name} ships no corpus; only the closed_book pipeline applies"
        )
    pipe = pipelines.get(p.name)
    needs_embed = pipe.needs_embedder
    embedder = factories.make_embedder(p.embedder, root) if needs_embed and p.embedder else None
    real_models = cfg.judge is not None and cfg.judge.kind != "fake" and p.reader.kind != "fake"
    if real_models and factories.model_family(cfg.judge.model) == factories.model_family(
        p.reader.model
    ):
        raise ValueError(
            f"judge {cfg.judge.model} and reader {p.reader.model} are the same model family"
        )
    reranker = factories.make_reranker(p.reranker, root) if pipe.needs_reranker else None
    reader = factories.make_llm(p.reader, root)
    judge = factories.make_llm(cfg.judge, root) if cfg.judge else None
    viewer = Viewer(principals=frozenset(cfg.principals))
    sha, dirty = code_version()
    with RunStore(runstore_path(cfg)) as rs:
        meta = {
            "kind": "qa",
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
                    rs.resume_run(run_id)
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
        path = store_path(cfg, ds)
        store = SqliteStore(path)
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
                            "judge",
                            question_id=q["id"],
                            provider=cfg.judge.kind,
                            model=cfg.judge.model,
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
                            "r2": metrics.recall_at_k(q["gold_chunk_ids"], ids, 2)
                            if q["gold_chunk_ids"]
                            else None,
                            "r5": metrics.recall_at_k(q["gold_chunk_ids"], ids, 5)
                            if q["gold_chunk_ids"]
                            else None,
                            "input_tokens": a["input_tokens"],
                            "output_tokens": a["output_tokens"],
                            "usd": rec.cost(
                                p.reader.model, a["input_tokens"], a["output_tokens"], 0
                            ),
                            "cached": int(a["cached"]),
                            "latency_s": a["latency_s"],
                            "n_chunks": a["n_chunks"],
                        },
                    )
            rs.add_artifact(run_id, "store", str(path), base.sha256_file(path))
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


def _with_vocabulary(cfg: ExtractConfig, ds: Dataset) -> ExtractConfig:
    """`small_model` classifies over closed vocabularies. When the config leaves them empty,
    take the entity types the dataset lists in its document metadata and the predicates of its
    gold triples, and record them in the config so the run identity names them."""
    x = cfg.extractor
    if x.kind != "small_model" or (x.entity_types and x.relation_types):
        return cfg
    types = x.entity_types or tuple(
        sorted(
            {
                e["type"]
                for m in ds.documents["metadata"].to_list()
                if m
                for e in json.loads(m).get("entities", [])
                if isinstance(e, dict) and "type" in e
            }
        )
    )
    relations = x.relation_types or tuple(sorted(set(ds.triples["predicate"].to_list())))
    if not types or not relations:
        raise ValueError(
            f"dataset {ds.name} gives no entity types or relation vocabulary; pass"
            " --entity-types and --relation-types for small_model"
        )
    return replace(cfg, extractor=replace(x, entity_types=types, relation_types=relations))


def run_extraction(cfg: ExtractConfig) -> str:
    """Build the graph for a dataset with one extractor and resolver, write it to the store
    once per graph identity, score it against the gold triples, and record the run. An
    identical configuration returns the stored run; `--force` recomputes."""
    t_start = time.perf_counter()
    root = cache_root(cfg)
    ds = _load(cfg)
    if ds.chunks.height == 0:
        raise ValueError(f"dataset {ds.name} ships no corpus; nothing to extract from")
    cfg = _with_vocabulary(cfg, ds)
    extractor = factories.make_extractor(cfg.extractor, root)
    identity = graph_identity(ds, extractor.spec, cfg.resolver, fingerprint.code_hash("graph"))
    viewer = Viewer(principals=frozenset(cfg.principals))
    sha, dirty = code_version()
    with RunStore(runstore_path(cfg)) as rs:
        meta = {
            "kind": "extract",
            "dataset": ds.name,
            "pipeline": None,
            "config_hash": cfg.hash(),
            "config_json": cfg.to_json(),
            "code_version": sha,
            "dirty": dirty,
            "code_hash": fingerprint.code_hash("extract"),
            "corpus_hash": ds.corpus_hash,
            "questions_hash": ds.questions_hash,
            "n": ds.chunks.height,
            "embedding_spec": None,
            "reranker_spec": None,
            "reader_model": None,
            "judge_model": None,
            "seed": 0,
            "viewer_json": json.dumps(sorted(viewer.principals)),
            "host": platform.node(),
            "reader_prompt_hash": None,
            "judge_prompt_hash": None,
            "extractor_spec": extractor.spec.hash(),
            "resolver_spec": cfg.resolver.hash(),
            "graph_identity": identity,
        }
        if not cfg.force:
            existing = rs.find_run(rs.identity_hash(meta))
            if existing:
                return existing
        run_id = rs.start_run(meta)
        rec = rs.recorder(run_id)
        path = store_path(cfg, ds)
        store = SqliteStore(path)
        status = "failed"
        try:
            ensure_documents(store, ds, rec)
            recorded_at = now_us()
            with rec.stage("extract", model=extractor.spec.model or extractor.spec.name) as ev:
                t0 = time.perf_counter()
                graph = extract_stages.extract(ds.chunks, ds.documents, extractor, recorded_at)
                extract_s = time.perf_counter() - t0
                ev.usage(0, 0, cached=extractor.misses == 0)
            with rec.stage("resolve", model=cfg.resolver.name):
                graph = extract_stages.resolve(graph, ds.chunks, cfg.resolver, recorded_at)
            written = ensure_graph(store, identity, graph, rec)
            with rec.stage("score"):
                pred = triples.predicted(graph, ds.chunks)
                scores = triples.score(pred, ds.triples, ds.chunks, ds.questions)
                gold_spans = triples.gold_spans(ds.documents)
                span = (
                    triples.span_score(triples.predicted_spans(graph, ds.chunks), gold_spans)
                    if gold_spans
                    else (None, None, None)
                )
            rs.add_extraction(
                run_id,
                {
                    **graph.counts(),
                    **scores,
                    "span_precision": span[0],
                    "span_recall": span[1],
                    "span_f1": span[2],
                    # a throughput measured on cache hits is the cache's, not the extractor's
                    "chunks_per_s": None if extractor.misses == 0 else ds.chunks.height / extract_s,
                    "graph_written": int(written),
                },
            )
            rs.add_artifact(run_id, "store", str(path), base.sha256_file(path))
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
