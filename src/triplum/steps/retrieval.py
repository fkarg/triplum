import re
from abc import abstractmethod
from typing import Protocol

import bm25s
from pydantic import ConfigDict, Field

from triplum.datatype import FingerprintedDataModel, RetrievalHit, Viewer
from triplum.store.protocols import RecordStore
from triplum.utils.fingerprint import FingerprintedComputationMixin

# operations of form (query, viewer) -> ranked chunks


class Retriever(Protocol):
    """Find the chunks that best answer a query, among those `viewer` may read."""

    @abstractmethod
    def __call__(self, query: str, /, *, viewer: Viewer, k: int) -> list[RetrievalHit]:
        """At most `k` hits, best first; only chunks of sources `viewer` may read."""
        ...


class BM25Settings(FingerprintedDataModel):
    """Tokenization and Lucene BM25 scoring of one configuration; every field can be changed.

    Tokens are the whole matches of `token_pattern` in the (optionally lowercased) text, for
    chunks and queries alike; capture groups do not change them and empty matches are skipped.
    """

    model_config = ConfigDict(frozen=True)

    k1: float = Field(ge=0)  # bounds keep every matching chunk's score positive
    b: float = Field(ge=0, le=1)
    token_pattern: str = r"\w+"
    lowercase: bool = True


HIPPORAG1 = BM25Settings(k1=1.2, b=0.75)
"""Approximates HippoRAG 1's Elasticsearch `standard` analyzer: lowercased words, no stopwords."""

BM25S_DEFAULT = BM25Settings(k1=1.5, b=0.75, token_pattern=r"(?u)\b\w\w+\b")
"""bm25s defaults: its default token pattern drops one-character tokens."""


class BM25(Retriever, FingerprintedComputationMixin):
    """Lexical retrieval over a snapshot of a store's chunks, scored by bm25s.

    Indexes the current chunks of every source `viewer` may read at construction. Those chunks
    are the term-statistics scope: scores of visible chunks depend on indexed chunks a query's
    viewer may not read. Later writes do not reach the index; build a new one.

    Each call ranks only indexed chunks whose source its own viewer may read, before choosing
    the top `k`. Hits share at least one token with the query, so there may be fewer than `k`.
    Equal scores are ordered by `(source_id, ordinal)`.
    """

    def __init__(
        self, store: RecordStore, /, *, viewer: Viewer, settings: BM25Settings = HIPPORAG1
    ) -> None:
        self._store = store
        self.settings = settings
        self._pattern = re.compile(settings.token_pattern)
        chunks = [
            chunk
            for source in store.sources(viewer=viewer)
            for chunk in store.chunks(source.id, viewer=viewer)
        ]
        self._chunks = sorted(chunks, key=lambda c: (c.source_id, c.ordinal))
        tokens = [self._tokens(chunk.text) for chunk in self._chunks]
        self._index: bm25s.BM25 | None = None
        if any(tokens):  # bm25s cannot index a corpus without tokens
            self._index = bm25s.BM25(k1=settings.k1, b=settings.b, method="lucene")
            self._index.index(tokens, show_progress=False)

    def fingerprint_config(self) -> dict[str, object]:
        return {"settings": self.settings}

    def _tokens(self, text: str) -> list[str]:
        text = text.lower() if self.settings.lowercase else text
        return [m.group() for m in self._pattern.finditer(text) if m.group()]

    def __call__(self, query: str, /, *, viewer: Viewer, k: int) -> list[RetrievalHit]:
        if k < 1:
            raise ValueError("k must be at least 1")
        if self._index is None:
            return []
        known = [t for t in self._tokens(query) if t in self._index.vocab_dict]
        if not known:  # bm25s raises on an empty query
            return []
        scores = self._index.get_scores(known)
        visible = {source.id for source in self._store.sources(viewer=viewer)}
        # Lucene idf is positive, so a chunk sharing a query token scores above zero.
        rows = [i for i, c in enumerate(self._chunks) if c.source_id in visible and scores[i] > 0]
        rows.sort(key=lambda i: -scores[i])  # stable: ties keep (source_id, ordinal) order
        return [RetrievalHit(chunk=self._chunks[i], score=float(scores[i])) for i in rows[:k]]
