"""Reranker identity and protocol: a `RerankSpec` names the model, revision and runtime so the
run identity and the call cache can tell rerankers apart; a `Reranker` scores (query, passage)
pairs pointwise."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

import numpy as np

from triplum.cache import content_key


@dataclass(frozen=True)
class RerankSpec:
    model: str
    revision: str
    runtime: str = "api"

    def hash(self) -> str:
        return content_key("rerank_spec", asdict(self))[:16]


class Reranker(Protocol):
    spec: RerankSpec
    seed_sensitive: bool

    def score(self, query: str, passages: list[str]) -> np.ndarray:
        """Higher is more relevant. Shape (len(passages),), float32."""
        ...
