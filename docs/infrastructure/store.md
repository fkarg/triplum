# Store

A **store** keeps the records a pipeline produces, so you can read them back later or in another
process. Today the store holds [sources](../concepts/source.md), who may read each of them, and
their [chunks](../concepts/chunk.md). Vectors, files and graph data are not stored yet.

There is one contract, [`RecordStore`][triplum.store.protocols.RecordStore], and two
implementations:

- [`MemoryStore`][triplum.store.memory.MemoryStore] keeps records in Python dictionaries.
- [`SQLAlchemyStore`][triplum.store.sql.generic.SQLAlchemyStore] keeps them in a relational
  database through [SQLModel](https://sqlmodel.tiangolo.com/) (which is built on SQLAlchemy). By
  default it uses SQLite, which ships with Python and needs no server.

The contract and both implementations, `RecordStore`, `MemoryStore` and `SQLAlchemyStore`, are
importable from `triplum.store`. `SQLAlchemyStore` uses SQLAlchemy for database
access; only SQLite is covered by triplum's tests. Backend-specific stores (for
SQLite or PostgreSQL) are planned where database-specific SQL is faster; they will share its
tables, [`SourceRow`][triplum.store.sql.tables.SourceRow],
[`SourceAccessRow`][triplum.store.sql.tables.SourceAccessRow] and
[`ChunkRow`][triplum.store.sql.tables.ChunkRow] in `triplum.store.sql.tables`.

A [`CollectionRow`][triplum.store.sql.tables.CollectionRow] mapping is also available, with the
`id` and `name` of a [collection](../concepts/collection.md). Source and chunk rows store their
`collection_id`, but `SQLAlchemyStore` does not yet create the collection table or manage
collection records. Listing sources takes a collection id and returns only that collection's
sources; an id no source carries gives none. There is no listing across all collections.

Every read takes a [`Viewer`][triplum.datatype.viewer.Viewer] and returns only what it may read;
see [Who may read](#who-may-read). Reads take no temporal view and do not reconstruct historical
state. Changing a document's text gives a new source ID; the stores keep no link
between the two versions and no history.

## Example

This chunks one source, writes both to a SQLite file, and reads them back through a second store
opened on the same file, as a later run of your program would. A later run reproduces the same
record IDs only if it reuses the same collection `id`.

```python
from triplum.datatype import Collection, Source, Viewer
from triplum.steps.chunking import FixedSize
from triplum.store import SQLAlchemyStore

collection = Collection(name="Research notes")
source = Source(
    collection_id=collection.id,
    origin="notes/returns.md",
    text="Returns are accepted within 30 days.",
)
chunks = FixedSize(20)(source)

store = SQLAlchemyStore("sqlite:///records.db")
store.add_sources([source], allow=["public"])
store.replace_chunks(source.id, chunks)
store.close()

reader = Viewer(principals=frozenset({"public"}))
reopened = SQLAlchemyStore("sqlite:///records.db")
print(reopened.source(source.id, viewer=reader) == source)
for chunk in reopened.chunks(source.id, viewer=reader):
    print(chunk.ordinal, chunk.start, repr(chunk.text))
reopened.close()
```

Output:

```text
True
0 0 'Returns are accepted'
1 20 ' within 30 days.'
```

1. `FixedSize(20)(source)` splits the source into chunks. Each chunk's `source_id` is the
   source's `id`, which is how the store connects them.
2. `SQLAlchemyStore("sqlite:///records.db")` opens (or creates) the SQLite file `records.db` in the
   current working directory and creates its `source`, `source_access` and `chunk` tables if they
   are missing.
3. `add_sources(..., allow=["public"])` stores the source and lets the principal `"public"` read
   it. It must come before `replace_chunks`: chunks can only be given to a stored source.
   `replace_chunks(source.id, chunks)` makes `chunks` the source's complete chunk list.
4. `close()` releases the store's database connections once you are done with it. Only
   `SQLAlchemyStore` has it: `close()` is not part of `RecordStore`, and `MemoryStore` has none.
5. `Viewer(principals=...)` says who is reading. `SQLAlchemyStore(...)` on the same URL sees
   everything the first store committed. `source(id, viewer=...)` returns the source with that
   `id`; `chunks(source_id, viewer=...)` returns its chunks ordered by `ordinal`.

## Who may read

Each `add_sources` call grants read access to the principals in `allow`: plain strings naming a
user, a group or anything else your application chooses. A `Viewer` holds the principals a reader
acts as. A source is visible to a viewer when the two sets share at least one principal.

Access is enforced only for reads through triplum. A SQLite database file holds every source's
text in plain form, readable by anyone who can read the file, so restrict the file's permissions
for confidential corpora.

```python
from triplum.datatype import Collection, Source, Viewer
from triplum.store import MemoryStore

collection = Collection(name="Research notes")
public = Source(collection_id=collection.id, origin="faq.md", text="Shipping is free.")
internal = Source(collection_id=collection.id, origin="margins.md", text="Margin is 40%.")

store = MemoryStore()
store.add_sources([public], allow=["public"])
store.add_sources([internal], allow=["finance"])

anyone = Viewer(principals=frozenset({"public"}))
analyst = Viewer(principals=frozenset({"public", "finance"}))
print(sorted(s.origin for s in store.sources(collection_id=collection.id, viewer=anyone)))
print(sorted(s.origin for s in store.sources(collection_id=collection.id, viewer=analyst)))
try:
    store.source(internal.id, viewer=anyone)
except KeyError:
    print("KeyError, as for a missing source")
```

Output:

```text
['faq.md']
['faq.md', 'margins.md']
KeyError, as for a missing source
```

- `"public"` is an ordinary principal with no special meaning: a viewer sees public sources only
  if it names `"public"`. A viewer without principals sees nothing, and a source added with an
  empty `allow` is readable by nobody.
- A source the viewer may not read behaves exactly like a missing one: `source` and `chunks`
  raise the same `KeyError(id)`, and `sources` leaves it out. Reads therefore do not reveal that
  it exists.
- Chunks are readable with their source; they have no access of their own.
- Sources with different access go in separate `add_sources` calls. Access is kept by the store,
  keyed by source `id` (in SQL, the `source_access` table); it is not part of `Source`, its `id`
  or its fingerprint.
- Writes are trusted ingestion: `add_sources` and `replace_chunks` take no viewer, and their
  conflict errors name stored ids. The store does not authorize writers.
- `allow` must be a collection of principals; a bare string raises `TypeError` rather than
  allowing its single characters.
- Principals match exactly on SQLite (the tested backend) and PostgreSQL. A database whose
  collation ignores case or trailing spaces (common MySQL and MSSQL defaults) would match more
  loosely than `MemoryStore`.
- Access cannot be revoked or changed yet, and it has no time axis.

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
  `CREATE TABLE` for its own `source`, `source_access` and `chunk` tables if they do not exist
  yet, and for no other table. Existing tables and rows are left alone; there are no migrations,
  so a table created by an older layout is not updated. A database created before source access
  and `external_id` were added is not upgraded; recreate it.
- **The in-memory default is shared across threads.** `SQLAlchemyStore()` keeps its in-memory
  SQLite database on a single connection, so every thread using that store instance sees the same
  records. Another store instance, even another `SQLAlchemyStore()`, gets its own empty database,
  and `close()` discards it. `MemoryStore` is not safe for concurrent writers.
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

- **Records are keyed by `id`.** Every source and chunk carries an `id`, a deterministic
  [UUIDv8](https://www.rfc-editor.org/rfc/rfc9562#name-uuid-version-8) derived from its content
  (see [Source](../concepts/source.md) and [Chunk](../concepts/chunk.md)). Re-adding a record
  produced the same way therefore writes an equal record, and the store keeps one copy.
- **Sources are only ever added.** `add_sources` stores each source that is not stored yet;
  re-adding an equal source with the same `allow` does nothing. `ValueError` is raised for a
  stored source re-added with a different `allow`, and for a different source with the `id` of a
  stored source or of another source in the same batch. Sources are never replaced or removed.
- **External ids are unique within a collection.** A source whose `external_id` is already held
  by another source of the same collection, stored or earlier in the batch, raises `ValueError`.
  Sources without an `external_id` never conflict, and other collections may reuse it.
- **Changed content is a new record.** A source with different text, origin or collection has a
  different `id` and is stored alongside the old one. Neither the old source nor its chunks are
  removed.
- **Each source has one current chunk list.** `replace_chunks(source_id, chunks)` makes the given
  chunks, in order, the source's complete chunk list and removes its previous chunks; an empty
  list leaves the source without chunks. To rechunk with another chunker, replace the source's
  chunks with the new result.
- **Chunks must fit their source.** `replace_chunks` raises `KeyError` if the source is not
  stored, and `ValueError` unless every chunk names that source and its `collection_id` and
  `origin`, has its list position as `ordinal`, and is an exact slice of the source text
  (`source.text[chunk.start : chunk.start + len(chunk.text)] == chunk.text`). A different chunk
  with the `id` of a stored chunk also raises `ValueError`.
- **A failed write changes nothing.** Each write checks its whole input before storing any of
  it, so when it raises, including when the iterable you pass raises partway, the store is
  unchanged. `SQLAlchemyStore` performs each write in one transaction.
- **One writer at a time.** These guarantees assume writes are not concurrent. Two
  `SQLAlchemyStore` writers adding the same new source at once may surface the database's
  integrity error instead of the documented `ValueError` or no-op.
- **Reads**: `source(id, viewer=...)` raises `KeyError` for an unknown or unreadable id.
  `sources(collection_id=..., viewer=...)` yields the sources of that collection the viewer may
  read, in no particular order; an unknown collection gives none.
  `chunks(source_id, viewer=...)` returns the current chunks ordered by `ordinal`, empty if the
  source has none, and raises `KeyError` if the source is unknown or unreadable.
- **Round trip**: a record read back equals the one you stored. `SQLAlchemyStore` rebuilds each
  record from its row and checks the stored `id` against its fields; a row edited outside the
  store so that they no longer match raises a Pydantic `ValidationError` on read.

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
- [`Viewer`][triplum.datatype.viewer.Viewer]
- [`SourceRow`][triplum.store.sql.tables.SourceRow],
  [`SourceAccessRow`][triplum.store.sql.tables.SourceAccessRow],
  [`ChunkRow`][triplum.store.sql.tables.ChunkRow]

Next: [Fingerprints](fingerprints.md).
