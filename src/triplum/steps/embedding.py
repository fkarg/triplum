# operations of form Text -> Embedding
from abc import abstractmethod
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

type Vectors = NDArray[np.float32]
"""Embeddings of a batch of texts: shape `(len(texts), dimensions)`, one row per text."""


class Embedder(Protocol):
    """Embed a batch of texts into vectors of a fixed size."""

    dimensions: int

    @abstractmethod
    def __call__(self, texts: list[str], /) -> Vectors: ...


class ZeroEmbedder(Embedder):
    """Return all-zero vectors. This is a placeholder for an embedding function."""

    def __init__(self, dimensions: int = 1536) -> None:
        self.dimensions = dimensions

    def __call__(self, texts: list[str], /) -> Vectors:
        return np.zeros((len(texts), self.dimensions), dtype=np.float32)
