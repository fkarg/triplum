import pyarrow as pa

from triplum.data import schema


def test_documents_schema_columns():
    assert schema.DOCUMENTS.names == ["id", "source", "uri", "observed_at", "metadata"]
    assert schema.DOCUMENTS.field("observed_at").type == pa.timestamp("us", tz="UTC")


def test_chunks_schema_columns():
    assert schema.CHUNKS.names == [
        "id",
        "document_id",
        "parent_id",
        "level",
        "span_start",
        "span_end",
        "text",
    ]
    assert schema.CHUNKS.field("id").type == pa.int64()


def test_chunk_embeddings_is_parametric_in_dims():
    s = schema.chunk_embeddings(4)
    assert s.names == ["chunk_id", "embedding_spec", "vector"]
    assert s.field("vector").type == pa.list_(pa.float32(), 4)


def test_facts_schema_columns():
    assert schema.FACTS.names == [
        "id",
        "proposition_id",
        "subject_id",
        "predicate",
        "object_id",
        "object_literal",
        "object_datatype",
        "object_lang",
        "valid_from",
        "valid_to",
        "recorded_at",
        "invalidated_at",
        "invalidated_by_fact_id",
        "confidence",
    ]


def test_ts_max_sentinel():
    assert schema.TS_MAX == 9223372036854775807
