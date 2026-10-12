from uuid import uuid4

from triplum.cache import PydanticCodec
from triplum.datatype import Chunk, Source


def test_source_serialization_and_default_codec():
    source = Source(origin="a.md", text="Unicode: λ")
    assert source.model_dump() == {"id": source.id, "origin": "a.md", "text": "Unicode: λ"}
    codec = PydanticCodec(Source)
    assert codec.decode(codec.encode(source)) == source


def test_chunk_serialization_and_default_codec():
    chunk = Chunk(source_id=uuid4(), origin="https://example.org/page", start=0, text="x")
    assert chunk.model_dump() == {
        "id": chunk.id,
        "source_id": chunk.source_id,
        "origin": "https://example.org/page",
        "start": 0,
        "text": "x",
    }
    codec = PydanticCodec(Chunk)
    assert codec.decode(codec.encode(chunk)) == chunk
