# Store-managed text search (proposal, under owner review)

Status: **draft P16**, not approved. Owner answers it builds on (2026-11-08, [storage
questions](../plans/questions/storage.md)): ST1 both, primarily storage; ST2 SQLAlchemy abstraction
where reasonable, not more; ST3 "the same technique" ≈ within a few points on reproduction; ST4
no native index object competing with `Retriever`; ST5 memory, SQLite, Postgres first. Policies:
collections are corpus boundaries; easy generic path plus override points; keep reference
implementations; collection isolation via tables for clean benchmarks; Viewer optional (P15).

## Declarations

```python
# src/triplum/store/protocols.py
class TextSearchStore(RecordStore, Protocol):
    """A store that ranks chunk text natively, per collection."""

    @abstractmethod
    def index_text(self, collection_id: UUID, /) -> None:
        """(Re)build the collection's text index from its current chunks.

        Searches see the chunks as of the last call; later writes need another call.
        """

    @abstractmethod
    def search_text(
        self, query: str, /, *, collection_id: UUID, viewer: Viewer | None = None, k: int
    ) -> list[RetrievalHit]:
        """At most `k` chunks of the collection, best first, as indexed by `index_text`.

        Statistics come from that collection's index alone. A given viewer filters before
        ranking. `KeyError` if the collection has no text index; `ValueError` if `k < 1`.
        Ties are ordered by `(source_id, ordinal)`; scores are higher-is-better.
        """
```

A search is a `Retriever` without any new class: `partial(store.search_text,
collection_id=c)` has the `Retriever` call shape and can be passed to fusion or evaluation.

Implementations, each configured in its constructor (settings belong to the store's identity):

- `MemoryStore(text=BM25Settings(...))`: bm25s, as `BM25` does today (the HippoRAG reference
  scoring), one in-memory index per collection.
- `SQLiteStore(url, text=FTS5Settings(...))`, a subclass of `SQLAlchemyStore`: one FTS5 table per
  collection (`chunk_text_<collection hex>`), holding chunk id, source id, ordinal, start and
  text, so hits carry the indexed payload. FTS5 fixes k1 = 1.2, b = 0.75 (the `HIPPORAG1`
  values); `FTS5Settings` covers what FTS5 actually exposes (tokenizer and its options, e.g.
  `unicode61 remove_diacritics 0`). Queries are matched as literal tokens (no FTS5 query syntax).
  Native scores are negated to higher-is-better.
- `SQLAlchemyStore` (generic, including Postgres): records only, no `TextSearchStore`. Postgres
  has no native BM25; an extension-backed `PostgresStore` (pg_search, pg_textsearch,
  VectorChord-bm25) is a later candidate.
- `BM25` over any `RecordStore` stays as the step-owned reference (unchanged).

## Guarantees and checks

- Collection isolation: another collection's chunks change neither scores nor order (one index or
  table per collection; a shared FTS5 table with a collection filter fails this, reproduced).
- Snapshot semantics: `search_text` returns the chunks as indexed, even after `replace_chunks`.
- Agreement (ST3): on the 20-question fixture, SQLite FTS5 R@2 and R@5 are within 0.05 of the
  `BM25`/bm25s reference with `HIPPORAG1`; the observed difference is recorded either way. It is a
  separate technique ("BM25 via SQLite FTS5"), not a replacement.
- Tests on both memory and SQLite: isolation, snapshot, viewer filtering before top `k`, ties,
  literal queries with FTS5 operators (`AND`, `"`, `*`), `KeyError` before indexing.

## Open

- Postgres in tests: a local server, a container, or skipped without one (AGENTS forbids skipped
  CLI tests, not database tests); which extension first.
- Run identity: store class, text settings, collection id and indexed-content digest (BE6).
- Whether `index_text` should also run automatically after writes (live) for some stores.
- RRF over `search_text` results in Python first; an SQL version later where measured.
