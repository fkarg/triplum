"""Regression checks for the retained Rust exports, not approval of the rebuild schema."""

import pyarrow as pa

from triplum import _core


def test_documents_schema_columns():
    s = pa.schema(_core.schema("documents"))
    assert s.names == [
        "id",
        "source",
        "uri",
        "observed_at",
        "metadata",
    ]
    assert s.field("observed_at").type == pa.timestamp("us", tz="UTC")


def test_chunks_schema_columns():
    s = pa.schema(_core.schema("chunks"))
    assert s.names == [
        "id",
        "document_id",
        "parent_id",
        "level",
        "span_start",
        "span_end",
        "text",
    ]
    assert s.field("id").type == pa.int64()


def test_chunk_embeddings_is_parametric_in_dims():
    s = pa.schema(_core.schema("chunk_embeddings", 4))
    assert s.names == ["chunk_id", "embedding_spec", "vector"]
    assert s.field("vector").type == pa.list_(pa.float32(), 4)


def test_facts_schema_columns():
    assert pa.schema(_core.schema("facts")).names == [
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
    assert _core.ts_max() == 9223372036854775807
