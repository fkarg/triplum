"""Canonical Arrow schemas, owned by the Rust core and re-exported here as pyarrow schemas."""

from __future__ import annotations

import time

import pyarrow as pa

from triplum import _core

TS_MAX: int = _core.ts_max()


def _schema(name: str, dims: int | None = None) -> pa.Schema:
    return pa.schema(_core.schema(name, dims))


DOCUMENTS = _schema("documents")
DOCUMENT_GRANTS = _schema("document_grants")
CHUNKS = _schema("chunks")
ENTITIES = _schema("entities")
FACTS = _schema("facts")
FACT_SUPPORT = _schema("fact_support")
MENTIONS = _schema("mentions")


def chunk_embeddings(dims: int) -> pa.Schema:
    return _schema("chunk_embeddings", dims)


def now_us() -> int:
    """Current UTC time in microseconds since the epoch."""
    return time.time_ns() // 1000
