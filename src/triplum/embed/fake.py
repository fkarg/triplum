"""Deterministic bag-of-hashed-words embedder for tests: similar texts get similar vectors."""

from __future__ import annotations

import hashlib
import re

import numpy as np

from triplum.embed.protocol import EmbeddingSpec, l2_normalize


class FakeEmbedder:
    seed_sensitive = False

    def __init__(self, dims: int = 64) -> None:
        self.spec = EmbeddingSpec(model="fake", revision="1", dims=dims, runtime="fake")

    def _embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.spec.dims), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in re.findall(r"\w+", t.lower()):
                h = int.from_bytes(hashlib.sha256(tok.encode()).digest()[:8], "little")
                out[i, h % self.spec.dims] += 1.0 if (h >> 63) == 0 else -1.0
                out[i, (h >> 8) % self.spec.dims] += 0.5
        return l2_normalize(out)

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts)
