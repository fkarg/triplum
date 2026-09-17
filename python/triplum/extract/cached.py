"""Per-chunk cache around any extractor, keyed on (extractor spec hash, chunk text)."""

from __future__ import annotations

import polars as pl

from triplum.cache import Cache, content_key
from triplum.extract.protocol import CLAIM_SCHEMA, SPAN_SCHEMA, Extractor


class CachedExtractor:
    def __init__(self, inner: Extractor, cache: Cache) -> None:
        self.inner = inner
        self.cache = cache
        self.spec = inner.spec
        self.misses = 0

    def run(self, chunks: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
        ids = chunks["id"].to_list()
        texts = chunks["text"].to_list()
        keys = [content_key("extract", {"spec": self.spec.hash(), "text": t}) for t in texts]
        rows: dict[int, dict] = {}
        missing = []
        for i, k in enumerate(keys):
            hit = self.cache.get_json(k)
            if hit is None:
                missing.append(i)
            else:
                rows[i] = hit
        if missing:
            self.misses += len(missing)
            spans, claims = self.inner.run(chunks[missing])
            for i in missing:
                cid = ids[i]
                rows[i] = {
                    "spans": spans.filter(pl.col("chunk_id") == cid).drop("chunk_id").rows(),
                    "claims": claims.filter(pl.col("chunk_id") == cid).drop("chunk_id").rows(),
                }
                self.cache.put_json(keys[i], rows[i])
        span_rows = [(ids[i], *r) for i in range(len(ids)) for r in rows[i]["spans"]]
        claim_rows = [(ids[i], *r) for i in range(len(ids)) for r in rows[i]["claims"]]
        return (
            pl.DataFrame(span_rows, schema=SPAN_SCHEMA, orient="row"),
            pl.DataFrame(claim_rows, schema=CLAIM_SCHEMA, orient="row"),
        )
