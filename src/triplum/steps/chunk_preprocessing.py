# Operations of type Chunk -> Chunk and Chunk -> Text
from abc import abstractmethod
from typing import Protocol

from triplum.datatype import Chunk
from triplum.utils.fingerprint import FingerprintedComputationMixin


class EmbeddingText(Protocol):
    """Choose the text that represents one chunk for embedding."""

    @abstractmethod
    def __call__(self, chunk: Chunk, /) -> str: ...


class OriginalText(EmbeddingText, FingerprintedComputationMixin):
    """Embed the chunk's own text, unchanged."""

    def fingerprint_config(self) -> dict[str, object]:
        return {}

    def __call__(self, chunk: Chunk, /) -> str:
        return chunk.text
