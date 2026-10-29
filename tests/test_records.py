from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from triplum.cache import PydanticCodec
from triplum.datatype import Chunk, Collection, Source
from triplum.datatype.ids import chunk_id, source_id

COLLECTION = UUID("01900000-0000-7000-8000-000000000001")


def test_source_serialization_and_default_codec():
    source = Source(collection_id=COLLECTION, origin="a.md", text="Unicode: λ")
    assert source.model_dump() == {
        "id": source.id,
        "collection_id": COLLECTION,
        "origin": "a.md",
        "text": "Unicode: λ",
    }
    codec = PydanticCodec(Source)
    assert codec.decode(codec.encode(source)) == source


def test_chunk_serialization_and_default_codec():
    chunk = Chunk(
        collection_id=COLLECTION,
        source_id=uuid4(),
        origin="https://example.org/page",
        ordinal=0,
        start=0,
        text="x",
    )
    assert chunk.model_dump() == {
        "id": chunk.id,
        "collection_id": COLLECTION,
        "source_id": chunk.source_id,
        "origin": "https://example.org/page",
        "ordinal": 0,
        "start": 0,
        "text": "x",
    }
    codec = PydanticCodec(Chunk)
    assert codec.decode(codec.encode(chunk)) == chunk


def test_source_id_is_derived_and_reproducible():
    collection = Collection(name="notes")
    a = Source(collection_id=collection.id, origin="a.md", text="A")
    assert a.id == source_id(collection.id, "a.md", "A")
    assert a.id.version == 8
    b = Source(collection_id=collection.id, origin="a.md", text="B")
    assert b.id != a.id
    assert Source(collection_id=collection.id, origin="a.md", text="A").id == a.id  # A -> B -> A


def test_chunk_id_is_derived_and_reproducible():
    source = Source(collection_id=COLLECTION, origin="a.md", text="abc")
    chunk = Chunk(
        collection_id=COLLECTION, source_id=source.id, origin="a.md", ordinal=1, start=2, text="c"
    )
    assert chunk.id == chunk_id(COLLECTION, source.id, 1, 2, "c")
    assert chunk.model_validate(chunk.model_dump(exclude={"id"})) == chunk


def test_matching_supplied_id_is_accepted_and_mismatching_is_rejected():
    source = Source(collection_id=COLLECTION, origin="a.md", text="A")
    assert Source(id=source.id, collection_id=COLLECTION, origin="a.md", text="A") == source
    with pytest.raises(ValidationError, match="does not match"):
        Source(id=source.id, collection_id=COLLECTION, origin="a.md", text="B")
    chunk = Chunk(
        collection_id=COLLECTION, source_id=source.id, origin="a.md", ordinal=0, start=0, text="A"
    )
    with pytest.raises(ValidationError, match="does not match"):
        Chunk(
            id=chunk.id,
            collection_id=COLLECTION,
            source_id=source.id,
            origin="a.md",
            ordinal=1,
            start=0,
            text="A",
        )


def test_records_are_frozen():
    source = Source(collection_id=COLLECTION, origin="a.md", text="A")
    with pytest.raises(ValidationError, match="frozen"):
        source.text = "B"  # ty: ignore[invalid-assignment] - the point of the test
    chunk = Chunk(
        collection_id=COLLECTION, source_id=source.id, origin="a.md", ordinal=0, start=0, text="A"
    )
    with pytest.raises(ValidationError, match="frozen"):
        chunk.ordinal = 1  # ty: ignore[invalid-assignment] - the point of the test


@pytest.mark.parametrize("ordinal", [-1, 65536])
def test_chunk_ordinal_is_bounded(ordinal: int):
    with pytest.raises(ValidationError, match="ordinal"):
        Chunk(
            collection_id=COLLECTION,
            source_id=uuid4(),
            origin="a.md",
            ordinal=ordinal,
            start=0,
            text="x",
        )
