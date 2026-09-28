"""Persistence for pipeline records, one Protocol per capability. Only records exist so far."""

from abc import abstractmethod
from collections.abc import Iterable, Iterator
from typing import Protocol
from uuid import UUID

from triplum.datatype import Chunk, Source


class RecordStore(Protocol):
    """Stores sources and their chunks by `id`.

    Adding a record whose `id` is already stored replaces it. A chunk's source must be added
    before the chunk; otherwise `add_chunks` raises `KeyError` and stores none of the batch.
    """

    @abstractmethod
    def add_sources(self, sources: Iterable[Source], /) -> None: ...

    @abstractmethod
    def add_chunks(self, chunks: Iterable[Chunk], /) -> None: ...

    @abstractmethod
    def source(self, id: UUID, /) -> Source:
        """The source with this `id`; `KeyError` if there is none."""
        ...

    @abstractmethod
    def sources(self) -> Iterator[Source]:
        """All sources, in no particular order."""
        ...

    @abstractmethod
    def chunks(self, source_id: UUID, /) -> list[Chunk]:
        """The chunks of one source, ordered by `start`; empty if it has none."""
        ...
