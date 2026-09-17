"""An extractor that returns the spans and claims it was given, for tests of everything
downstream of an extractor."""

from __future__ import annotations

import polars as pl

from triplum.extract.protocol import CLAIM_SCHEMA, SPAN_SCHEMA, ExtractorSpec


class FakeExtractor:
    seed_sensitive = False

    def __init__(self, spans: list[tuple], claims: list[tuple], version: str = "1") -> None:
        self.spans = pl.DataFrame(spans, schema=SPAN_SCHEMA, orient="row")
        self.claims = pl.DataFrame(claims, schema=CLAIM_SCHEMA, orient="row")
        self.spec = ExtractorSpec(name="fake", version=version)
        self.calls = 0

    def run(self, chunks: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
        self.calls += 1
        ids = chunks["id"].to_list()
        return (
            self.spans.filter(pl.col("chunk_id").is_in(ids)),
            self.claims.filter(pl.col("chunk_id").is_in(ids)),
        )
