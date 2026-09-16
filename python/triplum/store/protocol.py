"""The store protocol. Every read takes a Viewer; backends declare what they can filter exactly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import polars as pl

from triplum.data.viewer import Viewer
from triplum.embed.protocol import EmbeddingSpec


@dataclass(frozen=True)
class Capabilities:
    exact_acl_filter: bool
    vector_search_exact: bool  # brute force (exact) vs approximate
    bm25: bool


class Store(Protocol):
    def put_documents(self, docs: pl.DataFrame, grants: pl.DataFrame) -> None: ...
    def put_chunks(self, chunks: pl.DataFrame) -> None: ...
    def put_embeddings(
        self, spec: EmbeddingSpec, chunk_ids: list[int], vectors: np.ndarray
    ) -> None: ...
    def get_chunks(self, ids: list[int], viewer: Viewer) -> pl.DataFrame: ...
    def vector_search(
        self, spec: EmbeddingSpec, query: np.ndarray, k: int, viewer: Viewer
    ) -> pl.DataFrame: ...
    def bm25(self, query: str, k: int, viewer: Viewer) -> pl.DataFrame: ...
    def capabilities(self) -> Capabilities: ...
