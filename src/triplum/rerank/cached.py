"""Per-(query, passage) cache around any reranker, keyed on the reranker spec."""

from __future__ import annotations

import numpy as np

from triplum.cache import Cache, content_key
from triplum.rerank.protocol import Reranker


class CachedReranker:
    def __init__(self, inner: Reranker, cache: Cache) -> None:
        self.inner = inner
        self.cache = cache
        self.spec = inner.spec
        self.seed_sensitive = inner.seed_sensitive
        self.calls = 0  # pairs actually scored by the inner reranker

    def score(self, query: str, passages: list[str]) -> np.ndarray:
        keys = [
            content_key("rerank", {"spec": self.spec.hash(), "query": query, "passage": p})
            for p in passages
        ]
        out = np.zeros(len(passages), dtype=np.float32)
        missing = []
        for i, k in enumerate(keys):
            raw = self.cache.get(k)
            if raw is None:
                missing.append(i)
            else:
                out[i] = np.frombuffer(raw, dtype=np.float32)[0]
        if missing:
            scores = self.inner.score(query, [passages[i] for i in missing])
            self.calls += len(missing)
            for j, i in enumerate(missing):
                out[i] = scores[j]
                self.cache.put(keys[i], np.asarray([scores[j]], dtype=np.float32).tobytes())
        return out
