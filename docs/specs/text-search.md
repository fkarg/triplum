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
class TextSearchStore(Protocol):
    """Ranks chunk text per collection; a capability beside `RecordStore`, not a subtype."""

    @abstractmethod
    def index_text(self, collection_id: UUID, /) -> None:
        """(Re)build the collection's text index from its current chunks (a snapshot).

        Searches see the chunks as of the last successful call; later writes need another call.
        An empty collection builds an empty index. A failed rebuild keeps the previous index.
        """

    @abstractmethod
    def search_text(
        self, query: str, /, *, collection_id: UUID, viewer: Viewer | None = None, k: int
    ) -> list[RetrievalHit]:
        """At most `k` chunks of the collection, best first, as indexed by `index_text`.

        Statistics come from that collection's index alone. A given viewer filters before
        ranking. `KeyError` before the collection's first successful build; `ValueError` if
        `k < 1`. Hits carry the chunks as indexed, also after `replace_chunks`.
        Ties are ordered by `(source_id, ordinal)`; scores are higher-is-better.
        """
```

A search is a `Retriever` without any new class: `partial(store.search_text,
collection_id=c)` has the `Retriever` call shape and can be passed to fusion or evaluation.

Implementations, each configured in its constructor (settings belong to the store's identity):

- Generic path, `MemoryStore` and `SQLAlchemyStore` (so also Postgres):
  `text=BM25Settings(...)`, default `HIPPORAG1`; each keeps one private `BM25` reference
  (bm25s) per built collection, reusing today's scoring code. This is the generic default: it
  materializes the collection in Python, without native database search.
- `SQLiteStore(url, text=FTS5Settings(...))`, a subclass of `SQLAlchemyStore` overriding both
  methods natively: one FTS5 table per collection (`chunk_text_<collection hex>`); only `text` is
  indexed, chunk id, source id, ordinal and start are `UNINDEXED` payload (indexed metadata
  columns produce false matches, observed), and `origin` comes from the immutable source row. The
  effective build settings are stored with the table and checked before searching; a mismatch
  raises until `index_text` rebuilds (`CREATE ... IF NOT EXISTS` silently keeps an old
  tokenizer, observed). Rebuilds run in one transaction. FTS5 fixes k1 = 1.2, b = 0.75 (the `HIPPORAG1`
  values); `FTS5Settings` covers what FTS5 actually exposes (tokenizer and its options, e.g.
  `unicode61 remove_diacritics 0 tokenchars '_'` to match `\w+` more closely). Query: terms are
  extracted with the settings' pattern, each quoted as an FTS5 string, and joined with `OR`, so
  any shared term matches as in the reference (whole-query quoting means a phrase and scored R@2
  and R@5 of 0 on the fixture; implicit AND likewise; quoted terms with OR scored 0.550 / 0.750
  against the reference's 0.600 / 0.775, peer probe). A query without terms returns `[]`.
  Native scores are negated to higher-is-better; ties by source id, then numeric ordinal.
- An extension-backed native `PostgresStore` override (pg_search, pg_textsearch,
  VectorChord-bm25) is a later candidate; Postgres starts on the generic path.
- `BM25` over any `RecordStore` stays as the step-owned reference (unchanged).

## Guarantees and checks

- Collection isolation: another collection's chunks change neither scores nor order (one index or
  table per collection; a shared FTS5 table with a collection filter fails this, reproduced).
- Snapshot semantics: `search_text` returns the chunks as indexed, even after `replace_chunks`.
- Agreement (ST3): on the 20-question fixture, SQLite FTS5 R@2 and R@5 are within 0.05 of the
  `BM25`/bm25s reference with `HIPPORAG1`; the observed difference is recorded either way. It is a
  separate technique ("BM25 via SQLite FTS5"), not a replacement.
- Tests on memory, generic SQLAlchemy and native SQLite: isolation; snapshot (complete hit
  equality after rechunking); writes invisible until rebuild; rebuild to empty; failed rebuild
  keeps the old index; `KeyError` before the first build versus `[]` for a built empty index;
  `k < 1`; empty, punctuation-only, unknown and operator-looking queries (`AND`, `"`, `*`,
  `cat*`, `cat.dog`); one of several terms matching; viewer `None`, empty principals and a
  hidden best match, filtered before top `k`; ties; reopening with equal and changed settings.

## Review

Peer gpt-6.1-sol (2026-11-08, verdict challenges; ran FTS5 probes with SQLite 3.53.1 and the
fixture). Dispositions: generic SQLAlchemy path missing (ST2, ST5) → added, reusing `BM25`
privately; query semantics undefined, whole-query quoting scores 0 → OR of quoted terms with
measured fixture numbers; persisted tokenizer can silently differ → stored settings checked;
metadata columns matching text → `UNINDEXED`, origin from source rows; live refresh contradicted
the snapshot rule → removed, failed rebuilds keep the old index; missing boundary tests → added;
`TextSearchStore` inheriting `RecordStore` → independent capability. Not yet settled: the
agreement tolerance (R@2 sits exactly at 0.05 in the probe).

## Open

- Postgres in tests: the generic path must actually run against Postgres somewhere (a local
  server, a container, or CI only); which extension first for a native override.
- Run identity: store class, text settings, collection id and indexed-content digest (BE6).
- RRF over `search_text` results in Python first; an SQL version later where measured.
