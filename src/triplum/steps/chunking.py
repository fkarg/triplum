from abc import abstractmethod
from typing import Protocol

from triplum.datatype import Chunk, Source
from triplum.utils.fingerprint import FingerprintedComputationMixin

# operations of form Source -> Chunk


class Chunker(Protocol):
    """Split one source into chunks whose `start` and `text` are exact slices of its text."""

    @abstractmethod
    def __call__(self, source: Source, /) -> list[Chunk]: ...


class FixedSize(Chunker, FingerprintedComputationMixin):
    """Slice the text every `size` characters; the last chunk keeps the remainder.

    Chunks do not overlap and concatenate back to the source text. Empty text yields no chunks.
    """

    def __init__(self, size: int) -> None:
        if isinstance(size, bool) or size < 1:
            raise ValueError("size must be a positive integer")
        self.size = size

    def fingerprint_config(self) -> dict[str, object]:
        return {"size": self.size}

    def __call__(self, source: Source, /) -> list[Chunk]:
        return [
            Chunk(
                source_id=source.id,
                origin=source.origin,
                start=start,
                text=source.text[start : start + self.size],
            )
            for start in range(0, len(source.text), self.size)
        ]
