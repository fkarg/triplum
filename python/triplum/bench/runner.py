"""Compose the stages from a RunConfig or an ExtractConfig under a `Run`, record everything,
return the run ids. Identity is computed from the sources' fingerprints and the config before
anything is read; a stored run with that identity is returned when the manifests of every
stage it ran still validate, else the pipeline runs and each stage fetches or recomputes."""

from __future__ import annotations

import json
import platform
import subprocess
import time
from pathlib import Path

from triplum.bench import factories
from triplum.bench import stages as st
from triplum.bench.config import ExtractConfig, RunConfig
from triplum.bench.inputs import Benchmark, identities
from triplum.bench.runstore import IDENTITY_FIELDS, RunStore
from triplum.cache import content_key, default_root
from triplum.data.viewer import Viewer
from triplum.datasets import collate
from triplum.datasets import registry as datasets
from triplum.eval import judge as judge_mod
from triplum.eval import triples
from triplum.generate import reader as reader_mod
from triplum.retrieve import pipelines
from triplum.stage import Run, active, derive
from triplum.stage.fingerprint import validate
from triplum.store.sqlite.store import SqliteStore
from triplum.utils.data import Dataset, Take


def code_version() -> tuple[str, int]:
    """The checkout's git SHA and dirty flag, for provenance only: neither identifies a run.
    Outside a git checkout, ``("unknown", 1)``."""
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


def cache_root(cfg: RunConfig | ExtractConfig) -> Path:
    return Path(cfg.cache_root) if cfg.cache_root else default_root()


def runstore_path(cfg: RunConfig | ExtractConfig) -> Path:
    return Path(cfg.runstore_path) if cfg.runstore_path else cache_root(cfg) / "runs.db"


def store_path(cfg: RunConfig | ExtractConfig, name: str, corpus_hash: str) -> Path:
    """One SQLite file per corpus, shared by QA and extraction runs over the same dataset."""
    path = (
        Path(cfg.store_path)
        if cfg.store_path
        else cache_root(cfg) / "stores" / f"{name}-{corpus_hash[:8]}.sqlite"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _benchmark(cfg: RunConfig | ExtractConfig, data: Benchmark | None) -> Benchmark:
    """The composition to run; `n` selects questions and never truncates a corpus."""
    if data is not None:
        return data
    return (
        datasets.load_fixture(cfg.dataset, cfg.n)
        if cfg.fixture
        else datasets.load(cfg.dataset, cfg.n)
    )


def _count(source) -> int:
    """How many records a source has, when that is known without reading it; else 0, and the
    run's `n` is set once the questions stage has run."""
    if isinstance(source, Dataset) or (
        isinstance(source, Take) and isinstance(source.source, Dataset)
    ):
        return len(source)
    return 0


def run_valid(rs: RunStore, run_id: str) -> bool:
    """Whether every stage the run executed would run the same code now: each invocation's
    manifest still validates. A run without invocations predates stages and never matches."""
    inv = rs.invocations(run_id)
    if inv.height == 0:
        return False
    for code in inv["code"].to_list():
        if code is None:
            return False
        manifest = rs.manifest(code)
        if manifest is None or not validate(manifest):
            return False
    return True


def _find(rs: RunStore, identity: str) -> str | None:
    for run_id in rs.find_runs(identity):
        if run_valid(rs, run_id):
            return run_id
    return None


def _code_hash(rs: RunStore, run_id: str) -> str:
    codes = sorted({c for c in rs.invocations(run_id)["code"].to_list() if c})
    return content_key("code", codes)[:16]


def experiment_id(meta: dict) -> str:
    return content_key("experiment", {k: meta.get(k) for k in IDENTITY_FIELDS if k != "replicate"})[
        :16
    ]


# ---- question answering ---------------------------------------------------------------------


def run_benchmark(cfg: RunConfig, *, data: Benchmark | None = None) -> str:
    """Run a configured question-answering benchmark and return its run id: the first replicate
    of `run_experiment`."""
    return run_experiment(cfg, data=data)[0]


def run_experiment(cfg: RunConfig, *, data: Benchmark | None = None) -> list[str]:
    """Run `cfg.replicates` replicates of the configuration, each under the seed derived from
    the root seed and its index, and return their run ids, replicate 0 first. A stored run with
    the same identity whose stage manifests still validate is returned instead of rerunning,
    unless ``cfg.force``; with ``cfg.resume`` an interrupted run of that identity is continued.
    Every replicate is a run in the run store, grouped by an experiment id."""
    benchmark = _benchmark(cfg, data)
    p = cfg.pipeline
    if benchmark.qa is None:
        raise ValueError(
            f"dataset {benchmark.name} has no questions (extraction-only); it cannot be run"
        )
    if benchmark.needs:
        raise ValueError(f"dataset {benchmark.name} cannot be run yet: it needs {benchmark.needs}")
    if benchmark.corpus is None and p.name != "closed_book":
        raise ValueError(
            f"dataset {benchmark.name} ships no corpus; only the closed_book pipeline applies"
        )
    pipe = pipelines.get(p.name)
    root = cache_root(cfg)
    embedder = (
        factories.make_embedder(p.embedder, root) if pipe.needs_embedder and p.embedder else None
    )
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
    corpus_hash, evaluation_hash = identities(benchmark)
    sha, dirty = code_version()
    meta = {
        "kind": "qa",
        "dataset": benchmark.name,
        "pipeline": p.name,
        "config_hash": p.hash(),
        "config_json": cfg.to_json(),
        "code_version": sha,
        "dirty": dirty,
        "code_hash": "",
        "corpus_hash": corpus_hash,
        "questions_hash": evaluation_hash,
        "n": _count(benchmark.qa),
        "embedding_spec": embedder.spec.hash() if embedder else None,
        "reranker_spec": reranker.spec.hash() if reranker else None,
        "reader_model": p.reader.model,
        "judge_model": cfg.judge.model if cfg.judge else None,
        "judge_hash": cfg.judge.hash() if cfg.judge else None,
        "seed": cfg.seed,
        "replicate": 0,
        "viewer_json": json.dumps(sorted(viewer.principals)),
        "host": platform.node(),
        "reader_prompt_hash": reader_mod.PROMPT_HASH,
        "judge_prompt_hash": judge_mod.PROMPT_HASH if cfg.judge else None,
    }
    meta["experiment_id"] = experiment_id(meta)
    ids = []
    with RunStore(runstore_path(cfg)) as rs:
        for r in range(cfg.replicates):
            meta_r = {**meta, "replicate": r}
            identity = rs.identity_hash(meta_r)
            run_id = None if cfg.force else _find(rs, identity)
            if run_id is not None:
                ids.append(run_id)
                continue
            if cfg.resume and not cfg.force:
                run_id = rs.find_run(identity, status="running") or rs.find_run(
                    identity, status="failed"
                )
                if run_id:
                    rs.resume_run(run_id)
            if run_id is None:
                run_id = rs.start_run(meta_r)
                rs.snapshot_prices(
                    run_id,
                    [
                        m
                        for m in (
                            p.reader.model,
                            cfg.judge.model if cfg.judge else None,
                            embedder.spec.model if embedder else None,
                        )
                        if m is not None
                    ],
                )
            path = store_path(cfg, benchmark.name, corpus_hash)
            store = SqliteStore(path)
            status = "failed"
            t_start = time.perf_counter()
            try:
                with active(
                    Run(store=rs, root=root, run_id=run_id, seed=derive(cfg.seed, r), replicate=r)
                ):
                    corpus = (
                        st.corpus_frames(benchmark.corpus)
                        if benchmark.corpus is not None
                        else st.empty_corpus()
                    )
                    if corpus["chunks"].height == 0 and p.name != "closed_book":
                        raise ValueError(
                            f"dataset {benchmark.name} ships no corpus; only the closed_book pipeline applies"
                        )
                    qa = st.questions(benchmark.qa, corpus)
                    rs.update_run(run_id, n=qa.height)
                    rec = rs.recorder(run_id)
                    with rec.stage("index.documents"):
                        st.ingest(store, corpus, benchmark.name, corpus_hash)
                    if embedder is not None:
                        with rec.stage(
                            "index.embed", model=embedder.spec.model, provider=embedder.spec.runtime
                        ):
                            st.embed(store, corpus, embedder)
                    with rec.stage(
                        "retrieve",
                        model=reranker.spec.model if reranker else None,
                        provider=reranker.spec.runtime if reranker else None,
                    ) as ev:
                        hits = st.retrieve(qa, store, p, embedder, reranker, viewer)
                        if reranker is not None:
                            ev.usage(reranker.calls, 0, cached=reranker.calls == 0)
                    rows = st.answer(qa, hits, store, reader, p.reader, judge, cfg.judge, viewer)
                # a fetched answer stage called nothing: its rows cost nothing and took no time
                for row in rows.iter_rows(named=True):
                    rs.add_question(run_id, {**row, "usd": None, "cached": 1, "latency_s": 0.0})
                rs.add_artifact(run_id, "store", str(path), store.identity())
                status = "ok"
            finally:
                store.close()
                hits_n, misses_n = rs.cache_totals(run_id)
                rs.finish_run(
                    run_id,
                    status=status,
                    wall_s=time.perf_counter() - t_start,
                    cache_hits=hits_n,
                    cache_misses=misses_n,
                    code_hash=_code_hash(rs, run_id),
                )
            ids.append(run_id)
    return ids


# ---- extraction -----------------------------------------------------------------------------


def _with_vocabulary(cfg: ExtractConfig, corpus: dict, gold) -> ExtractConfig:
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
                for m in corpus["documents"]["metadata"].to_list()
                if m
                for e in json.loads(m).get("entities", [])
                if isinstance(e, dict) and "type" in e
            }
        )
    )
    relations = x.relation_types or (
        tuple(sorted(set(gold["predicate"].to_list()))) if gold is not None else ()
    )
    if not types or not relations:
        raise ValueError(
            f"dataset {cfg.dataset} gives no entity types or relation vocabulary; pass"
            " --entity-types and --relation-types for small_model"
        )
    extractor = x.model_copy(update={"entity_types": types, "relation_types": relations})
    return cfg.model_copy(update={"extractor": extractor})


def run_extraction(cfg: ExtractConfig, *, data: Benchmark | None = None) -> str:
    """Build the graph for a dataset with one extractor and resolver, write it to the store
    once per graph identity, score it against the gold triples, and record the run. An
    identical configuration whose stage manifests still validate returns the stored run;
    `--force` records a new run (its stages fetch what they can)."""
    t_start = time.perf_counter()
    benchmark = _benchmark(cfg, data)
    if benchmark.corpus is None:
        raise ValueError(f"dataset {benchmark.name} ships no corpus; nothing to extract from")
    root = cache_root(cfg)
    corpus_hash, evaluation_hash = identities(benchmark)
    viewer = Viewer(principals=frozenset(cfg.principals))
    sha, dirty = code_version()
    if _needs_vocabulary(cfg):
        # The vocabulary comes from the corpus and the gold, so the identity of this run is not
        # known until they are read; this one read is bare (no run to record it under).
        corpus0 = st.corpus_frames.fn(benchmark.corpus)
        qa0 = st.questions.fn(benchmark.qa, corpus0) if benchmark.qa is not None else None
        gold0 = (
            st.gold_triples.fn(benchmark.extraction, qa0)
            if benchmark.extraction is not None
            else None
        )
        cfg = _with_vocabulary(cfg, corpus0, gold0)
    extractor = factories.make_extractor(cfg.extractor, root)
    with RunStore(runstore_path(cfg)) as rs:
        meta = {
            "kind": "extract",
            "dataset": benchmark.name,
            "pipeline": None,
            "config_hash": cfg.hash(),
            "config_json": cfg.to_json(),
            "code_version": sha,
            "dirty": dirty,
            "code_hash": "",
            "corpus_hash": corpus_hash,
            "questions_hash": evaluation_hash,
            "n": 0,
            "embedding_spec": None,
            "reranker_spec": None,
            "reader_model": None,
            "judge_model": None,
            "judge_hash": None,
            "seed": 0,
            "replicate": 0,
            "viewer_json": json.dumps(sorted(viewer.principals)),
            "host": platform.node(),
            "reader_prompt_hash": None,
            "judge_prompt_hash": None,
            "extractor_spec": extractor.spec.hash(),
            "resolver_spec": cfg.resolver.hash(),
            "graph_identity": None,
        }
        meta["experiment_id"] = experiment_id(meta)
        if not cfg.force:
            existing = _find(rs, rs.identity_hash(meta))
            if existing:
                return existing
        run_id = rs.start_run(meta)
        path = store_path(cfg, benchmark.name, corpus_hash)
        store = SqliteStore(path)
        status = "failed"
        try:
            with active(Run(store=rs, root=root, run_id=run_id, seed=0, replicate=0)):
                corpus = st.corpus_frames(benchmark.corpus)
                if corpus["chunks"].height == 0:
                    raise ValueError(
                        f"dataset {benchmark.name} ships no corpus; nothing to extract from"
                    )
                rs.update_run(run_id, n=corpus["chunks"].height)
                qa = st.questions(benchmark.qa, corpus) if benchmark.qa is not None else None
                gold = (
                    st.gold_triples(benchmark.extraction, qa)
                    if benchmark.extraction is not None
                    else None
                )
                rec = rs.recorder(run_id)
                with rec.stage("index.documents"):
                    st.ingest(store, corpus, benchmark.name, corpus_hash)
                with rec.stage("extract", model=extractor.spec.model or extractor.spec.name) as ev:
                    misses_before = extractor.misses
                    raw, extract_s = st.timed(st.claims, corpus["chunks"], extractor)
                    ev.usage(0, 0, cached=extractor.misses == misses_before)
                grounded = st.ground(raw, corpus, extractor.spec.hash())
                resolved = st.resolve(grounded, corpus, cfg.resolver)
                extraction = st.extraction_of(resolved)
                identity = extraction.hash()
                rs.update_run(run_id, graph_identity=identity)
                before = store.get_meta("graph_identity")
                with rec.stage("index.graph"):
                    st.graph(store, resolved)
                written = before != identity
                with rec.stage("score"):
                    chunks = corpus["chunks"]
                    pred = triples.predicted(extraction, chunks)
                    scores = triples.score(
                        pred,
                        gold if gold is not None else collate.triples_frame([]),
                        chunks,
                        qa if qa is not None else collate.questions_frame([]),
                    )
                    gold_spans = triples.gold_spans(corpus["documents"])
                    span = (
                        triples.span_score(triples.predicted_spans(extraction, chunks), gold_spans)
                        if gold_spans
                        else (None, None, None)
                    )
            rs.add_extraction(
                run_id,
                {
                    **extraction.counts(),
                    **scores,
                    "span_precision": span[0],
                    "span_recall": span[1],
                    "span_f1": span[2],
                    # a throughput measured on cache hits is the cache's, not the extractor's
                    "chunks_per_s": None
                    if extractor.misses == misses_before
                    else chunks.height / extract_s,
                    "graph_written": int(written),
                },
            )
            rs.add_artifact(run_id, "store", str(path), store.identity())
            status = "ok"
        finally:
            store.close()
            hits_n, misses_n = rs.cache_totals(run_id)
            rs.finish_run(
                run_id,
                status=status,
                wall_s=time.perf_counter() - t_start,
                cache_hits=hits_n,
                cache_misses=misses_n,
                code_hash=_code_hash(rs, run_id),
            )
        return run_id


def _needs_vocabulary(cfg: ExtractConfig) -> bool:
    x = cfg.extractor
    return x.kind == "small_model" and not (x.entity_types and x.relation_types)
