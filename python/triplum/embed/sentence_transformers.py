"""sentence-transformers adapter: picks cuda, mps or cpu and records it in the spec."""

from __future__ import annotations

import numpy as np

from triplum.embed.protocol import EmbeddingSpec, l2_normalize


def pick_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class SentenceTransformersEmbedder:
    def __init__(self, spec: EmbeddingSpec, model, batch_size: int = 32) -> None:
        self.spec = spec
        self.model = model
        self.batch_size = batch_size

    @classmethod
    def from_model(
        cls,
        name: str,
        *,
        query_prefix: str = "",
        passage_prefix: str = "",
        device: str | None = None,
        batch_size: int = 32,
        trust_remote_code: bool = False,
    ) -> "SentenceTransformersEmbedder":
        from sentence_transformers import SentenceTransformer

        device = device or pick_device()
        model = SentenceTransformer(name, device=device, trust_remote_code=trust_remote_code)
        card = getattr(model, "model_card_data", None)
        revision = getattr(card, "base_model_revision", None) or "unknown"
        spec = EmbeddingSpec(
            model=name,
            revision=str(revision),
            dims=int(model.get_sentence_embedding_dimension()),
            pooling="model",
            normalize=True,
            query_prefix=query_prefix,
            passage_prefix=passage_prefix,
            quantization="fp32" if device == "cpu" else "fp16",
            runtime=device,
        )
        return cls(spec, model, batch_size)

    def _embed(self, texts: list[str], prefix: str) -> np.ndarray:
        arr = self.model.encode(
            [prefix + t for t in texts],
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=False,
        ).astype(np.float32)
        return l2_normalize(arr) if self.spec.normalize else arr

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, self.spec.query_prefix)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, self.spec.passage_prefix)
