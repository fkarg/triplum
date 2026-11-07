"""Write checks shared by record stores: conflicts and chunk-to-source consistency."""

from collections.abc import Callable, Iterable
from uuid import UUID

from triplum.datatype import Chunk, Source


def principals(allow: Iterable[str]) -> frozenset[str]:
    """`allow` as a set; a bare string is rejected, since it would allow its single characters."""
    if isinstance(allow, str):
        raise TypeError(f"allow must be a collection of principals, not the string {allow!r}")
    return frozenset(allow)


def new_sources(
    sources: Iterable[Source],
    allow: frozenset[str],
    stored: Callable[[UUID], tuple[Source, frozenset[str]] | None],
    holder: Callable[[UUID, str], UUID | None],
) -> list[Source]:
    """The sources of the batch that are not stored yet, in order, without duplicates.

    `stored` looks up a stored source and its allowed principals by id; `holder` finds the id of
    the stored source with an external id in a collection. Raises `ValueError` when a source
    differs from a stored or earlier batch source with the same id, when a stored source is
    re-added with another `allow`, or when another source of its collection, stored or in the
    batch, holds its external id.
    """
    batch: dict[UUID, Source] = {}
    held: dict[tuple[UUID, str], UUID] = {}
    for source in sources:
        record = (batch[source.id], allow) if source.id in batch else stored(source.id)
        other, access = (None, allow) if record is None else record
        if other is not None and other != source:
            raise ValueError(f"a different source with id {source.id} is already stored or added")
        if access != allow:
            raise ValueError(f"source {source.id} is already stored with other access")
        if other is None:
            if source.external_id is not None:
                key = (source.collection_id, source.external_id)
                owner = held.get(key) or holder(*key)
                if owner is not None:
                    raise ValueError(
                        f"external id {source.external_id!r} is already held by source {owner}"
                    )
                held[key] = source.id
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
