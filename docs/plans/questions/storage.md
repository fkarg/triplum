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

No unanswered ST decisions at this checkpoint. Native Postgres search remains a later
candidate; run identity is tracked under BE6. P16 implements the approved text-search slice;
see [the contract and implementation review](../../specs/text-search.md).

## Answered

### ST1. Where indexes live

Step-owned (today: `BM25` builds its own index from store reads), store-managed (a store builds,
owns and refreshes indexes for a collection from a backend-specific spec), or both.

- Claude: store-managed. A store creates an index for a collection from a backend-specific spec
  (bm25s settings for memory, an FTS5 spec for SQLite, ...), owns its refresh, and records the
  spec in its identity. bm25s stays as the memory store's lexical index (the HippoRAG reference).
- Peer (gpt-6.1-sol, 2026-11-08): both, with different purposes: keep `BM25` over `RecordStore`
  as the portable reference; a concrete store builds native indexes as objects holding one built
  snapshot (building again gives a new object); no registry, automatic refresh or universal spec
  language. Store-managed does not mean live: snapshot semantics need an explicit contract, and
  ingestion finishes before building. Observed: a snapshot BM25 returned a chunk no longer in the
  store after rechunking.

Owner (2026-11-08): **both, but primarily storage where possible/reasonable.** Earlier in the
same round: rebuild BM25 to require a store that supports it, enforced through types; keep
reference implementations (bm25s/HippoRAG).

### ST2. What is shared across backends

Only a ranked list (query → ranked chunk ids and scores, the "run" of IR tooling) consumed by
fusion, reranking, baselines and evaluation; or also minimal per-capability search Protocols
(lexical, vector) that every store implementing them answers.

- Claude: the ranked list is the cross-backend contract. Search calls stay minimal (query or
  vector, collection, viewer, k); every backend knob lives in the index spec, never in a shared
  query object (avoids LlamaIndex's accreting `VectorStoreQuery`).
- Peer: ranked output is the common data boundary, but keep payload-bearing `list[RetrievalHit]`
  (ids-only needs historical chunk lookup the store lacks; oracle hits have no score). No lexical
  or vector search Protocol until a real composition needs one; native operations stay concrete
  methods. Scores are not comparable across lists; legs of one experiment need the same collection
  and indexed state; eligibility before top `k`.

Owner (2026-11-08): **whatever is possible/reasonable as a SQLAlchemy abstraction, but not more
than makes sense.** Generic default path, overridable per backend; later stages (RRF) may be
Python or SQL, both possible and tested.

### ST3. What "the same technique" means

Backend and index spec are part of the technique's identity (FTS5 BM25 and bm25s BM25 are
different techniques), optionally with agreement tests against a Python reference when an
implementation claims equivalence.

- Claude: backend and spec are part of identity; agreement tests (fixture top-k or a stated
  tolerance) only when an implementation claims to match a reference.
- Peer: distinguish method family (BM25), configured implementation (FTS5 vs bm25s), indexed
  state (canonical indexed chunk fingerprints plus collection id, since empty indexes collide) and
  request (query, k, visibility). Observed: two BM25 instances over different corpora share a
  computation fingerprint but give different results. Agreement tests only for claimed
  equivalence; fixture agreement is not general equivalence.

Owner (2026-11-08): no definition yet; **roughly anything within a few points on
reproduction.**

### ST4. The Retriever protocol

Keep as the thin "produces a ranked list for a query" role for composition (fusion, evaluation),
replace by a ranked-list record plus plain functions, or drop.

- Claude: keep the thin role; store searches and later stages (fusion, rerank, oracle) all fit it.
  Weakly held.
- Peer: keep unchanged; a native index object implements it directly (no forwarding class);
  the collection stays bound at construction.

Owner (2026-11-08): **no native index object competing with the Retriever protocol**; the
Retriever abstraction itself is worth revisiting (store-level retrieval, lossy abstractions).

### ST5. First backends

Which stores get indexes first.

- Claude: memory (bm25s lexical, exact numpy dense) and SQLite (FTS5 lexical; dense brute force)
  now; Postgres when a concrete need appears.
- Peer: bm25s first (already covers memory), SQLite FTS5 as the first native prototype, one
  FTS5 table per built collection index, with FTS5's real controls as settings (not
  `BM25Settings`), literal query handling, higher-is-better scores and deterministic ties. Observed:
  in one shared FTS5 table, adding collection B changed collection A's scores and even reversed
  A's order despite `WHERE collection='A'` (FTS5 statistics are table-wide; reproduced by Claude: order reversed); default FTS5 matches
  "cafe" to "café", unlike our tokenizer.

Owner (2026-11-08): **memory, SQLite, Postgres first**, then go from there (Postgres BM25
extensions to try eventually).
