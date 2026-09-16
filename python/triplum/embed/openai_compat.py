"""OpenAI-compatible embeddings endpoint. Prefixes from the spec are prepended here."""

from __future__ import annotations

import os
from typing import Any

import numpy as np

from triplum.embed.protocol import EmbeddingSpec, l2_normalize


class OpenAICompatEmbedder:
    def __init__(
        self,
        spec: EmbeddingSpec,
        *,
        base_url: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        client: Any | None = None,
        batch_size: int = 128,
    ) -> None:
        self.spec = spec
        self.batch_size = batch_size
        if client is None:
            from openai import OpenAI

            client = OpenAI(base_url=base_url, api_key=os.environ.get(api_key_env))
        self.client = client

    def _embed(self, texts: list[str], prefix: str) -> np.ndarray:
        rows: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = [prefix + t for t in texts[i : i + self.batch_size]]
            resp = self.client.embeddings.create(
                model=self.spec.model, input=batch, dimensions=self.spec.dims
            )
            rows.extend(item.embedding for item in resp.data)
        arr = np.asarray(rows, dtype=np.float32).reshape(len(texts), self.spec.dims)
        return l2_normalize(arr) if self.spec.normalize else arr

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, self.spec.query_prefix)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, self.spec.passage_prefix)
