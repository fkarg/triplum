"""Persistence for pipeline records, one Protocol per capability. Only records exist so far."""

from abc import abstractmethod
from collections.abc import Iterable, Iterator
from typing import Protocol
from uuid import UUID

from triplum.datatype import Chunk, Source, Viewer


class RecordStore(Protocol):
    """Stores sources, who may read them, and the current chunks of each source.

    Records have deterministic ids, so writing a record again normally writes an equal record.
    Sources are never replaced or removed: a changed text is a new source with a new `id`. Each
    source has one current chunk list, which `replace_chunks` swaps as a whole.

    Every read takes a `Viewer` and sees only sources whose allowed principals meet the viewer's;
    chunks are readable with their source. A source the viewer may not read behaves exactly like a
    missing one. Writes are trusted ingestion: they take no viewer, and their conflict errors
    reveal stored ids.

    A write checks its whole input before changing anything: when it raises, the store is unchanged.
    Guarantees assume one writer at a time.
    """

    @abstractmethod
    def add_sources(self, sources: Iterable[Source], /, *, allow: Iterable[str]) -> None:
        """Store each source that is not stored yet, readable by the principals in `allow`.

        Re-adding an equal source with the same `allow` does nothing. `ValueError` for a stored
        source re-added with a different `allow`; for a different source with the `id` of a stored
        source or of another source in the batch; and for an `external_id` held by another source
        of the same collection, stored or in the batch. An empty `allow` lets nobody read.
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
    def source(self, id: UUID, /, *, viewer: Viewer) -> Source:
        """The source with this `id`; `KeyError` if there is none or `viewer` may not read it."""
        ...

    @abstractmethod
    def sources(self, *, collection_id: UUID, viewer: Viewer) -> Iterator[Source]:
        """The sources of collection `collection_id` that `viewer` may read, in no particular order.

        An unknown collection gives no sources.
        """
        ...

    @abstractmethod
    def chunks(self, source_id: UUID, /, *, viewer: Viewer) -> list[Chunk]:
        """The current chunks of one source, ordered by `ordinal`; empty if it has none.

        `KeyError` if the source is not stored or `viewer` may not read it.
        """
        ...
