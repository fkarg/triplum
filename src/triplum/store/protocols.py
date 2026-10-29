"""Persistence for pipeline records, one Protocol per capability. Only records exist so far."""

from abc import abstractmethod
from collections.abc import Iterable, Iterator
from typing import Protocol
from uuid import UUID

from triplum.datatype import Chunk, Source


class RecordStore(Protocol):
    """Stores sources and the current chunks of each source.

    Records have deterministic ids, so writing a record again normally writes an equal record.
    Sources are never replaced or removed: a changed text is a new source with a new `id`. Each
    source has one current chunk list, which `replace_chunks` swaps as a whole.

    A write checks its whole input before changing anything: when it raises, the store is unchanged.
    """

    @abstractmethod
    def add_sources(self, sources: Iterable[Source], /) -> None:
        """Store each source that is not stored yet.

        Re-adding an equal source does nothing. A different source with the `id` of a stored
        source, or of another source in the batch, raises `ValueError`.
        """
        ...

    @abstractmethod
    def replace_chunks(self, source_id: UUID, chunks: Iterable[Chunk], /) -> None:
        """Make `chunks`, in order, the complete current chunk list of the stored source `source_id`.

        The source's previous chunks are removed; an empty input leaves it without chunks. Raises
        `KeyError` if the source is not stored, and `ValueError` unless every chunk names that
        source and its `collection_id` and `origin`, has its list position as `ordinal`, and is an
        exact slice of the source text within its bounds. A chunk that differs from a stored chunk
        with the same `id`, of any source, also raises `ValueError`.
        """
        ...

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
        """The current chunks of one source, ordered by `ordinal`; empty if it has none."""
        ...
