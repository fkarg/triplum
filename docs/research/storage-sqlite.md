# SQLite as a knowledge-graph + retrieval store

Research note for `triplum`. Target: single-machine, Arrow-native, composable KG construction + GraphRAG retrieval + evaluation. SQLite is the first concrete backend behind the abstract store protocol; Oxigraph, LadybugDB and possibly DuckDB come later.

Date: 2026-09-16. Everything below is sourced; where a claim is a third-party benchmark or an inference rather than documented behaviour, it says so.


> **Reconciliation with [`design.md`](design.md) (2026-09-16).** This note and
> [`temporal-and-permissions.md`](temporal-and-permissions.md) were researched in parallel and the
> design record arbitrated where they differ. The DDL in section 7 is the engineering reference for
> FTS5, sqlite-vec, indexes and PRAGMAs, but four parts of it are superseded:
>
> - `fact_support` gains `group_no`: a fact is visible iff ANY support group is FULLY visible.
> - `document_principals` becomes system-versioned `document_grants(document_id, principal,
>   granted_at, revoked_at)`.
> - `entities` keeps only `id` and `canonical_id`; name, type and aliases are facts (so `alias_tri`
>   indexes alias facts, not an `entity_aliases` table). `facts` gains `invalidated_by_fact_id`
>   and `extractor`; embeddings move to `chunk_embeddings(chunk_id, embedding_spec, vector)`.
> - ACL is **not** a post-filter with over-fetch: the `vec0` partition key is a hash of the
>   document's principal set (coarse, sound pre-filter), the FTS5 table carries an `acl` token
>   column ANDed into the MATCH, and a materialised `fact_principal(principal, fact_id)` closure is
>   the exact check. Ranking is cut after the filter. Section 3's over-fetch discussion stays as the
>   record of why this was necessary.
>
> Kept as decided: sentinel `valid_to`, STRICT tables, JSONB metadata, partial live indexes,
> recursive CTEs only for bounded k-hop with in-memory CSR for PPR, WAL settings, DuckDB as an
> attached lens, uv-managed CPython for extension loading.

---

## 1. Full-text: FTS5

FTS5 is compiled into essentially every modern SQLite build and gives us BM25 for free.

**Tokenizers.** `unicode61` (default, diacritic-folding, `tokenchars`/`separators`/`categories` options), `ascii`, `porter` (a *wrapper* — `tokenize='porter unicode61 remove_diacritics 2'`), and `trigram`. Trigram is the one that matters for entity-alias matching: it makes `LIKE '%foo%'` and `GLOB` indexable, but only for substrings of **3+ characters**, and it is incompatible with `detail=none`/`detail=column` for tokens longer than 3 chars. `LIKE ... ESCAPE` cannot be optimised. ([FTS5 docs](https://www.sqlite.org/fts5.html))

**External content.** For triplum the right shape is `content='chunks', content_rowid='id'` — FTS5 stores only the inverted index, chunk text stays in a normal STRICT table, and triggers keep them in sync. The docs give the exact trigger trio (`AFTER INSERT` / `AFTER DELETE` with the `'delete'` command / `AFTER UPDATE` as delete-then-insert). The failure mode is silent: if the content table and index drift, MATCH queries return NULL columns rather than an error. Budget a periodic `INSERT INTO chunks_fts(chunks_fts, rank) VALUES('integrity-check', 1)` in the eval harness. Contentless (`content=''`) plus `contentless_delete=1` (SQLite 3.43+) is the alternative if we ever want the index without keeping text, but it forbids partial UPDATEs.

**Ranking.** `bm25()` is hardcoded to k1=1.2, b=0.75 — **not tunable**, which is a real constraint for retrieval research. What *is* tunable is per-column weighting: `bm25(chunks_fts, 10.0, 1.0)`, settable per query via `rank MATCH 'bm25(10.0, 1.0)'` or persistently via `INSERT INTO t(t, rank) VALUES('rank','bm25(...)')`. `ORDER BY rank` is faster than `ORDER BY bm25(t)`. Scores are negated (lower = better) and **not comparable across tables**, because avgdl differs — relevant if we ever shard the FTS index. If we need k1/b sweeps for evaluation, we must either reimplement BM25 over `fts5vocab` statistics or accept fixed constants and tune only weights and fusion.

**Size levers.** `detail=column` cuts index size ~45% at the cost of phrase/NEAR queries; `detail=none` cuts ~82% but also kills column filters. `prefix='2 3'` costs space but makes `term*` queries cheap. `columnsize=0` saves space but degrades bm25. Maintenance: `'optimize'` (slow, full) vs incremental `('merge', 500)`.

## 2. Vectors: sqlite-vec and alternatives

**Status.** sqlite-vec is still **pre-v1**; the current line is `v0.1.10-alpha.4` (2026-05-18), with `v0.1.9` (2026-03-31) the latest stable. The README warns of breaking changes. Notably, ANN indexes (**DiskANN**, plus experimental `ivf` and `rescore`) landed in the `v0.1.10-alpha` series — docs still pending. Before that, sqlite-vec was **brute-force only**. ([releases](https://github.com/asg017/sqlite-vec/releases), [repo](https://github.com/asg017/sqlite-vec))

**Filtering.** `vec0` supports three column kinds beyond the vector: **metadata columns** (max 16; TEXT/INTEGER/FLOAT/BOOLEAN; usable in KNN `WHERE` with `= != > >= < <=` only — no `IS NULL`, `LIKE`, `IN`), **partition key columns** (max 4, ideally 1; internally shards the index, ~100+ vectors per partition value recommended), and **auxiliary columns** (`+name`, max 16, unindexed, *not* usable in WHERE). ([vec0 docs](https://alexgarcia.xyz/sqlite-vec/features/vec0.html))

This maps directly onto our access pattern: partition by `document_source` or tenant, metadata-filter on `valid_from`/`valid_to` integers. It does **not** cover principal-set membership (no `IN`, no array containment), so ACL filtering has to be a post-filter or an over-fetch-then-join — see §3.

**Scale.** The author's own numbers: 100k vectors, KNN under a 100 ms target — 3072-dim float = 214 ms, 1536-dim = 105 ms, ≤1024-dim ≤75 ms, but 3072-dim **binary** = 11 ms with anecdotally ~95% retained accuracy on `text-embedding-3-large`. At 1M × 128-dim (sift1m) it works but "the limits really show". ([v0.1.0 post](https://alexgarcia.xyz/blog/2024/sqlite-vec-stable-release/index.html))

**Production reports at 100k–10M: thin and low-quality.** I found practitioner blog posts claiming ~200k vectors comfortable, ~25 ms/query and ~15 s insert at 1M, ~86 MB index overhead at 215k — but these are dev.to posts without recall@k, cache state, or persistence parity, and at least one is promotional. **I could not verify any credible first-party production report in the 1M–10M range.** Treat 1M as the honest ceiling for brute-force float32, extendable with binary quantization (`bit[N]`) or int8, and re-evaluate once DiskANN stabilises.

**Loading.** Python: `pip install sqlite-vec`, then `conn.enable_load_extension(True); sqlite_vec.load(conn)`. Rust: `cargo add sqlite-vec` and register via `sqlite3_auto_extension(Some(transmute(sqlite3_vec_init as *const ())))` with rusqlite's `bundled` feature; the crate compiles the C source with `cc`, so first builds are slow. Pass vectors zero-copy with `zerocopy::AsBytes`. ([rust docs](https://alexgarcia.xyz/sqlite-vec/rust.html))

**Alternatives.** `sqlite-vss` is explicitly **not in active development**; its README redirects to sqlite-vec. `sqlite-lembed` (local GGUF embeddings via llama.cpp) is alpha, no batching, no GPU in prebuilt binaries — not suitable; embeddings belong in our Python/Rust pipeline, not in SQL. **USearch's SQLite extension** is the most mature alternative: real HNSW, shipped inside the `usearch` Python wheel (`conn.load_extension(usearch.sqlite_path())`), with binary distance functions (`distance_hamming_binary`, `distance_jaccard_binary`) — but it exposes distance *functions*, not an indexed vtable, so it does not replace `vec0` for KNN.

## 3. Graph traversal, temporal and ACL filtering

**Recursive CTEs.** SQLite's `WITH RECURSIVE` handles k-hop and BFS/DFS: `UNION` (not `UNION ALL`) gives cycle safety by deduplicating; `ORDER BY level` on the recursive select selects breadth-first, `ORDER BY level DESC` depth-first; `LIMIT` in the recursive select is the runaway guard. Restrictions: exactly one self-reference per recursive SELECT, no aggregates or window functions in it. Shortest path is the classic `min(level)` variant. ([WITH docs](https://www.sqlite.org/lang_with.html))

**Performance.** The decisive factor is *covering* indexes in both directions. A documented case on a 10k-node graph: a 6-hop traversal went from 2.57 s to 2.5 ms purely by replacing a single-column type index with covering `(source_id, type, target_id)` and `(target_id, type, source_id)` indexes. The failure mode is fan-out, not table size: an independent 100k-node/500k-edge benchmark measured 47.7 µs for depth-1–5 from a random node but **3.79 s from the max-degree hub**, reaching 99% of the graph. Recursive CTEs cannot prune with a shared visited-set the way BFS with an explicit frontier does. (Both are third-party benchmarks — directionally consistent with the engine's design, but not first-party.)

**Practical rule for triplum:** recursive CTEs for bounded, low-fan-out traversal (k ≤ 3, neighbourhood expansion around seed entities from hybrid retrieval — exactly the GraphRAG local-search pattern). For anything iterative and global — **personalised PageRank, community detection, betweenness** — pull the adjacency into memory as CSR/`petgraph` and iterate there. PPR over a 1M-edge graph is ~20–100 sparse mat-vec products; doing that through SQL is the wrong tool. The adjacency for 1M edges as two `u32` arrays is ~8 MB; loading it via one sequential Arrow-shaped scan costs milliseconds. Keep a `GraphView` abstraction that materialises CSR once per query session and is invalidated on write.

**Existing libraries.** `dpapathanasiou/simple-graph` (~1.5k stars, MIT) is the canonical reference: two tables (`nodes` with a JSON blob + unique `id`, `edges` as source/target pairs with JSON properties), traversal via recursive CTEs, with Python/Go/Julia/R/Dart/Swift ports. It is a *schema idea*, not a dependency — its generic JSON-node design is exactly what we should **not** copy, because it forfeits typed columns and covering indexes. CozoDB (Rust, Datalog, optional SQLite backend, HNSW vector index, time-travel) is architecturally the closest prior art to triplum, but upstream releases appear stalled at 0.7.x with no 1.0; one database catalogue tags it abandoned. I found **no** actively-maintained, widely-used Python or Rust "graph database on SQLite" library worth depending on.

**JSON1 vs typed columns.** Use typed columns for anything queried or joined. Use **JSONB** (SQLite 3.45+, binary, several-fold faster than text JSON, smaller on disk) for open-world metadata. Where a JSON field becomes hot, promote it with a `STORED` generated column plus an index rather than an expression index — clearer and equally fast. `json_each` is fine for exploding a small array in a projection; it is a table-valued scan, so it is a poor basis for a hot ACL filter. ([JSON docs](https://www.sqlite.org/json1.html))

**ACL: use a junction table, not a JSON array or a bitmask.** A `document_principals(principal, document_id)` table as `WITHOUT ROWID` with PK `(principal, document_id)` is a clustered covering index: the principal→documents lookup is a single B-tree range scan with no rowid indirection. `json_each` over a JSON array cannot be indexed for set membership, and a bitmask caps the principal universe and breaks on principal churn. `WITHOUT ROWID` is specifically right here — small rows, composite non-integer PK, which is exactly its documented sweet spot (rows under ~1/20 of a page). ([WITHOUT ROWID](https://www.sqlite.org/withoutrowid.html))

**Temporal intervals.** SQLite has no interval index. The workable pattern for `valid_from <= t AND (valid_to IS NULL OR t < valid_to)`: store times as INTEGER unix-micros, use a **sentinel** (`9223372036854775807`) instead of NULL for open-ended `valid_to` so the predicate is a plain range, and index `(subject_id, predicate, valid_from)` so the leading equality columns do the selective work and `valid_from` prunes the tail. Add a **partial index** `WHERE invalidated_at IS NULL` for the overwhelmingly common "current facts only" query — partial indexes are much smaller and the planner uses them when the WHERE clause matches syntactically. Do not expect a two-sided interval index; the honest answer is that SQLite will range-scan on `valid_from` and filter `valid_to`, which is fine when the leading key columns are selective.

**STRICT tables** (3.37+) cost nothing and catch type drift at the boundary — use them everywhere; allowed types are `INT/INTEGER/REAL/TEXT/BLOB/ANY`.

## 4. Arrow interop

**ADBC.** `adbc-driver-sqlite` (Python, also usable from Rust *via the driver manager*) is a C driver, officially described as "essentially a reference driver … prioritising feature coverage over optimisation". It supports bulk ingest (`adbc_ingest`), transactions, `adbc.sqlite.query.batch_rows` for read batch size, and runtime extension loading via `adbc.sqlite.load_extension.enabled` + path + entrypoint. Type inference is a real hazard: it promotes INT64→DOUBLE→STRING based on the first batch and errors on later incompatible values — STRICT tables make this a non-issue. **There is no native Rust SQLite ADBC driver**; Rust goes through `adbc_core`'s driver manager loading `libadbc_driver_sqlite`, so it buys nothing over rusqlite for us. ([ADBC SQLite](https://arrow.apache.org/adbc/current/driver/sqlite.html), [Rust tracking issue](https://github.com/apache/arrow-adbc/issues/1723))

**Polars.** `read_database` accepts a raw `sqlite3` DBAPI2 connection, a SQLAlchemy connection, or an ADBC connection, with `iter_batches`/`batch_size` for streaming. `read_database_uri` (ConnectorX/ADBC) is documented as noticeably faster but takes only a URI, which means we cannot hand it a connection with sqlite-vec already loaded — a decisive constraint. `write_database(engine='adbc')` uses `adbc_ingest` and avoids the pandas round-trip that `engine='sqlalchemy'` still goes through. **No published SQLite bulk-ingest throughput numbers exist** for either path; the "ADBC is faster" claim is directional only, and we should measure it ourselves.

**Rust.** `connector_arrow` implements Arrow `RecordBatch` reading *and* `Append` writing on top of `rusqlite::Connection` — the only maintained option. Otherwise, build Arrow arrays directly from `rusqlite::Rows` with `arrow-rs` builders.

**Keeping conversion off the hot path.** SQLite is a row store with a row-at-a-time C API; there is no zero-copy path. So: (a) the retrieval hot path returns **IDs and scores only** — a few thousand rows, where conversion cost is irrelevant; (b) bulk paths (ingest, eval export, adjacency materialisation) are batch-oriented — one statement producing many rows, converted once into a `RecordBatch`; (c) embeddings move as BLOBs reinterpreted as `f32`/`u8` slices, never element-wise; (d) never convert inside a per-chunk loop. If columnar analytics over the corpus becomes a bottleneck, attach the file from DuckDB rather than reshaping storage.

## 5. Concurrency and ops

**WAL** is the only sensible mode: readers never block the single writer and vice versa, and the setting persists in the file. Constraints that matter for us: WAL needs **shared memory**, so it is same-host only (fine — single machine, but it rules out an NFS-mounted corpus); a read-only process still needs write access to the directory unless `-shm`/`-wal` exist; `page_size` cannot be changed while in WAL; transactions over ~100 MB may be slower than rollback mode and over ~1 GB can fail. Auto-checkpoint fires at 1000 pages (~4 MB). **Checkpoint starvation** — continuous overlapping readers preventing a checkpoint from completing — is the realistic failure mode for "notebook open all day + benchmark runner writing", so set `journal_size_limit` and run periodic `wal_checkpoint(TRUNCATE)`. ([WAL docs](https://www.sqlite.org/wal.html))

`synchronous=NORMAL` under WAL omits fsync per commit and is safe against crashes but *not* against power loss for un-checkpointed transactions. For a derived KG that can be rebuilt from source documents, that is the right trade.

Per-connection settings (they reset on every new connection — `journal_mode` and `page_size` are the file-level exceptions): `busy_timeout=5000`, `cache_size=-262144` (256 MB), `mmap_size=268435456`, `temp_store=MEMORY`, `foreign_keys=ON`. Use `BEGIN IMMEDIATE` for write transactions to avoid deferred-transaction upgrade deadlocks. Run `PRAGMA optimize` before closing long-lived connections.

**Growth and maintenance.** Deleted pages are reused but the file never shrinks; `auto_vacuum=INCREMENTAL` plus periodic `incremental_vacuum` avoids full `VACUUM` (whole-file rewrite, 2× space). `VACUUM INTO 'snapshot.db'` produces a compacted, immutable eval snapshot cheaply. For live backup use the online backup API (`Connection.backup(dst, pages=…, progress=…)`).

**Python builds — the practical answer.** `sqlite3` is "not built with loadable extension support by default" and macOS's `/usr/lib/libsqlite3.dylib` omits the API entirely; you get either `AttributeError: … enable_load_extension` or `Symbol not found: _sqlite3_enable_load_extension`. uv-managed Pythons come from `astral-sh/python-build-standalone`, which builds with `--enable-loadable-sqlite-extensions` and statically links its own SQLite — so extension loading works. **Recommendation: require a uv-managed (or python.org) interpreter, assert support at import time, and document `apsw` as the escape hatch** (statically bundles SQLite, exposes FTS5/vtable/backup/session APIs, ignores the system library entirely) with `pysqlite3-binary` as the drop-in DBAPI fallback. Never support the macOS system Python. Verify with:

```bash
uv run python -c "import sqlite3; c=sqlite3.connect(':memory:'); print(sqlite3.sqlite_version, hasattr(c,'enable_load_extension'))"
```

Note also that `sqlite3.sqlite_version` is the *library* version, independent of the Python version — FTS5 `contentless_delete` needs ≥3.43, JSONB needs ≥3.45.

## 6. DuckDB, in two paragraphs

What you gain: a real columnar engine with vectorised execution and genuine zero-copy Arrow interop in both directions, which removes the row↔column tax entirely from bulk paths and makes corpus-wide analytics (eval aggregation, degree distributions, coverage stats) an order of magnitude cheaper. `fts` gives BM25 with tunable k1/b — and BM25F with layered JSON query trees upstream — which SQLite's fixed-constant `bm25()` does not. `vss` gives HNSW rather than brute force. `duckpgq` gives SQL/PGQ pattern matching and graph algorithms, i.e. the property-graph arm without a separate engine. And DuckDB can `ATTACH 'kg.sqlite' (TYPE sqlite)` and read *and write* the SQLite file directly — so this is additive, not exclusive.

What you lose: the vector story is weaker than it looks. `vss`'s HNSW index can only be created on in-memory databases unless you set `hnsw_enable_experimental_persistence`, because WAL recovery for custom indexes is unimplemented — crash during uncommitted writes risks index corruption; even then every checkpoint re-serialises the whole index, the index must fit in RAM and does not count against `memory_limit`, only FLOAT32 is supported, and `vss_join`/`vss_match` never use the index. `duckpgq` is a community extension currently **not available for DuckDB 1.5.x** (pin 1.4.4). The `fts` index is a materialised schema that must be rebuilt, not incrementally maintained. Concurrency is stricter: one process holds the write lock on the file. The binary is ~10× larger, and mixing two SQLite libraries in one process is explicitly warned against.

**Conclusion: SQLite first is the right call.** DuckDB's wins are concentrated in analytics and evaluation, not in the incremental-write, point-lookup, per-query-filtered path that KG construction and GraphRAG retrieval actually exercise. Attach DuckDB *over* the SQLite file for eval and analytics before considering it as a primary store.

---

## 7. Proposed schema

Times are INTEGER unix microseconds UTC. `TS_MAX = 9223372036854775807` is the open-interval sentinel. `chunks.id` is a deliberate `INTEGER PRIMARY KEY` (a rowid alias) because both FTS5 external-content and `vec0` join on rowid.

```sql
-- ---------- connection / file settings ----------
PRAGMA journal_mode      = WAL;          -- file-level, persists
PRAGMA auto_vacuum       = INCREMENTAL;  -- must be set before first write
PRAGMA journal_size_limit= 67108864;
-- per-connection, re-apply on every open:
PRAGMA synchronous       = NORMAL;
PRAGMA busy_timeout      = 5000;
PRAGMA cache_size        = -262144;      -- 256 MiB
PRAGMA mmap_size         = 268435456;    -- 256 MiB
PRAGMA temp_store        = MEMORY;
PRAGMA foreign_keys      = ON;

-- ---------- documents ----------
CREATE TABLE documents (
  id           TEXT PRIMARY KEY,           -- content-addressed
  source       TEXT NOT NULL,              -- connector / corpus id
  uri          TEXT,
  observed_at  INTEGER NOT NULL,           -- when we ingested it
  metadata     BLOB                        -- JSONB, open-world
) STRICT;

CREATE INDEX documents_source_observed ON documents(source, observed_at);

-- ACL: junction table, clustered, covering. Principal-first for the hot direction.
CREATE TABLE document_principals (
  principal    TEXT NOT NULL,
  document_id  TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  PRIMARY KEY (principal, document_id)
) STRICT, WITHOUT ROWID;

CREATE INDEX document_principals_doc ON document_principals(document_id);

-- ---------- chunks ----------
CREATE TABLE chunks (
  id           INTEGER PRIMARY KEY,        -- rowid: joined by fts5 + vec0
  uid          TEXT NOT NULL UNIQUE,       -- stable external id
  document_id  TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  parent_id    INTEGER REFERENCES chunks(id) ON DELETE CASCADE,
  level        INTEGER NOT NULL DEFAULT 0, -- 0 = leaf, n = summary level
  span_start   INTEGER NOT NULL,           -- byte offsets into document text
  span_end     INTEGER NOT NULL,
  token_count  INTEGER,
  text         TEXT NOT NULL
) STRICT;

CREATE INDEX chunks_document ON chunks(document_id, span_start);
CREATE INDEX chunks_parent   ON chunks(parent_id) WHERE parent_id IS NOT NULL;

-- ---------- lexical index (external content) ----------
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  text,
  content      = 'chunks',
  content_rowid= 'id',
  tokenize     = "unicode61 remove_diacritics 2",
  prefix       = '2 3'
);

CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.id, old.text);
END;
CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.id, old.text);
  INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;

-- alias/substring matching for entity linking
CREATE VIRTUAL TABLE alias_tri USING fts5(alias, tokenize = "trigram");

-- ---------- dense index ----------
-- chunk_id mirrors chunks.id. source_id is a partition key (shards the index);
-- observed_at is a metadata column so recency can be pushed into the KNN scan.
CREATE VIRTUAL TABLE chunk_vec USING vec0(
  chunk_id     INTEGER PRIMARY KEY,
  source_id    TEXT PARTITION KEY,
  observed_at  INTEGER,
  embedding    float[1024] distance_metric=cosine
);

-- optional binary-quantized twin for cheap first-stage recall at >1M vectors
CREATE VIRTUAL TABLE chunk_vec_bit USING vec0(
  chunk_id     INTEGER PRIMARY KEY,
  source_id    TEXT PARTITION KEY,
  embedding    bit[1024]
);

-- ---------- entities ----------
CREATE TABLE entities (
  id           TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  type         TEXT NOT NULL,
  canonical_id TEXT REFERENCES entities(id),   -- NULL => is canonical
  metadata     BLOB                             -- JSONB
) STRICT;

CREATE INDEX entities_type_name ON entities(type, name);
CREATE INDEX entities_canonical ON entities(canonical_id) WHERE canonical_id IS NOT NULL;

CREATE TABLE entity_aliases (
  entity_id    TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  alias        TEXT NOT NULL,
  PRIMARY KEY (alias, entity_id)
) STRICT, WITHOUT ROWID;

-- ---------- facts (bitemporal) ----------
-- valid_*  : when the fact is true in the world
-- recorded_at / invalidated_at : when we believed it
CREATE TABLE facts (
  id             INTEGER PRIMARY KEY,
  subject_id     TEXT    NOT NULL REFERENCES entities(id),
  predicate      TEXT    NOT NULL,
  object_id      TEXT             REFERENCES entities(id),
  object_literal TEXT,
  object_type    TEXT,                         -- datatype tag for literals
  valid_from     INTEGER NOT NULL DEFAULT 0,
  valid_to       INTEGER NOT NULL DEFAULT 9223372036854775807,
  recorded_at    INTEGER NOT NULL,
  invalidated_at INTEGER,                      -- NULL => currently believed
  confidence     REAL    NOT NULL DEFAULT 1.0,
  CHECK ((object_id IS NULL) <> (object_literal IS NULL)),
  CHECK (valid_from < valid_to)
) STRICT;

-- forward traversal, current beliefs only (partial index = much smaller)
CREATE INDEX facts_spo_live ON facts(subject_id, predicate, valid_from, valid_to)
  WHERE invalidated_at IS NULL;
-- reverse traversal
CREATE INDEX facts_ops_live ON facts(object_id, predicate, valid_from, valid_to)
  WHERE invalidated_at IS NULL AND object_id IS NOT NULL;
-- full bitemporal history (audit / replay)
CREATE INDEX facts_history ON facts(subject_id, predicate, recorded_at);
CREATE INDEX facts_literal ON facts(predicate, object_literal)
  WHERE object_literal IS NOT NULL;

-- ---------- provenance ----------
CREATE TABLE fact_support (
  fact_id   INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
  chunk_id  INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  weight    REAL NOT NULL DEFAULT 1.0,
  PRIMARY KEY (fact_id, chunk_id)
) STRICT, WITHOUT ROWID;

CREATE INDEX fact_support_chunk ON fact_support(chunk_id, fact_id);

CREATE TABLE mentions (
  entity_id  TEXT    NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  chunk_id   INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  span_start INTEGER NOT NULL,
  span_end   INTEGER NOT NULL,
  confidence REAL NOT NULL DEFAULT 1.0,
  PRIMARY KEY (chunk_id, span_start, entity_id)
) STRICT, WITHOUT ROWID;

CREATE INDEX mentions_entity ON mentions(entity_id, chunk_id);

-- ---------- visibility ----------
-- Views take no parameters, so the session's principals and as-of instant live
-- in TEMP tables populated once per connection/query-session.
CREATE TEMP TABLE session_principals (principal TEXT PRIMARY KEY) WITHOUT ROWID;
CREATE TEMP TABLE session_clock (as_of INTEGER NOT NULL, now INTEGER NOT NULL);

CREATE TEMP VIEW visible_documents AS
SELECT d.*
FROM documents d
WHERE EXISTS (
  SELECT 1 FROM document_principals dp
  JOIN session_principals sp ON sp.principal = dp.principal
  WHERE dp.document_id = d.id
);

CREATE TEMP VIEW visible_chunks AS
SELECT c.* FROM chunks c JOIN visible_documents d ON d.id = c.document_id;

CREATE TEMP VIEW visible_facts AS
SELECT f.*
FROM facts f, session_clock k
WHERE f.valid_from <= k.as_of
  AND k.as_of < f.valid_to
  AND f.recorded_at <= k.now
  AND (f.invalidated_at IS NULL OR f.invalidated_at > k.now)
  AND EXISTS (
    SELECT 1 FROM fact_support fs
    JOIN visible_chunks vc ON vc.id = fs.chunk_id
    WHERE fs.fact_id = f.id
  );
```

Retrieval then over-fetches from `chunk_vec`/`chunks_fts` (partition- and metadata-filtered where possible) and joins against `visible_chunks` — because neither FTS5 nor `vec0` can express principal-set membership, ACL is always a *post*-filter, and the over-fetch factor must be tuned per tenant.

---

## Decisions we recommend

1. **SQLite + FTS5 external-content + sqlite-vec `vec0`, pinned to a stable release (`0.1.9`), not the ANN alpha.** Revisit DiskANN when it leaves alpha and the docs land.
2. **STRICT tables everywhere; JSONB for open-world metadata; promote hot JSON fields to STORED generated columns.**
3. **Junction tables (`WITHOUT ROWID`, principal-first PK) for ACL.** No JSON arrays, no bitmasks.
4. **Sentinel `valid_to` instead of NULL**, plus partial indexes `WHERE invalidated_at IS NULL` for the current-beliefs path.
5. **Recursive CTEs only for bounded k-hop; CSR/petgraph in memory for PPR and any iterative algorithm.** The store protocol should expose `neighbors(k)` and `adjacency_batches() -> RecordBatch` as separate capabilities so this split is explicit.
6. **rusqlite + `connector_arrow` in Rust; raw `sqlite3` connection + Polars `read_database(iter_batches=True)` in Python.** ADBC only where we need `adbc_ingest` throughput; measure before adopting.
7. **Require uv-managed/python.org CPython; assert `enable_load_extension` at import; document `apsw` as the fallback.** Refuse to run on macOS system Python.
8. **WAL + `synchronous=NORMAL` + `busy_timeout` + `BEGIN IMMEDIATE`; single writer process, many readers; `VACUUM INTO` for eval snapshots.**
9. **Keep DuckDB as an attached analytics/eval lens over the same file**, not a second primary store.

## Open questions

- **Fixed BM25 constants.** Do we accept k1=1.2/b=0.75, or reimplement BM25 over `fts5vocab` to make k1/b sweepable in evaluation? The latter is real work but is the only way to compare lexical scoring fairly against the DuckDB/Oxigraph arms.
- **ACL post-filter blowup.** With highly selective principals, the over-fetch factor from `vec0` may need to be very large. Is per-tenant partitioning on the `vec0` partition key sufficient, or do we need per-tenant database files?
- **Embedding storage duplication.** `vec0` owns the vectors in shadow tables. Do we also keep a canonical BLOB copy in `chunks` for re-indexing and model swaps (doubling storage), or re-embed on model change?
- **Vector ceiling.** At what corpus size do we switch to binary-quantized first-stage + float rescore, and is that our own logic or sqlite-vec's `rescore` index once stable?
- **Write coordination.** Notebook + benchmark runner is two processes. Do we enforce a single writer by convention, or add an advisory lock table?
- **Evidence at scale:** the maintainer's own sqlite-vec v0.1.0 benchmark reports 33 ms/query for `vec0` (chunk 8192/2048) over 1,000,000 SIFT-128 vectors at k=20; no production report at 1M-10M vectors was found, and no published Polars-to-ADBC SQLite bulk-ingest throughput figure exists (checked 2026-09-17). Both still need our own benchmarks before the ingest path is designed around them.

---

## Sources

- [SQLite FTS5](https://www.sqlite.org/fts5.html)
- [SQLite WITH clause / recursive CTEs](https://www.sqlite.org/lang_with.html)
- [SQLite JSON functions (JSON/JSONB)](https://www.sqlite.org/json1.html)
- [SQLite WAL mode](https://www.sqlite.org/wal.html)
- [SQLite STRICT tables](https://www.sqlite.org/stricttables.html)
- [SQLite WITHOUT ROWID tables](https://www.sqlite.org/withoutrowid.html)
- [sqlite-vec repository](https://github.com/asg017/sqlite-vec)
- [sqlite-vec releases](https://github.com/asg017/sqlite-vec/releases)
- [sqlite-vec `vec0` features](https://alexgarcia.xyz/sqlite-vec/features/vec0.html)
- [sqlite-vec in Rust](https://alexgarcia.xyz/sqlite-vec/rust.html)
- [Introducing sqlite-vec v0.1.0 (benchmarks)](https://alexgarcia.xyz/blog/2024/sqlite-vec-stable-release/index.html)
- [ANN index tracking issue #25](https://github.com/asg017/sqlite-vec/issues/25)
- [sqlite-vss (deprecated)](https://github.com/asg017/sqlite-vss)
- [sqlite-lembed](https://github.com/asg017/sqlite-lembed)
- [USearch SQLite extension](https://github.com/unum-cloud/usearch/blob/main/sqlite/README.md)
- [dpapathanasiou/simple-graph](https://github.com/dpapathanasiou/simple-graph)
- [CozoDB](https://github.com/cozodb/cozo) / [docs](https://docs.cozodb.org/)
- [ADBC SQLite driver](https://arrow.apache.org/adbc/current/driver/sqlite.html)
- [arrow-adbc Rust completeness issue #1723](https://github.com/apache/arrow-adbc/issues/1723)
- [adbc_core (Rust)](https://docs.rs/adbc_core/latest/adbc_core/)
- [connector_arrow](https://docs.rs/connector_arrow/latest/connector_arrow/)
- [Polars `read_database`](https://docs.pola.rs/api/python/stable/reference/api/polars.read_database.html) / [`write_database`](https://docs.pola.rs/py-polars/html/reference/api/polars.DataFrame.write_database.html) / [database guide](https://docs.pola.rs/user-guide/io/database/)
- [Python `sqlite3` docs](https://docs.python.org/3/library/sqlite3.html)
- [Simon Willison — loading SQLite extensions in Python on macOS](https://til.simonwillison.net/sqlite/sqlite-extensions-python-macos)
- [APSW: differences from sqlite3](https://rogerbinns.github.io/apsw/pysqlite.html)
- [astral-sh/python-build-standalone](https://github.com/astral-sh/python-build-standalone)
- [DuckDB SQLite extension](https://duckdb.org/docs/current/core_extensions/sqlite)
- [DuckDB VSS extension](https://duckdb.org/docs/current/core_extensions/vss)
- [DuckDB Full-Text Search extension](https://duckdb.org/docs/current/core_extensions/full_text_search)
- [DuckPGQ community extension](https://duckdb.org/community_extensions/extensions/duckpgq) / [repo](https://github.com/cwida/duckpgq-extension) / [VLDB paper](https://www.vldb.org/pvldb/vol16/p4034-wolde.pdf)
- Third-party, lower-confidence benchmarks (used only where labelled): [SQLite-as-graph-DB traversal report](https://dev.to/rohansx/sqlite-as-a-graph-database-recursive-ctes-semantic-search-and-why-we-ditched-neo4j-1ai), [go-sqlite-graph covering-index PR](https://github.com/justintout/go-sqlite-graph/pull/2), [LatticeDB vs SQLite traversal benchmark](https://dev.to/jamilxt/latticedb-vs-sqlite-i-ran-the-graph-traversal-benchmarks-the-gap-is-real-but-the-fine-print-14io)
