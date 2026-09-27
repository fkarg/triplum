# Operations of type Chunk -> Chunk and Chunk -> Text
from abc import abstractmethod
from typing import Protocol

from triplum.datatype import Chunk


class EmbeddingText(Protocol):
    """Choose the text that represents one chunk for embedding."""

    @abstractmethod
    def __call__(self, chunk: Chunk, /) -> str: ...


class OriginalText(EmbeddingText):
    """Embed the chunk's own text, unchanged."""

    def __call__(self, chunk: Chunk, /) -> str:
        return chunk.text
