import hashlib
import json
from uuid import UUID, uuid7

import pytest

from triplum.datatype.ids import MAX_ORDINAL, chunk_id, source_id

COLLECTION = UUID("01900000-0000-7000-8000-000000000001")
OTHER = UUID("01900000-0000-7000-8000-000000000002")


def _leading_bits(kind: str, payload: list[object], n: int) -> int:
    """Independent recomputation of the documented digest encoding."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(kind.encode() + b"\0" + encoded.encode()).digest()
    return int.from_bytes(digest) >> (256 - n)


def _payload(id: UUID) -> int:
    """The 122 custom bits of a UUIDv8, read around its version and variant bits."""
    value = id.int
    return ((value >> 80) << 74) | (((value >> 64) & 0xFFF) << 62) | (value & ((1 << 62) - 1))


def test_ids_are_uuidv8_with_the_documented_layout():
    source = source_id(COLLECTION, "notes.md", "A")
    chunk = chunk_id(COLLECTION, source, 7, 3, "x")
    for id in (source, chunk):
        assert id.version == 8
        assert id.variant == "specified in RFC 4122"
    tag = _leading_bits("collection-tag", [str(COLLECTION)], 24)
    digest = _leading_bits("source-id", [str(COLLECTION), "notes.md", "A"], 98)
    assert _payload(source) == (tag << 98) | digest
    chunk_digest = _leading_bits("chunk-id", [str(COLLECTION), str(source), 7, 3, "x"], 48)
    expected = (tag >> 8) << 106 | (digest >> 56) << 64 | 7 << 48 | chunk_digest
    assert _payload(chunk) == expected


def test_source_id_follows_text_versions():
    a = source_id(COLLECTION, "notes.md", "A")
    b = source_id(COLLECTION, "notes.md", "B")
    assert b != a
    assert source_id(COLLECTION, "notes.md", "A") == a  # A -> B -> A recovers A


def test_source_id_distinguishes_origin_collection_and_framing():
    a = source_id(COLLECTION, "notes.md", "A")
    assert source_id(COLLECTION, "other.md", "A") != a
    assert source_id(OTHER, "notes.md", "A") != a
    assert source_id(COLLECTION, "ab", "c") != source_id(COLLECTION, "a", "bc")


def test_ids_share_a_collection_prefix():
    sources = [source_id(COLLECTION, f"doc{i}", "x") for i in range(3)]
    assert len({s.hex[:6] for s in sources}) == 1
    assert source_id(OTHER, "doc0", "x").hex[:6] != sources[0].hex[:6]


def test_chunk_ids_are_reproducible_and_scoped_to_their_source():
    s = source_id(COLLECTION, "notes.md", "Alpha Beta")
    c = chunk_id(COLLECTION, s, 0, 0, "Alpha")
    assert c.version == 8
    assert chunk_id(COLLECTION, s, 0, 0, "Alpha") == c
    other = source_id(COLLECTION, "other.md", "Alpha Beta")
    assert chunk_id(COLLECTION, other, 0, 0, "Alpha") != c
    assert chunk_id(COLLECTION, s, 1, 0, "Alpha") != c
    assert chunk_id(COLLECTION, s, 0, 6, "Alpha") != c


def test_chunk_ids_of_one_source_share_its_prefix():
    s = source_id(COLLECTION, "notes.md", "Alpha Beta")
    chunks = [chunk_id(COLLECTION, s, i, i * 6, "x") for i in range(3)]
    assert len({c.int >> 66 for c in chunks}) == 1  # tag and source prefix


@pytest.mark.parametrize("ordinal", [-1, MAX_ORDINAL + 1])
def test_chunk_ordinal_out_of_range_is_rejected(ordinal: int):
    with pytest.raises(ValueError, match="ordinal"):
        chunk_id(COLLECTION, uuid7(), ordinal, 0, "x")


def test_largest_ordinal_is_accepted():
    assert chunk_id(COLLECTION, uuid7(), MAX_ORDINAL, 0, "x").version == 8


def test_chunk_ids_keep_collections_apart_when_their_tags_collide():
    # These two collections share a 16-bit tag; the full collection id still separates chunks.
    first = UUID("01900000-0000-7000-8000-000000000193")
    second = UUID("01900000-0000-7000-8000-000000000212")
    assert _leading_bits("collection-tag", [str(first)], 16) == _leading_bits(
        "collection-tag", [str(second)], 16
    )
    source = uuid7()
    assert chunk_id(first, source, 0, 0, "x") != chunk_id(second, source, 0, 0, "x")
