from collections.abc import Iterable, Iterator
from uuid import UUID

from triplum.datatype import Chunk, Source, Viewer
from triplum.store.checks import checked_chunks, new_sources, principals
from triplum.store.protocols import RecordStore


class MemoryStore(RecordStore):
    """Records in dictionaries; gone when the process ends. Not safe for concurrent writers."""

    def __init__(self) -> None:
        self._sources: dict[UUID, Source] = {}
        self._access: dict[UUID, frozenset[str]] = {}
        self._chunks: dict[UUID, list[Chunk]] = {}
        self._chunk_ids: dict[UUID, Chunk] = {}
        self._external_ids: dict[tuple[UUID, str], UUID] = {}

    def add_sources(self, sources: Iterable[Source], /, *, allow: Iterable[str]) -> None:
        access = principals(allow)

        def stored(id: UUID) -> tuple[Source, frozenset[str]] | None:
            return (self._sources[id], self._access[id]) if id in self._sources else None

        for source in new_sources(
            sources, access, stored, lambda c, e: self._external_ids.get((c, e))
        ):
            self._sources[source.id] = source
            self._access[source.id] = access
            if source.external_id is not None:
                self._external_ids[source.collection_id, source.external_id] = source.id

    def replace_chunks(self, source_id: UUID, chunks: Iterable[Chunk], /) -> None:
        checked = checked_chunks(self._sources[source_id], chunks, self._chunk_ids.get)
        for chunk in self._chunks.get(source_id, []):
            del self._chunk_ids[chunk.id]
        self._chunks[source_id] = checked
        self._chunk_ids.update((chunk.id, chunk) for chunk in checked)

    def _visible(self, id: UUID, viewer: Viewer) -> bool:
        return id in self._access and not self._access[id].isdisjoint(viewer.principals)

    def source(self, id: UUID, /, *, viewer: Viewer) -> Source:
        if not self._visible(id, viewer):
            raise KeyError(id)
        return self._sources[id]

    def sources(self, *, viewer: Viewer) -> Iterator[Source]:
        return iter([s for id, s in self._sources.items() if self._visible(id, viewer)])

    def chunks(self, source_id: UUID, /, *, viewer: Viewer) -> list[Chunk]:
        if not self._visible(source_id, viewer):
            raise KeyError(source_id)
        return list(self._chunks.get(source_id, []))
