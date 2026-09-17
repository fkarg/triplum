"""Wrap any LLM with the disk cache. A hit is an exact replay and is marked as such."""

from __future__ import annotations

from dataclasses import asdict

from triplum.cache import Cache
from triplum.llm.protocol import DEFAULT_PARAMS, LLM, Completion, Usage, request_hash


class CachedLLM:
    def __init__(self, inner: LLM, cache: Cache) -> None:
        self.inner = inner
        self.cache = cache
        self.adapter = inner.adapter
        self.model = inner.model
        self.seed_sensitive = inner.seed_sensitive

    def complete(self, messages, *, schema=None, params=DEFAULT_PARAMS) -> Completion:
        key = request_hash(self.adapter, self.model, messages, schema, params)
        hit = self.cache.get_json(key)
        if hit is not None:
            return Completion(
                text=hit["text"],
                parsed=hit["parsed"],
                usage=Usage(**hit["usage"]),
                model=hit["model"],
                request_hash=key,
                cached=True,
                raw=hit.get("raw", {}),
            )
        c = self.inner.complete(messages, schema=schema, params=params)
        self.cache.put_json(
            key,
            {
                "text": c.text,
                "parsed": c.parsed,
                "usage": asdict(c.usage),
                "model": c.model,
                "raw": c.raw,
            },
        )
        return c
