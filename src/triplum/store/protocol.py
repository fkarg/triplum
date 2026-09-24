"""The store protocol. Every read takes a Viewer; backends declare what they can filter exactly."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import polars as pl

from triplum.data.corpus import CorpusBatch
from triplum.data.viewer import Viewer
from triplum.embed.protocol import EmbeddingSpec


@dataclass(frozen=True)
class Capabilities:
    exact_acl_filter: bool
    vector_search_exact: bool  # brute force (exact) vs approximate
    bm25: bool


class Store(Protocol):
    def ingest_corpus(self, corpus_hash: str, dataset: str, batches: Iterable[CorpusBatch]) -> None:
        """Bind a fingerprint and publish the corpus after all batches are written."""
        ...

    def put_documents(self, docs: pl.DataFrame, grants: pl.DataFrame) -> None: ...
    def put_chunks(self, chunks: pl.DataFrame) -> None: ...
    def put_embeddings(
        self, spec: EmbeddingSpec, chunk_ids: list[int], vectors: np.ndarray
    ) -> None: ...
    def get_chunks(self, ids: list[int], viewer: Viewer) -> pl.DataFrame: ...
    def search_text(self, query: str, viewer: Viewer, limit: int = 10) -> pl.DataFrame:
        """Visible full-text matches in stable document order, without relevance ranking."""
        ...

    def vector_search(
        self, spec: EmbeddingSpec, query: np.ndarray, k: int, viewer: Viewer
    ) -> pl.DataFrame: ...
    def bm25(self, query: str, k: int, viewer: Viewer) -> pl.DataFrame: ...
    def capabilities(self) -> Capabilities: ...

    # ---- identity and effects: what a stage sees, and what a store-effect stage records ----

    def identity(self) -> str:
        """What the store holds, as a content key of its corpus and graph identities; the
        identity of a store argument to a stage, and what a run records instead of a file hash."""
        ...

    def begin_effect(self, key: str, stage: str) -> None: ...
    def complete_effect(self, key: str) -> None: ...
    def effect_complete(self, key: str) -> bool:
        """Whether the store-effect stage with this execution key ran to completion here."""
        ...

    # ---- graph side: the D2 fact tables under D4 visibility -------------------------------

    def put_graph(
        self,
        entities: pl.DataFrame,
        facts: pl.DataFrame,
        fact_support: pl.DataFrame,
        mentions: pl.DataFrame,
    ) -> None:
        """Write the four graph frames in one transaction. A fact without a support group, or
        with both or neither of `object_id` and `object_literal`, is rejected."""
        ...

    def facts(self, viewer: Viewer) -> pl.DataFrame:
        """Every fact visible to the viewer: one of its support groups is fully visible, its
        validity interval contains `as_of_valid`, it was recorded by `as_of_recorded` and not
        invalidated by then."""
        ...

    def mentions(self, chunk_ids: list[int], viewer: Viewer) -> pl.DataFrame: ...

    def neighbours(self, entity_ids: list[str], hops: int, viewer: Viewer) -> pl.DataFrame:
        """The visible facts within `hops` of the given entities, following `same_as` facts the
        viewer can see as identity (zero cost) and every other fact as one hop."""
        ...
