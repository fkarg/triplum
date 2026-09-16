from __future__ import annotations

import numpy as np

from triplum.embed.sentence_transformers import pick_device
from triplum.rerank.protocol import RerankSpec


class CrossEncoderReranker:
    def __init__(self, spec: RerankSpec, model, batch_size: int = 32) -> None:
        self.spec = spec
        self.model = model
        self.batch_size = batch_size

    @classmethod
    def from_model(
        cls, name: str, *, device: str | None = None, batch_size: int = 32, max_length: int = 512
    ):
        from sentence_transformers import CrossEncoder

        device = device or pick_device()
        model = CrossEncoder(name, device=device, max_length=max_length)
        return cls(RerankSpec(model=name, revision="hf", runtime=device), model, batch_size)

    def score(self, query: str, passages: list[str]) -> np.ndarray:
        pairs = [(query, p) for p in passages]
        return np.asarray(
            self.model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False),
            dtype=np.float32,
        )
