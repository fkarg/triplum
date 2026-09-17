"""Deterministic token-overlap reranker for tests and offline runs."""

from __future__ import annotations

import re

import numpy as np

from triplum.rerank.protocol import RerankSpec


class FakeReranker:
    seed_sensitive = False
    spec = RerankSpec(model="fake", revision="1", runtime="fake")

    def score(self, query: str, passages: list[str]) -> np.ndarray:
        q = set(re.findall(r"\w+", query.lower()))
        out = np.zeros(len(passages), dtype=np.float32)
        for i, p in enumerate(passages):
            toks = re.findall(r"\w+", p.lower())
            out[i] = sum(t in q for t in toks) / max(1, len(toks))
        return out
