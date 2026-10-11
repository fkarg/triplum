from uuid import uuid4

from triplum.datatype import Chunk


def test_chunk_origin_survives_json_round_trip():
    chunk = Chunk(source_id=uuid4(), origin="https://example.org/page", start=0, text="x")

    assert Chunk.model_validate_json(chunk.model_dump_json()) == chunk
