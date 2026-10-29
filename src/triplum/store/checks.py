"""Write checks shared by record stores: conflicts and chunk-to-source consistency."""

from collections.abc import Callable, Iterable
from uuid import UUID

from triplum.datatype import Chunk, Source


def new_sources(sources: Iterable[Source], stored: Callable[[UUID], Source | None]) -> list[Source]:
    """The sources of the batch that are not stored yet, in order, without duplicates.

    `stored` looks up a stored source by id. Raises `ValueError` when a source differs from a
    stored or earlier batch source with the same id.
    """
    batch: dict[UUID, Source] = {}
    for source in sources:
        other = batch[source.id] if source.id in batch else stored(source.id)
        if other is not None and other != source:
            raise ValueError(f"a different source with id {source.id} is already stored or added")
        if other is None:
            batch[source.id] = source
    return list(batch.values())


def checked_chunks(
    source: Source, chunks: Iterable[Chunk], stored: Callable[[UUID], Chunk | None]
) -> list[Chunk]:
    """`chunks` as a list, after checking that they form a valid chunk list of `source`.

    `stored` looks up a stored chunk of any source by id. Raises `ValueError` for a chunk of another source,
    collection or origin, an ordinal other than its list position, a span outside the source text
    or not matching it, or a difference from a stored chunk with the same id.
    """
    checked = list(chunks)
    for position, chunk in enumerate(checked):
        if (chunk.source_id, chunk.collection_id, chunk.origin) != (
            source.id,
            source.collection_id,
            source.origin,
        ):
            raise ValueError(f"chunk {chunk.id} does not belong to source {source.id}")
        if chunk.ordinal != position:
            raise ValueError(f"chunk at position {position} has ordinal {chunk.ordinal}")
        end = chunk.start + len(chunk.text)
        if (
            chunk.start < 0
            or end > len(source.text)
            or source.text[chunk.start : end] != chunk.text
        ):
            raise ValueError(f"chunk {chunk.id} is not a slice of its source text")
        other = stored(chunk.id)
        if other is not None and other != chunk:
            raise ValueError(f"a different chunk with id {chunk.id} is already stored")
    return checked
