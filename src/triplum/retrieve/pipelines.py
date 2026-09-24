"""Named retrieval pipelines: each is one composition of the stages with its defaults, callable
as a plain function, and `PIPELINES` is the one list the runner, the CLI and the code fingerprint
read. A pipeline takes the questions frame, a store and a viewer, plus keyword settings, and
returns the `stages.SCHEMA` frame; components it does not use are ignored. Pass a bigger
`candidates`, another embedder or a different reranker to override a default, or compose the
stages directly for anything these do not cover.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import polars as pl

from triplum.data.viewer import Viewer
from triplum.embed.protocol import Embedder
from triplum.rerank.protocol import Reranker
from triplum.retrieve import stages
from triplum.store.protocol import Store

TOP_K = 5
CANDIDATES = 20


@dataclass(frozen=True)
class Pipeline:
    name: str
    description: str
    run: Callable[..., pl.DataFrame]
    needs_embedder: bool = False
    needs_reranker: bool = False


def closed_book(questions: pl.DataFrame, store: Store, viewer: Viewer, **_) -> pl.DataFrame:
    return stages.none(questions)


def oracle(
    questions: pl.DataFrame, store: Store, viewer: Viewer, *, k: int = TOP_K, **_
) -> pl.DataFrame:
    return stages.oracle(questions, k)


def bm25(
    questions: pl.DataFrame, store: Store, viewer: Viewer, *, k: int = TOP_K, **_
) -> pl.DataFrame:
    return stages.bm25(questions, store, k, viewer)


def dense(
    questions: pl.DataFrame,
    store: Store,
    viewer: Viewer,
    *,
    embedder: Embedder,
    k: int = TOP_K,
    **_,
) -> pl.DataFrame:
    return stages.dense(questions, store, embedder, k, viewer)


def rrf(
    questions: pl.DataFrame,
    store: Store,
    viewer: Viewer,
    *,
    embedder: Embedder,
    k: int = TOP_K,
    candidates: int = CANDIDATES,
    **_,
) -> pl.DataFrame:
    return stages.fusion(questions, store, embedder, k, candidates, viewer)


def hybrid(
    questions: pl.DataFrame,
    store: Store,
    viewer: Viewer,
    *,
    embedder: Embedder,
    reranker: Reranker,
    k: int = TOP_K,
    candidates: int = CANDIDATES,
    **_,
) -> pl.DataFrame:
    return stages.hybrid(questions, store, embedder, reranker, k, candidates, viewer)


PIPELINES: dict[str, Pipeline] = {
    p.name: p
    for p in (
        Pipeline("closed_book", "no retrieval; the reader sees only the question", closed_book),
        Pipeline("bm25", "FTS5 BM25 over the viewer's chunks, top k", bm25),
        Pipeline("dense", "query embedding, vector KNN under the viewer, top k", dense, True),
        Pipeline(
            "rrf",
            "dense and BM25 candidates fused by reciprocal rank fusion, top k by fused score",
            rrf,
            True,
        ),
        Pipeline(
            "hybrid",
            "rrf fusion, then the top candidates reranked by a cross-encoder, top k",
            hybrid,
            True,
            True,
        ),
        Pipeline("oracle", "the gold chunks in gold order; the reader ceiling", oracle),
    )
}
NAMES = list(PIPELINES)


def get(name: str) -> Pipeline:
    if name not in PIPELINES:
        raise ValueError(f"unknown pipeline {name!r}; one of {', '.join(NAMES)}")
    return PIPELINES[name]
