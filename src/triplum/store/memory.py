from collections.abc import Iterable, Iterator
from uuid import UUID

from triplum.datatype import Chunk, Source
from triplum.store.protocols import RecordStore


class MemoryStore(RecordStore):
    """Records in dictionaries; gone when the process ends."""

    def __init__(self) -> None:
        self._sources: dict[UUID, Source] = {}
        self._chunks: dict[UUID, Chunk] = {}

    def add_sources(self, sources: Iterable[Source], /) -> None:
        self._sources.update((source.id, source) for source in sources)

    def add_chunks(self, chunks: Iterable[Chunk], /) -> None:
        chunks = list(chunks)
        for chunk in chunks:
            if chunk.source_id not in self._sources:
                raise KeyError(chunk.source_id)
        self._chunks.update((chunk.id, chunk) for chunk in chunks)

    def source(self, id: UUID, /) -> Source:
        return self._sources[id]

    def sources(self) -> Iterator[Source]:
        return iter(list(self._sources.values()))

    def chunks(self, source_id: UUID, /) -> list[Chunk]:
        found = [chunk for chunk in self._chunks.values() if chunk.source_id == source_id]
        return sorted(found, key=lambda chunk: chunk.start)
