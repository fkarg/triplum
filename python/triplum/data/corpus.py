"""Canonical corpus batches at the ingestion boundary, independent of evaluation targets."""

from typing import NamedTuple

import polars as pl

from triplum.data import schema

DOC_SCHEMA = schema.polars_schema(schema.DOCUMENTS)
GRANT_SCHEMA = schema.polars_schema(schema.DOCUMENT_GRANTS)
CHUNK_SCHEMA = schema.polars_schema(schema.CHUNKS)


class CorpusBatch(NamedTuple):
    """Documents, their grants and chunks in the canonical schemas.

    This is a batch value, not a dataset superclass. Sources may yield these directly,
    or a custom collator may construct them from source-specific records.
    """

    documents: pl.DataFrame
    grants: pl.DataFrame
    chunks: pl.DataFrame
