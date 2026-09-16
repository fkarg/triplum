use std::sync::Arc;

use arrow_schema::{DataType, Field, Schema, SchemaRef, TimeUnit};

fn ts() -> DataType {
    DataType::Timestamp(TimeUnit::Microsecond, Some("UTC".into()))
}

fn f(name: &str, dt: DataType, nullable: bool) -> Field {
    Field::new(name, dt, nullable)
}

pub fn documents() -> SchemaRef {
    Arc::new(Schema::new(vec![
        f("id", DataType::Utf8, false),
        f("source", DataType::Utf8, false),
        f("uri", DataType::Utf8, true),
        f("observed_at", ts(), false),
        f("metadata", DataType::Utf8, true),
    ]))
}

pub fn document_grants() -> SchemaRef {
    Arc::new(Schema::new(vec![
        f("document_id", DataType::Utf8, false),
        f("principal", DataType::Utf8, false),
        f("granted_at", ts(), false),
        f("revoked_at", ts(), true),
    ]))
}

pub fn chunks() -> SchemaRef {
    Arc::new(Schema::new(vec![
        f("id", DataType::Int64, false),
        f("document_id", DataType::Utf8, false),
        f("parent_id", DataType::Int64, true),
        f("level", DataType::Int32, false),
        f("span_start", DataType::Int64, false),
        f("span_end", DataType::Int64, false),
        f("text", DataType::Utf8, false),
    ]))
}

pub fn chunk_embeddings(dims: i32) -> SchemaRef {
    Arc::new(Schema::new(vec![
        f("chunk_id", DataType::Int64, false),
        f("embedding_spec", DataType::Utf8, false),
        f(
            "vector",
            DataType::FixedSizeList(Arc::new(Field::new("item", DataType::Float32, true)), dims),
            false,
        ),
    ]))
}

pub fn entities() -> SchemaRef {
    Arc::new(Schema::new(vec![
        f("id", DataType::Utf8, false),
        f("canonical_id", DataType::Utf8, true),
    ]))
}

pub fn facts() -> SchemaRef {
    Arc::new(Schema::new(vec![
        f("id", DataType::Int64, false),
        f("proposition_id", DataType::Utf8, false),
        f("subject_id", DataType::Utf8, false),
        f("predicate", DataType::Utf8, false),
        f("object_id", DataType::Utf8, true),
        f("object_literal", DataType::Utf8, true),
        f("object_datatype", DataType::Utf8, true),
        f("object_lang", DataType::Utf8, true),
        f("valid_from", ts(), false),
        f("valid_to", ts(), false),
        f("recorded_at", ts(), false),
        f("invalidated_at", ts(), true),
        f("invalidated_by_fact_id", DataType::Int64, true),
        f("confidence", DataType::Float32, false),
    ]))
}

pub fn fact_support() -> SchemaRef {
    Arc::new(Schema::new(vec![
        f("fact_id", DataType::Int64, false),
        f("group_no", DataType::Int32, false),
        f("chunk_id", DataType::Int64, false),
        f("extractor", DataType::Utf8, false),
        f("recorded_at", ts(), false),
    ]))
}

pub fn mentions() -> SchemaRef {
    Arc::new(Schema::new(vec![
        f("entity_id", DataType::Utf8, false),
        f("chunk_id", DataType::Int64, false),
        f("span_start", DataType::Int64, false),
        f("span_end", DataType::Int64, false),
        f("confidence", DataType::Float32, false),
    ]))
}

/// Look a canonical schema up by table name. `dims` is only used by `chunk_embeddings`.
pub fn by_name(name: &str, dims: Option<i32>) -> Option<SchemaRef> {
    match name {
        "documents" => Some(documents()),
        "document_grants" => Some(document_grants()),
        "chunks" => Some(chunks()),
        "chunk_embeddings" => dims.map(chunk_embeddings),
        "entities" => Some(entities()),
        "facts" => Some(facts()),
        "fact_support" => Some(fact_support()),
        "mentions" => Some(mentions()),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_table_resolves() {
        for name in ["documents", "document_grants", "chunks", "entities", "facts", "fact_support", "mentions"] {
            assert!(by_name(name, None).is_some(), "{name}");
        }
        assert_eq!(by_name("chunk_embeddings", Some(8)).unwrap().fields().len(), 3);
        assert!(by_name("chunk_embeddings", None).is_none());
        assert!(by_name("nope", None).is_none());
    }
}
