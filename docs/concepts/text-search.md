# Store-managed text search

A store can build a text index from one [collection](collection.md) and search it for ranked
[chunks](chunk.md). This keeps index construction beside the records and lets a backend use its
own search engine. [`TextSearchStore`][triplum.store.protocols.TextSearchStore] describes this
capability independently of record storage.

## Build, then search

```python
from triplum.datatype import Collection, Source
from triplum.steps.chunking import WholeText
from triplum.store import MemoryStore

collection = Collection(name="Shop policies")
source = Source(
    collection_id=collection.id,
    origin="returns.md",
    text="Returns are accepted within 30 days.",
)
store = MemoryStore()
store.add_sources([source], allow=["public"])
store.replace_chunks(source.id, WholeText()(source))
store.index_text(collection.id)

hits = store.search_text("returns", collection_id=collection.id, k=5)
print([(hit.chunk.origin, hit.chunk.text) for hit in hits])

store.replace_chunks(source.id, [])
print(len(store.search_text("returns", collection_id=collection.id, k=5)))
store.index_text(collection.id)
print(store.search_text("returns", collection_id=collection.id, k=5))
```

```text
[('returns.md', 'Returns are accepted within 30 days.')]
1
[]
```

`index_text(collection_id)` builds a **snapshot** of the collection's current chunks. Added
sources and replaced chunks become searchable only after another successful build. Until then,
hits retain the indexed chunks, even when those chunks are no longer current in the store.
A failed rebuild preserves the previous index.

Searching before a collection's first successful build raises `KeyError`. Building an empty
collection succeeds and its searches return `[]`. A `k` below 1 raises `ValueError`.

## Use the Retriever call shape

Bind the collection with `partial` to obtain the same call shape as a
[`Retriever`][triplum.steps.retrieval.Retriever]:

```python
from functools import partial

search = partial(store.search_text, collection_id=collection.id)
hits = search("returns", k=5)
```

The result is the usual `list[RetrievalHit]`, ready for [retrieval recall](recall.md).
Backend settings alone do not identify the indexed contents; run identity for these searches
is not defined yet, so do not cache search calls.

## Choose an implementation

| Store | Text index | Lifetime |
| --- | --- | --- |
| `MemoryStore()` | bm25s, using `HIPPORAG1` settings | In this store instance |
| `SQLAlchemyStore(url)` | The same bm25s implementation, reading records from SQL | In this store instance; rebuild after reopening |
| `SQLiteStore(url)` | Native SQLite FTS5 | Persisted with the database |

The generic SQL path reads the collection's chunks into Python. It works without native database
text-search extensions, including for PostgreSQL. Pass `text=BM25Settings(...)` to
`MemoryStore` or `SQLAlchemyStore` to choose other [BM25 settings](retrieval.md#settings-and-presets).
The standalone [`BM25`][triplum.steps.retrieval.BM25] remains available as the reference retriever
over any `RecordStore`.

### Native SQLite

`SQLiteStore` shares the SQL record tables with `SQLAlchemyStore` and builds one FTS5 table per
collection. Use it with a file URL to keep the index after closing:

```python
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from triplum.datatype import Collection, Source
from triplum.steps.chunking import WholeText
from triplum.store import SQLiteStore

collection = Collection(name="Policies")
source = Source(collection_id=collection.id, origin="returns.md", text="Returns within 30 days.")
with TemporaryDirectory() as directory:
    url = f"sqlite:///{Path(directory) / 'records.db'}"
    with closing(SQLiteStore(url)) as sqlite:
        sqlite.add_sources([source], allow=["public"])
        sqlite.replace_chunks(source.id, WholeText()(source))
        sqlite.index_text(collection.id)
    with closing(SQLiteStore(url)) as reopened:
        print(
            [
                hit.chunk.origin
                for hit in reopened.search_text("returns", collection_id=collection.id, k=5)
            ]
        )
```

```text
['returns.md']
```

[`FTS5Settings`][triplum.store.sql.sqlite.FTS5Settings] configures native search through
`SQLiteStore(url, text=FTS5Settings(...))`:

- `tokenizer` is the FTS5 tokenizer declaration. The default is
  `unicode61 remove_diacritics 0 tokenchars '_'`: it retains accents and underscores.
- `token_pattern` extracts whole, nonempty query terms, `\w+` by default. Each term is quoted
  literally, then combined with `OR`. Search operators in user text do not become FTS5 syntax.
  Indexed text is tokenized by FTS5, which also tokenizes each quoted query term. A custom
  pattern that selects a NUL-containing term raises `ValueError`.

[FTS5 fixes BM25's `k1` to 1.2 and `b` to 0.75](https://sqlite.org/fts5.html#the_bm25_function);
these are not settings on this backend. Its
tokenization and scoring differ from bm25s, so treat it as a separate technique when comparing
results. Native scores are converted to higher-is-better.

The build records its settings. Reopening with different settings raises `ValueError` on search
until `index_text` rebuilds the collection. Reopening with equal settings can search immediately.

## Collection and viewer scope

Each index contains one collection. Other collections change neither its results nor its scores.
Only chunk text is searchable; record ids, offsets and origins are payload, not indexed terms.
Hits rank by score, with ties ordered by `(source_id, ordinal)`.

`search_text` accepts an optional [Viewer](../infrastructure/store.md#who-may-read). Without one,
access is not filtered. Given one, only readable sources can supply hits, and filtering happens
before choosing the top `k`. An empty viewer sees no hits. Term statistics still come from all
indexed chunks of the collection, including chunks the viewer cannot read.

Next: [Retrieval recall](recall.md), scoring ranked hits against gold evidence.
