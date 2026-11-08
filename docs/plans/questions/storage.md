# Storage, indexing and retrieval building blocks

Questions use the `ST` prefix. Process: [questions index](README.md). Research:
[store-managed indexing](../storage-research.md), [RT10 collection scope](../rt10-collection-scope.md).

Owner direction (2026-11-08): collections are corpus boundaries, never access; the store is the
source of truth for records (later permissions); Viewers deferred; explicit building blocks and
rough shapes over interfaces for their own sake; indexing and retrieval are tied to the storage
backend and its optimization targets; leaning towards store-managed indexes; whether a
backend-independent Retriever abstraction is useful is open. RT10 folds into this area.

Current state: `RecordStore` (memory, SQLAlchemy/SQLite) holds sources, chunks and grants;
`BM25(store, /, *, collection_id, viewer, settings)` reads one collection into an in-memory bm25s
index (reproduces HippoRAG's BM25); `Retriever.__call__(query, /, *, viewer, k)`; recall consumes
hit lists.

## Open

### ST1. Where indexes live

Step-owned (today: `BM25` builds its own index from store reads), store-managed (a store builds,
owns and refreshes indexes for a collection from a backend-specific spec), or both.

- Claude: store-managed. A store creates an index for a collection from a backend-specific spec
  (bm25s settings for memory, an FTS5 spec for SQLite, ...), owns its refresh, and records the
  spec in its identity. bm25s stays as the memory store's lexical index (the HippoRAG reference).

### ST2. What is shared across backends

Only a ranked list (query → ranked chunk ids and scores, the "run" of IR tooling) consumed by
fusion, reranking, baselines and evaluation; or also minimal per-capability search Protocols
(lexical, vector) that every store implementing them answers.

- Claude: the ranked list is the cross-backend contract. Search calls stay minimal (query or
  vector, collection, viewer, k); every backend knob lives in the index spec, never in a shared
  query object (avoids LlamaIndex's accreting `VectorStoreQuery`).

### ST3. What "the same technique" means

Backend and index spec are part of the technique's identity (FTS5 BM25 and bm25s BM25 are
different techniques), optionally with agreement tests against a Python reference when an
implementation claims equivalence.

- Claude: backend and spec are part of identity; agreement tests (fixture top-k or a stated
  tolerance) only when an implementation claims to match a reference.

### ST4. The Retriever protocol

Keep as the thin "produces a ranked list for a query" role for composition (fusion, evaluation),
replace by a ranked-list record plus plain functions, or drop.

- Claude: keep the thin role; store searches and later stages (fusion, rerank, oracle) all fit it.
  Weakly held.

### ST5. First backends

Which stores get indexes first.

- Claude: memory (bm25s lexical, exact numpy dense) and SQLite (FTS5 lexical; dense brute force)
  now; Postgres when a concrete need appears.
