"""The benchmark pipeline as stages: each takes what it uses as arguments, reads no module
global but constants, and returns a frame, a dict of frames or nothing (a store effect). The
runner composes them under a `Run`; a notebook calls them bare."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext

import polars as pl

from triplum.bench import factories
from triplum.bench.config import LLMConfig, PipelineConfig
from triplum.bench.inputs import check
from triplum.data.corpus import CHUNK_SCHEMA, DOC_SCHEMA, GRANT_SCHEMA, CorpusBatch, Document
from triplum.data.schema import now_us
from triplum.data.viewer import Viewer
from triplum.datasets import collate
from triplum.embed.protocol import Embedder
from triplum.eval import judge as judge_mod
from triplum.eval import metrics
from triplum.eval.inputs import QUESTION_SCHEMA, TRIPLE_SCHEMA, Question, Triple
from triplum.extract import stages as extract_stages
from triplum.extract.protocol import Extraction, Extractor, ResolverSpec
from triplum.generate.reader import read
from triplum.llm.protocol import LLM
from triplum.rerank.protocol import Reranker
from triplum.retrieve import pipelines
from triplum.retrieve import stages as retrieve_stages
from triplum.stage import current, stage, stage_seed
from triplum.store.sqlite.store import SqliteStore
from triplum.utils.data import DataLoader, Source

BATCH = 1024
ANSWER_SCHEMA = {
    "question_id": pl.Utf8,
    "retrieved_json": pl.Utf8,
    "answer": pl.Utf8,
    "em": pl.Float64,
    "f1": pl.Float64,
    "contain": pl.Float64,
    "judge": pl.Float64,
    "r2": pl.Float64,
    "r5": pl.Float64,
    "input_tokens": pl.Int64,
    "output_tokens": pl.Int64,
    "n_chunks": pl.Int64,
}
TIMING = ("usd", "cached", "latency_s")  # per-question row columns that are not content
GRAPH_FRAMES = ("entities", "facts", "fact_support", "mentions", "claims")


class CorpusMismatch(RuntimeError):
    pass


class GraphMismatch(RuntimeError):
    pass


def _concat(frames: list[pl.DataFrame], schema) -> pl.DataFrame:
    return pl.concat(frames) if frames else pl.DataFrame(schema=schema)


def batch(corpus: dict[str, pl.DataFrame]) -> CorpusBatch:
    return CorpusBatch(corpus["documents"], corpus["grants"], corpus["chunks"])


def graph_frames(extraction: Extraction) -> dict[str, pl.DataFrame]:
    return {name: getattr(extraction, name) for name in GRAPH_FRAMES}


def extraction_of(frames: dict[str, pl.DataFrame]) -> Extraction:
    return Extraction(*(frames[name] for name in GRAPH_FRAMES))


# ---- sources to frames ----------------------------------------------------------------------


def empty_corpus() -> dict[str, pl.DataFrame]:
    return {
        "documents": pl.DataFrame(schema=DOC_SCHEMA),
        "grants": pl.DataFrame(schema=GRANT_SCHEMA),
        "chunks": pl.DataFrame(schema=CHUNK_SCHEMA),
    }


@stage
def corpus_frames(corpus: Source[Document]) -> dict[str, pl.DataFrame]:
    """The whole corpus in the canonical frames, read once per corpus identity (R7)."""
    batches = list(DataLoader(corpus, batch_size=BATCH, collate_fn=collate.corpus_batch))
    return {
        "documents": _concat([b.documents for b in batches], DOC_SCHEMA),
        "grants": _concat([b.grants for b in batches], GRANT_SCHEMA),
        "chunks": _concat([b.chunks for b in batches], CHUNK_SCHEMA),
    }


@stage
def questions(qa: Source[Question], corpus: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """The questions frame, checked against the corpus: unique document ids, every gold chunk
    present."""
    frame = _concat(
        list(DataLoader(qa, batch_size=BATCH, collate_fn=collate.questions_frame)),
        QUESTION_SCHEMA,
    )
    check(batch(corpus), frame)
    return frame


@stage
def gold_triples(extraction: Source[Triple], questions: pl.DataFrame | None) -> pl.DataFrame:
    """The gold triples; question-linked ones restricted to the questions present."""
    frame = _concat(
        list(DataLoader(extraction, batch_size=BATCH, collate_fn=collate.triples_frame)),
        TRIPLE_SCHEMA,
    )
    if questions is not None:
        frame = frame.filter(
            pl.col("question_id").is_null() | pl.col("question_id").is_in(questions["id"].implode())
        )
    return frame


# ---- store effects --------------------------------------------------------------------------


@stage
def ingest(
    store: SqliteStore, corpus: dict[str, pl.DataFrame], name: str, corpus_hash: str
) -> None:
    """Bind a store file to exactly one corpus and write it; another corpus is a refusal."""
    bound = store.get_meta("corpus_hash")
    if bound == corpus_hash:
        return
    if bound is not None:
        raise CorpusMismatch(
            f"store {store.path} holds corpus {bound[:12]}, dataset is {corpus_hash[:12]}"
        )
    store.put_documents(corpus["documents"], corpus["grants"])
    store.put_chunks(corpus["chunks"])
    store.set_meta("corpus_hash", corpus_hash)
    store.set_meta("dataset", name)


@stage
def embed(store: SqliteStore, corpus: dict[str, pl.DataFrame], embedder: Embedder) -> None:
    """Every chunk embedded under the embedder's spec, batch by batch, skipping what exists."""
    chunks = corpus["chunks"]
    ids = chunks["id"].to_list()
    texts = chunks["text"].to_list()
    have = store.has_embeddings(embedder.spec, ids)
    todo = [i for i, h in enumerate(have) if not h]
    for start in range(0, len(todo), 256):
        idx = todo[start : start + 256]
        vecs = embedder.embed_passages([texts[i] for i in idx])
        store.put_embeddings(embedder.spec, [ids[i] for i in idx], vecs)


@stage
def graph(store: SqliteStore, graph: dict[str, pl.DataFrame]) -> None:
    """Write the graph once per identity (the content hash of its frames). A store holding a
    graph of another identity is a refusal, never a silent mix."""
    extraction = extraction_of(graph)
    identity = extraction.hash()
    bound = store.get_meta("graph_identity")
    if bound == identity:
        return
    if bound is not None:
        raise GraphMismatch(
            f"store {store.path} holds graph {bound}, this run needs {identity}; delete the"
            " store file or pass --store to build the new graph elsewhere"
        )
    store.put_graph(
        extraction.entities, extraction.facts, extraction.fact_support, extraction.mentions
    )
    store.set_meta("graph_identity", identity)


# ---- question answering ---------------------------------------------------------------------


@stage
def retrieve(
    questions: pl.DataFrame,
    store: SqliteStore,
    pipeline: PipelineConfig,
    embedder: Embedder | None,
    reranker: Reranker | None,
    viewer: Viewer,
) -> pl.DataFrame:
    """The pipeline's retrieval stage over every question; exactly `retrieve_stages.SCHEMA`."""
    pipe = pipelines.get(pipeline.name)
    if pipe.needs_embedder and embedder is None:
        raise ValueError(f"pipeline {pipeline.name} needs an embedder")
    if pipe.needs_reranker and reranker is None:
        raise ValueError(f"pipeline {pipeline.name} needs a reranker")
    out = pipe.run(
        questions,
        store,
        viewer,
        k=pipeline.top_k,
        candidates=pipeline.candidates,
        embedder=embedder,
        reranker=reranker,
    )
    if dict(out.schema) != retrieve_stages.SCHEMA:
        raise TypeError(
            f"retrieval stage {pipeline.name} returned {out.schema}, expected {retrieve_stages.SCHEMA}"
        )
    return out


@contextmanager
def _unit() -> Iterator[None]:
    run = current()
    with run.store.question_unit() if run is not None else nullcontext():
        yield


@stage
def answer(
    questions: pl.DataFrame,
    hits: pl.DataFrame,
    store: SqliteStore,
    reader: LLM,
    reader_cfg: LLMConfig,
    judge: LLM | None,
    judge_cfg: LLMConfig | None,
    viewer: Viewer,
) -> pl.DataFrame:
    """Read and judge every question, scoring as it goes. Seeded through the reader and judge
    adapters: the derived seed reaches their requests and their cache keys. Under a run, each
    finished question's row and events commit together, so a crash leaves what was done and
    `--resume` picks up from the call cache. The returned frame is content only; latency, cost
    and cache state go to the run's rows and not into the artifact."""
    run = current()
    rec = run.store.recorder(run.run_id) if run is not None else None
    seed = stage_seed()
    params = factories.gen_params(reader_cfg, seed)
    jparams = factories.gen_params(judge_cfg, seed) if judge_cfg is not None else None
    rows = []
    for q in questions.iter_rows(named=True):
        with _unit():
            one = questions.filter(pl.col("id") == q["id"])
            a = read(one, hits, store, reader, viewer, params).row(0, named=True)
            if rec is not None:
                with rec.stage(
                    "read", question_id=q["id"], provider=reader.adapter, model=reader.model
                ) as ev:
                    ev.usage(a["input_tokens"], a["output_tokens"], cached=a["cached"])
            ids = hits.filter(pl.col("question_id") == q["id"]).sort("rank")["chunk_id"].to_list()
            jud = None
            if judge is not None and jparams is not None:
                if rec is not None:
                    cm = rec.stage(
                        "judge", question_id=q["id"], provider=judge.adapter, model=judge.model
                    )
                else:
                    cm = nullcontext()
                with cm as ev:
                    ok, jc = judge_mod.judge_correct(
                        judge, q["question"], q["aliases"], a["answer"], jparams
                    )
                    if ev is not None:
                        ev.usage(
                            jc.usage.input_tokens,
                            jc.usage.output_tokens,
                            jc.usage.cached_input_tokens,
                            jc.cached,
                        )
                    jud = float(ok)
            row = {
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
                "usd": rec.cost(reader.model, a["input_tokens"], a["output_tokens"], 0)
                if rec is not None
                else None,
                "cached": int(a["cached"]),
                "latency_s": a["latency_s"],
                "n_chunks": a["n_chunks"],
            }
            if run is not None:
                run.store.add_question(run.run_id, row)
            rows.append({k: v for k, v in row.items() if k not in TIMING})
    return pl.DataFrame(rows, schema=ANSWER_SCHEMA, orient="row")


# ---- extraction -----------------------------------------------------------------------------


@stage
def claims(chunks: pl.DataFrame, extractor: Extractor) -> dict[str, pl.DataFrame]:
    """What the extractor returns for every chunk: spans and claims."""
    spans, claims = extractor.run(chunks)
    return {"spans": spans, "claims": claims}


@stage
def ground(
    claims: dict[str, pl.DataFrame], corpus: dict[str, pl.DataFrame], extractor_hash: str
) -> dict[str, pl.DataFrame]:
    """Ground spans and claims into the four graph frames plus the claim audit trail."""
    extraction = extract_stages.ground(
        corpus["chunks"],
        corpus["documents"],
        claims["spans"],
        claims["claims"],
        extractor_hash,
        now_us(),
    )
    return graph_frames(extraction)


@stage
def resolve(
    graph: dict[str, pl.DataFrame], corpus: dict[str, pl.DataFrame], resolver: ResolverSpec
) -> dict[str, pl.DataFrame]:
    """Add the resolver's `same_as` facts."""
    extraction = extract_stages.resolve(extraction_of(graph), corpus["chunks"], resolver, now_us())
    return graph_frames(extraction)


def timed[T](fn, *args) -> tuple[T, float]:
    t0 = time.perf_counter()
    out = fn(*args)
    return out, time.perf_counter() - t0
