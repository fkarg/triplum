"""Per-text cache around any embedder, keyed on (spec hash, role, text)."""

from __future__ import annotations

import numpy as np

from triplum.cache import Cache, content_key
from triplum.embed.protocol import Embedder


class CachedEmbedder:
    def __init__(self, inner: Embedder, cache: Cache) -> None:
        self.inner = inner
        self.cache = cache
        self.spec = inner.spec

    def _embed(self, texts: list[str], role: str) -> np.ndarray:
        keys = [
            content_key("embed", {"spec": self.spec.hash(), "role": role, "text": t}) for t in texts
        ]
        out = np.zeros((len(texts), self.spec.dims), dtype=np.float32)
        missing: list[int] = []
        for i, k in enumerate(keys):
            raw = self.cache.get(k)
            if raw is None:
                missing.append(i)
            else:
                out[i] = np.frombuffer(raw, dtype=np.float32)
        if missing:
            fn = self.inner.embed_queries if role == "query" else self.inner.embed_passages
            vecs = fn([texts[i] for i in missing])
            for j, i in enumerate(missing):
                out[i] = vecs[j]
                self.cache.put(keys[i], vecs[j].astype(np.float32).tobytes())
        return out

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, "query")

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, "passage")
