"""Canonical Arrow schemas, owned by the Rust core and re-exported here as pyarrow schemas."""

from __future__ import annotations

import time

import polars as pl
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


def polars_schema(arrow: pa.Schema) -> pl.Schema:
    """The Polars view of a canonical schema for frames exchanged between modules. Column names,
    order and non-time types come from the Arrow definition; timestamp columns are the integer
    UTC microseconds D2 specifies for interchange (the physical Arrow representation), so frames
    built from Python ints and SQLite rows need no conversion."""
    view = pl.DataFrame(pa.Table.from_pylist([], schema=arrow)).schema
    return pl.Schema(
        {
            name: pl.Int64 if isinstance(dtype, pl.Datetime) else dtype
            for name, dtype in view.items()
        }
    )


def now_us() -> int:
    """Current UTC time in microseconds since the epoch."""
    return time.time_ns() // 1000
