"""Embedding spec and protocol. The spec is the identity of an embedding: same model on a different
runtime, or with different prefixes, is a different spec and a different index."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

import numpy as np

from triplum.cache import content_key


@dataclass(frozen=True)
class EmbeddingSpec:
    model: str
    revision: str
    dims: int
    pooling: str = "provider"
    normalize: bool = True
    query_prefix: str = ""
    passage_prefix: str = ""
    quantization: str = "none"
    runtime: str = "api"
    max_seq_length: int | None = None  # None: model default; silent truncation changes vectors
    instruction: str = ""  # task text recorded separately from the template in query_prefix
    padding_side: str = ""  # "" = model default; Qwen3 needs "left" or batched pooling is wrong

    def hash(self) -> str:
        return content_key("embedding_spec", asdict(self))[:16]

    def table_name(self) -> str:
        return f"emb_{self.hash()}"


class Embedder(Protocol):
    spec: EmbeddingSpec

    def embed_queries(self, texts: list[str]) -> np.ndarray: ...
    def embed_passages(self, texts: list[str]) -> np.ndarray: ...


def l2_normalize(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return (x / n).astype(np.float32)
