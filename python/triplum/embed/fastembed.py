"""fastembed (ONNX) adapter."""

from __future__ import annotations

import numpy as np

from triplum.embed.protocol import EmbeddingSpec, l2_normalize


class FastEmbedEmbedder:
    def __init__(self, spec: EmbeddingSpec, model, batch_size: int = 64) -> None:
        self.spec = spec
        self.model = model
        self.batch_size = batch_size

    @classmethod
    def from_model(
        cls, name: str, *, query_prefix: str = "", passage_prefix: str = "", batch_size: int = 64
    ):
        import fastembed
        from fastembed import TextEmbedding

        model = TextEmbedding(model_name=name)
        dims = next(m["dim"] for m in TextEmbedding.list_supported_models() if m["model"] == name)
        spec = EmbeddingSpec(
            model=name,
            revision=f"fastembed-{fastembed.__version__}",
            dims=int(dims),
            pooling="model",
            normalize=True,
            query_prefix=query_prefix,
            passage_prefix=passage_prefix,
            quantization="onnx-default",
            runtime="onnx",
        )
        return cls(spec, model, batch_size)

    def _embed(self, texts: list[str], prefix: str) -> np.ndarray:
        arr = np.asarray(
            list(self.model.embed([prefix + t for t in texts], batch_size=self.batch_size)),
            dtype=np.float32,
        )
        return l2_normalize(arr) if self.spec.normalize else arr

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, self.spec.query_prefix)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, self.spec.passage_prefix)
