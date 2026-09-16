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

    def score(self, query: str, passages: list[str]) -> np.ndarray:
        """Higher is more relevant. Shape (len(passages),), float32."""
        ...
