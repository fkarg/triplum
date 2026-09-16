"""Retrieval stages. Each returns a frame (question_id, chunk_id, rank, score), rank starting at 1.
Visibility is the store's job: every call passes the Viewer through."""

from __future__ import annotations

import polars as pl

from triplum.data.viewer import Viewer
from triplum.embed.protocol import Embedder
from triplum.rerank.protocol import Reranker
from triplum.store.protocol import Store

SCHEMA = {"question_id": pl.Utf8, "chunk_id": pl.Int64, "rank": pl.Int64, "score": pl.Float64}


def _frame(rows: list[tuple]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=SCHEMA, orient="row")


def _ranked(qid: str, ids: list[int], scores: list[float], k: int) -> list[tuple]:
    return [(qid, int(c), r + 1, float(s)) for r, (c, s) in enumerate(zip(ids[:k], scores[:k]))]


def none(questions: pl.DataFrame) -> pl.DataFrame:
    return _frame([])


def oracle(questions: pl.DataFrame, k: int) -> pl.DataFrame:
    rows = []
    for q in questions.iter_rows(named=True):
        ids = q["gold_chunk_ids"][:k]
        rows += _ranked(q["id"], ids, [1.0] * len(ids), k)
    return _frame(rows)


def dense(
    questions: pl.DataFrame, store: Store, embedder: Embedder, k: int, viewer: Viewer
) -> pl.DataFrame:
    qvecs = embedder.embed_queries(questions["question"].to_list())
    rows = []
    for q, v in zip(questions.iter_rows(named=True), qvecs):
        hits = store.vector_search(embedder.spec, v, k, viewer)
        rows += _ranked(q["id"], hits["id"].to_list(), hits["score"].to_list(), k)
    return _frame(rows)


def bm25(questions: pl.DataFrame, store: Store, k: int, viewer: Viewer) -> pl.DataFrame:
    rows = []
    for q in questions.iter_rows(named=True):
        hits = store.bm25(q["question"], k, viewer)
        rows += _ranked(q["id"], hits["id"].to_list(), hits["score"].to_list(), k)
    return _frame(rows)


def rrf(rankings: list[list[int]], k_const: int = 60) -> list[tuple[int, float]]:
    """Reciprocal rank fusion; returns (id, score) sorted by score desc."""
    acc: dict[int, float] = {}
    for ranking in rankings:
        for r, cid in enumerate(ranking):
            acc[cid] = acc.get(cid, 0.0) + 1.0 / (k_const + r + 1)
    return sorted(acc.items(), key=lambda t: (-t[1], t[0]))


def hybrid(
    questions: pl.DataFrame,
    store: Store,
    embedder: Embedder,
    reranker: Reranker,
    k: int,
    candidates: int,
    viewer: Viewer,
) -> pl.DataFrame:
    """Dense and BM25 candidates fused by RRF, top `candidates` reranked, top k returned."""
    qvecs = embedder.embed_queries(questions["question"].to_list())
    rows = []
    for q, v in zip(questions.iter_rows(named=True), qvecs):
        d = store.vector_search(embedder.spec, v, candidates, viewer)["id"].to_list()
        b = store.bm25(q["question"], candidates, viewer)["id"].to_list()
        fused = [cid for cid, _ in rrf([d, b])][:candidates]
        if not fused:
            continue
        chunks = store.get_chunks(fused, viewer)
        text_by_id = dict(zip(chunks["id"].to_list(), chunks["text"].to_list()))
        ids = [c for c in fused if c in text_by_id]
        scores = reranker.score(q["question"], [text_by_id[c] for c in ids])
        order = sorted(range(len(ids)), key=lambda i: (-float(scores[i]), ids[i]))
        rows += _ranked(q["id"], [ids[i] for i in order], [float(scores[i]) for i in order], k)
    return _frame(rows)
