# Store

A **store** keeps the records a pipeline produces, so you can read them back later or in another
process. Today the store holds [sources](../concepts/source.md) and their
[chunks](../concepts/chunk.md). Vectors, files and graph data are not stored yet.

There is one contract, [`RecordStore`][triplum.store.protocols.RecordStore], and two
implementations:

- [`MemoryStore`][triplum.store.memory.MemoryStore] keeps records in Python dictionaries.
- [`SQLAlchemyStore`][triplum.store.sql.generic.SQLAlchemyStore] keeps them in a relational
  database through [SQLModel](https://sqlmodel.tiangolo.com/) (which is built on SQLAlchemy). By
  default it uses SQLite, which ships with Python and needs no server.

All three are importable from `triplum.store`. `SQLAlchemyStore` uses SQLAlchemy for database
access; only SQLite is covered by triplum's tests. Backend-specific stores (for
SQLite or PostgreSQL) are planned where database-specific SQL is faster; they will share its
tables, [`SourceRow`][triplum.store.sql.tables.SourceRow] and
[`ChunkRow`][triplum.store.sql.tables.ChunkRow] in `triplum.store.sql.tables`.

A [`CollectionRow`][triplum.store.sql.tables.CollectionRow] mapping is also available, with the
`id` and `name` of a [collection](../concepts/collection.md). `SQLAlchemyStore` does not yet create
its table or manage collection records; `RecordStore` has no collection methods. Source and chunk
rows do not yet carry collection membership.

The current read methods take record IDs, with no Viewer or temporal-view argument. They do not
filter access by principal or reconstruct historical state. Those are requirements of the
[intended retrieval flow](../flow.md#2-retrieval-select-evidence-for-a-question), not guarantees
of these stores. Adding a record with an existing ID replaces it rather than preserving history.

## Example

This chunks one source, writes both to a SQLite file, and reads them back through a second store
opened on the same file, as a later run of your program would.

```python
from triplum.datatype import Source
from triplum.steps.chunking import FixedSize
from triplum.store import SQLAlchemyStore

source = Source(origin="notes/returns.md", text="Returns are accepted within 30 days.")
chunks = FixedSize(20)(source)

store = SQLAlchemyStore("sqlite:///records.db")
store.add_sources([source])
store.add_chunks(chunks)

reopened = SQLAlchemyStore("sqlite:///records.db")
print(reopened.source(source.id) == source)
for chunk in reopened.chunks(source.id):
    print(chunk.start, repr(chunk.text))
```

Output:

```text
True
0 'Returns are accepted'
20 ' within 30 days.'
```

1. `FixedSize(20)(source)` splits the source into chunks. Each chunk's `source_id` is the
   source's `id`, which is how the store connects them.
2. `SQLAlchemyStore("sqlite:///records.db")` opens (or creates) the SQLite file `records.db` in the
   current working directory and creates its `source` and `chunk` tables if they are missing.
3. `add_sources` must come before `add_chunks`: a chunk whose source is not stored is rejected.
4. `SQLAlchemyStore(...)` on the same URL sees everything the first store committed. `source(id)`
   returns the source with that `id`; `chunks(source_id)` returns its chunks ordered by `start`.

## Choosing where records go

| You write | What you get |
| --- | --- |
| `MemoryStore()` | Python dictionaries. Gone when the process ends. |
| `SQLAlchemyStore()` | An in-memory SQLite database. Gone when the process ends, and private to this store instance. |
| `SQLAlchemyStore("sqlite:///records.db")` | The file `records.db`, relative to the current working directory (three slashes). |
| `SQLAlchemyStore("sqlite:////data/triplum/records.db")` | The absolute path `/data/triplum/records.db` (four slashes: three for the URL, one for the path). |
| `SQLAlchemyStore("postgresql+psycopg://user:password@host/dbname")` | A PostgreSQL database; see below. |

Practical details:

- **The file is created for you, the folder is not.** SQLite creates `records.db` if it does not
  exist, but the directory it lives in must already exist.
- **Tables are created when the store is constructed.** `SQLAlchemyStore(url)` runs
  `CREATE TABLE` for its own `source` and `chunk` tables if they do not exist yet, and for no
  other table. Existing tables and rows are left alone; there are no migrations, so a table
  created by an older layout is not updated.
- **The in-memory default is shared across threads.** `SQLAlchemyStore()` keeps its in-memory
  SQLite database on a single connection, so every thread using that store instance sees the same
  records. Another store instance, even another `SQLAlchemyStore()`, gets its own empty database.
- **To start over**, delete the SQLite file (`rm records.db`). There is no method that clears a
  store.
- **Inspecting the data**: the SQLite file is an ordinary database. Any SQLite client can open it,
  for example `sqlite3 records.db "select origin, length(text) from source"` if the `sqlite3`
  command-line tool is installed.

### PostgreSQL and other databases

`SQLAlchemyStore` hands the URL to SQLAlchemy's `create_engine` unchanged, so any database SQLAlchemy
supports can be named. SQLAlchemy does not include database drivers other than SQLite's, and
triplum does not depend on one. For PostgreSQL, install a driver into the same environment and
name it in the URL:

- `uv add psycopg` (psycopg 3), then `postgresql+psycopg://user:password@host/dbname`.
- `uv add psycopg2`, then `postgresql+psycopg2://user:password@host/dbname`. A bare
  `postgresql://` URL also selects psycopg2, SQLAlchemy's default PostgreSQL driver.

The database itself must already exist; `SQLAlchemyStore` creates tables, not databases. Only SQLite is
covered by triplum's tests. PostgreSQL is expected to work because the tables use only portable
column types, but this has not been verified.

## What it guarantees

- **Records are keyed by `id`.** Every source and chunk carries an `id`, a
  [UUIDv7](https://www.rfc-editor.org/rfc/rfc9562#name-uuid-version-7) generated when the record
  is created. It is not derived from the content: two sources with identical text get different
  ids and are stored as two records. Their [fingerprints](fingerprints.md) are equal, which is
  how you detect such duplicates.
- **Adding an `id` that is already stored replaces the record.** Chunks stored for a replaced
  source are not removed.
- **A chunk needs its source.** If any chunk in `add_chunks` refers to a source that is not
  stored, `add_chunks` raises `KeyError` and stores none of the batch.
- **Reads**: `source(id)` raises `KeyError` for an unknown id. `sources()` yields every source in
  no particular order. `chunks(source_id)` returns a list ordered by `start`, empty if the source
  has no chunks.
- **Round trip**: a record read back equals the one you stored, including whether a chunk's `origin`
  was a `Path` or a `str`.

## Capabilities, not one big store

Storage is split by capability: one Protocol for each kind of thing kept. `RecordStore` covers
records; vectors, blobs (files) and graph data will each get their own Protocol when they are
built. A single backend may implement several of them, and a pipeline asks only for the
capabilities it uses. Code that only reads chunks therefore accepts a `RecordStore` and works with
either implementation above, or with your own class that has the same methods.

The store is also separate from the [cache](cache.md). The cache remembers results of
computations so they need not be repeated; the store holds the records you decided to keep.

## Reference

- [`RecordStore`][triplum.store.protocols.RecordStore]
- [`MemoryStore`][triplum.store.memory.MemoryStore]
- [`SQLAlchemyStore`][triplum.store.sql.generic.SQLAlchemyStore]
- [`SourceRow`][triplum.store.sql.tables.SourceRow], [`ChunkRow`][triplum.store.sql.tables.ChunkRow]

Next: [Fingerprints](fingerprints.md).
