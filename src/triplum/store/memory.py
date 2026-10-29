from collections.abc import Iterable, Iterator
from uuid import UUID

from triplum.datatype import Chunk, Source
from triplum.store.checks import checked_chunks, new_sources
from triplum.store.protocols import RecordStore


class MemoryStore(RecordStore):
    """Records in dictionaries; gone when the process ends. Not safe for concurrent writers."""

    def __init__(self) -> None:
        self._sources: dict[UUID, Source] = {}
        self._chunks: dict[UUID, list[Chunk]] = {}
        self._chunk_ids: dict[UUID, Chunk] = {}

    def add_sources(self, sources: Iterable[Source], /) -> None:
        for source in new_sources(sources, self._sources.get):
            self._sources[source.id] = source

    def replace_chunks(self, source_id: UUID, chunks: Iterable[Chunk], /) -> None:
        checked = checked_chunks(self._sources[source_id], chunks, self._chunk_ids.get)
        for chunk in self._chunks.get(source_id, []):
            del self._chunk_ids[chunk.id]
        self._chunks[source_id] = checked
        self._chunk_ids.update((chunk.id, chunk) for chunk in checked)

    def source(self, id: UUID, /) -> Source:
        return self._sources[id]

    def sources(self) -> Iterator[Source]:
        return iter(list(self._sources.values()))

    def chunks(self, source_id: UUID, /) -> list[Chunk]:
        return list(self._chunks.get(source_id, []))
