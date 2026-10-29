"""Deterministic UUIDv8 record ids derived from record content; no storage or I/O.

Every id is a pure function of its inputs: equal inputs give equal ids, and no timestamp enters.
The canonical encoding below is part of the id contract. Changing it re-keys every record.

Source payload (122 bits): ``[collection tag 24][scoped source digest 98]``.
Chunk payload (122 bits): ``[collection tag 16][source prefix 42][ordinal 16][chunk digest 48]``.
The collection tag and source prefix are locality hints only: the full collection id enters both
digests and the full source id enters the chunk digest, so prefix collisions never merge records.
"""

from typing import TYPE_CHECKING
from uuid import UUID, uuid8

from triplum.utils.cache import content_key

if TYPE_CHECKING:
    from triplum.datatype.chunk import Chunk
    from triplum.datatype.source import Source

UNSET = UUID(int=0)
"""Placeholder default of a record `id` field before its derived id is attached."""

MAX_ORDINAL = 0xFFFF
"""Largest chunk ordinal: a chunking result holds at most 65,536 chunks (ordinals 0 to 65,535)."""


def _bits(digest_hex: str, n: int) -> int:
    """The leading `n` bits of a SHA-256 hex digest."""
    return int(digest_hex, 16) >> (256 - n)


def _pack(payload: int) -> UUID:
    """Place 122 payload bits into the custom fields of a UUIDv8 (48, 12 and 62 bits)."""
    return uuid8(a=payload >> 74, b=(payload >> 62) & 0xFFF, c=payload & ((1 << 62) - 1))


def _unpack(id: UUID) -> int:
    """The 122 payload bits of a UUIDv8, inverting `_pack`."""
    value = id.int
    a = value >> 80
    b = (value >> 64) & 0xFFF
    c = value & ((1 << 62) - 1)
    return (a << 74) | (b << 62) | c


def _collection_tag(collection_id: UUID, n: int) -> int:
    return _bits(content_key("collection-tag", [str(collection_id)]), n)


def source_id(collection_id: UUID, origin: str, text: str) -> UUID:
    """Id of one exact prepared text from one origin in one collection.

    Origin and text are used exactly as given; normalize them before deriving the id.

    Examples:
        >>> a = source_id(collection.id, "notes.md", "A")
        >>> source_id(collection.id, "notes.md", "A") == a
        True
    """
    tag = _collection_tag(collection_id, 24)
    digest = _bits(content_key("source-id", [str(collection_id), origin, text]), 98)
    return _pack((tag << 98) | digest)


def chunk_id(collection_id: UUID, source_id: UUID, ordinal: int, start: int, text: str) -> UUID:
    """Id of the excerpt at `ordinal` and character offset `start` in one source's chunking result.

    The chunking computation does not enter: equal output gives equal ids, whichever chunker
    produced it. `collection_id` must be the collection of the source `source_id` names; both
    enter the digest in full.
    """
    if not 0 <= ordinal <= MAX_ORDINAL:
        raise ValueError(f"chunk ordinal must be between 0 and {MAX_ORDINAL}, got {ordinal}")
    tag = _collection_tag(collection_id, 16)
    source_prefix = (_unpack(source_id) >> (98 - 42)) & ((1 << 42) - 1)
    digest = _bits(
        content_key("chunk-id", [str(collection_id), str(source_id), ordinal, start, text]), 48
    )
    return _pack((tag << 106) | (source_prefix << 64) | (ordinal << 48) | digest)


def attach(record: Source | Chunk, derived: UUID) -> None:
    """Set `record.id` to `derived`, rejecting a different caller-supplied id.

    Called from record validators: records are frozen, so the id is set once during validation.
    """
    supplied = record.id
    if "id" in record.model_fields_set and supplied != derived:
        raise ValueError(f"id {supplied} does not match the id derived from the record, {derived}")
    object.__setattr__(record, "id", derived)
