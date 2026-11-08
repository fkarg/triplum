# RT10 investigation: where collection selection lives

Research record for [RT10](questions/retrieval.md#rt10-collection-at-retriever-construction-or-per-query) (2026-11-08), written by a research subagent; external facts come from fetched pages (two load-bearing ones re-fetched). Options only; recommendations are recorded in the question file.


Scope: research only, no recommendation. Sources read: `AGENTS.md`, `docs/goals.md`,
`docs/specs/retrieval.md` (P8, P9, P14 draft), `docs/specs/source-access.md` (P6, P7),
`docs/plans/questions/retrieval.md` (RT10), `dense-fusion.md` (DF1-DF3),
`ingress-identity.md` (Q13, Q33), `benchmark-evidence.md` (BE11, BE14),
`docs/plans/interface-map.md`, `docs/specs/indexing.md`, `docs/specs/embedding.md`,
`src/triplum/steps/retrieval.py`, `src/triplum/store/{protocols,memory}.py`,
`src/triplum/store/sql/{tables,generic}.py`, `examples/bm25_recall.py`.

Grading: **observed** = checked in the repo or a cited doc this session; **inferred** = reasoning
from named facts; **assumed** = not checked.

---

## 0. Short version

RT10 bundles three questions that can be answered separately, and the candidate designs differ
mainly in which of them they force together:

1. **Index scope**: which chunks an index holds. For BM25 this decides scores (document
   frequencies, average length); for a graph it decides the graph; for dense vectors it decides
   only which rows a filtered ANN search visits, not the scores (cosine/dot scores do not depend
   on other documents). *Inferred* from the BM25 formula and vector similarity definitions.
2. **Per-query eligibility**: which indexed chunks a call may return (collection, viewer, later
   time, later BE11 per-question document sets). Owner: filter inside the index before ranking.
3. **Index lifecycle and identity**: who builds, persists, refreshes and fingerprints an index
   state, and what a run records about it (BE6, BE17).

The layer matters as much as the shape. Databases put the collection/tenant/partition in the
*query call* or in a *handle* obtained per collection; retriever frameworks usually bind filters
when the retriever object is built, some allow per-call overrides (section 5). triplum can choose
differently for a future store index capability (`store/protocols.py`) and for the `Retriever`
step.

Decisions the owner has not made yet that dominate the choice (section 6): what a request over
several collections means for scores (per-collection then merge, or union statistics); whether
retriever results reflect content at construction (snapshot) or at call time (live); and whether
indexes are store capabilities or step-owned objects.

---

## 1. Ground truth in the repository (observed)

- `Retriever.__call__(query: str, /, *, viewer: Viewer, k: int) -> list[RetrievalHit]`
  (approved P8; RT9 kept the protocol at three rules: at most `k`, best first, only visible).
- `BM25.__init__(store, /, *, viewer, settings=HIPPORAG1)` today; P14 (accepted by the owner,
  being implemented concurrently in the working tree) adds required `collection_id`. The
  constructor reads `store.sources(...)` and `store.chunks(...)`, sorts chunks by
  `(source_id, ordinal)`, tokenizes, builds a bm25s index in memory. Each call re-reads
  `store.sources(viewer=query_viewer)` (P14: of that collection) to mask before ranking.
- `BM25.fingerprint_config()` returns `{"settings": ...}` only. The spec says indexed content,
  construction viewer and collection belong to run identity (BE6), and retriever calls must not be
  cached until content identity exists (security review in `docs/specs/retrieval.md`, "Open").
- `RecordStore.sources(*, collection_id, viewer)` (P14; SQL `WHERE collection_id = ? AND
  visible`). `source(id)` and `chunks(source_id)` are id-selected and take no collection.
- Source id = `content_key("source-id", [collection_id, origin, text])`; Source fingerprint also
  covers `collection_id` (P6). So a digest of indexed chunk fingerprints already implies the
  collection (*inferred* from the id definition; chunks carry `collection_id`).
- `Collection(id=uuid7(), name)` exists as a model; `CollectionRow` exists as a table; no store
  operation creates or reads collections (Q13 open). Unknown collection ids give no sources.
- `docs/plans/interface-map.md` lists "retrieval caches inside retrievers (conflicts with
  cache-free benchmarks)" among rejected patterns (lines 60-61).
- BE11 (deferred): per-question eligible document keys "enforced before ranking"; owner ideas:
  collection filters, a dataset spawning several collections, or treating the 10-20 passage
  setting as reranking.
- DF2: no vector index capability exists; needs Viewer-aware pre-filtering.
- Owner decisions in force: queries select one collection, optimized per collection only, hits
  only from their own collection (Q33); "a sources query may take several collection ids, maybe
  later" (accepting P14); every store read takes a Viewer; filter inside the index before ranking;
  benchmark runs never read or write the cache and carry full run identity; one indexed vector
  per chunk per embedding configuration.

---

## 2. Candidate designs (declarations are sketches, not proposals)

### A. Collection bound at retriever construction (provisional P14)

```python
class BM25(Retriever, FingerprintedComputationMixin):
    def __init__(
        self,
        store: RecordStore,
        /,
        *,
        collection_id: UUID,
        viewer: Viewer,
        settings: BM25Settings = HIPPORAG1,
    ) -> None: ...
    def __call__(self, query: str, /, *, viewer: Viewer, k: int) -> list[RetrievalHit]: ...
```

The retriever object *is* one collection's index (BM25) or one collection's bound filter (a
dense retriever over a shared persistent table).

### B. Collection per query in the Retriever call

```python
class Retriever(Protocol):
    def __call__(
        self, query: str, /, *, collection_id: UUID, viewer: Viewer, k: int
    ) -> list[RetrievalHit]: ...
```

Sub-variants for index-holding retrievers: **B1 eager** (`BM25(store, collection_ids=[...],
viewer=...)` builds `dict[UUID, index]`, unknown id raises or returns `[]`); **B2 lazy** (index
built on first call per collection, i.e. a cache inside the retriever).

### C. Scope or query object per call

```python
class Scope(BaseModel):            # frozen
    collection_ids: frozenset[UUID]
    # later: as_of (bi-temporal), eligible source ids (BE11), metadata filters

def __call__(self, query: str, /, *, scope: Scope, viewer: Viewer, k: int) -> list[RetrievalHit]
# or C': a Query record carrying text + scope; or C'': Scope replaces Viewer and holds principals
```

### D. Index objects per collection, built by a factory or registry; retrievers route

```python
class BM25Index:  # owns tokens, bm25s arrays, chunk list
    @classmethod
    def build(cls, store, /, *, collection_id, viewer, settings) -> "BM25Index": ...
    def fingerprint(self) -> str: ...  # settings + digest of indexed chunk fingerprints


class BM25(Retriever):
    def __init__(self, index: BM25Index, store: RecordStore, /) -> None: ...
    def __call__(self, query, /, *, viewer, k): ...


class ByCollection(Retriever):  # optional router (if B's call shape is wanted)
    def __init__(self, retrievers: Mapping[UUID, Retriever], /) -> None: ...
    def __call__(self, query, /, *, collection_id, viewer, k): ...
```

D is A with the index split out as its own object with a lifecycle and fingerprint, plus an
optional router. Without the router, the Retriever call is unchanged.

### E. Collection inside Viewer

```python
class Viewer(BaseModel):
    principals: frozenset[str]
    collection_ids: frozenset[UUID]  # or a single collection_id
```

`store.sources(viewer=...)` stays collection-free in signature; every read is collection-scoped
for free. The construction viewer then fixes the index scope (collection and visibility), the
query viewer masks.

### F. Collection-scoped store handle

```python
records = store.collection(collection_id)  # RecordStore-like view, reads limited to one collection
bm25 = BM25(records, viewer=reader)  # P8 signature unchanged
```

Selection lives at the storage boundary, as a handle (Weaviate's `collection.with_tenant(...)`,
a LanceDB table, an Elasticsearch index or alias). Depends directly on the storage-interfaces
topic (Q13).

### G. Constructor default plus per-call override

`BM25(store, collection_id=default, ...)` and `__call__(..., collection_id: UUID | None = None)`.
Listed for completeness; the RT10 peer already noted it duplicates selection (two sources of
truth, and the override still needs an index for the other collection).

### H. Index from a corpus dataset rather than a store query

`BM25.from_sources(corpus_dataset, settings)`: the Pyserini/BEIR shape (index per corpus). The
collection becomes the identity of the corpus dataset (`dataset.fingerprint()` already covers
`collection_id`). Access masking would still read store grants per call. It bypasses the "every
store read takes a Viewer" path for index construction, which is acceptable only for public
benchmark corpora; listed because it makes benchmark run identity trivial.

### I. Per-collection retrievers plus a multi-collection composite

A, D or F for single collections, plus `AcrossCollections([r_a, r_b], merge=RRF(...))` as an
ordinary Retriever for the "several collection ids later" case. A completion for A/D/F rather than
a separate design.

### J. One shared index, with eligibility and statistics scope both chosen per query

One index over all collections; each call names both the eligible set (collection plus viewer)
and the statistics corpus (default: the same collection). This is what Qdrant offers since
v1.19 with a per-query `idf` statistics-corpus filter, separate from the retrieval filter (section
5). For triplum's in-memory BM25 it would mean keeping raw term frequencies and computing idf and
average length per call over the chosen corpus, instead of bm25s's precomputed score matrix
(*inferred*: bm25s precomputes per-token scores at index time, which bakes in the statistics).
It is the per-call design that keeps per-collection statistics without per-collection index
objects, and it also covers per-viewer statistics (statistics corpus = viewer's projection) at
per-query cost.

---

## 3. Walkthroughs by scenario

Common setup (all scenarios, observed shape from `examples/bm25_recall.py`):

```python
collection = Collection(id=HOTPOTQA_ID, name="hotpotqa")  # fixed id: reproducible Source ids
corpus = list(fixture.corpus(collection.id))
store = MemoryStore()  # fresh per benchmark run
store.add_sources(corpus, allow=["public"])
for s in corpus:
    store.replace_chunks(s.id, WholeText()(s))
reader = Viewer(principals=frozenset({"public"}))
```

Run identity items that exist in every design (*inferred* from BE6 wording and the AGENTS
requirement "everything changing an answer"): corpus dataset fingerprint (covers collection id),
chunker fingerprint, retriever fingerprint (settings), construction and query viewer principals,
`k`, and a content digest of what the index holds. Today nothing computes that digest; BM25
holds every indexed chunk, so it could.

### (a) HotpotQA benchmark, BM25, R@k

| Design | Calls | Index owner / build / refresh | Run identity specifics |
| --- | --- | --- | --- |
| A | `bm25 = BM25(store, collection_id=c, viewer=reader)`; `bm25(q, viewer=reader, k=5)` | BM25 object; built in constructor; never refreshed | collection fixed per retriever; record once per run. Index build cost = constructor time, measurable separately from query latency |
| B1 | `BM25(store, collection_ids=[c], viewer=reader)`; `bm25(q, collection_id=c, viewer=reader, k=5)` | BM25 object, dict per collection, eager | collection per call; constant over a benchmark, but the record must say so per question or assert it |
| B2 | `BM25(store, viewer=reader)`; same call | BM25 object, lazy on first call | build cost lands in the first query's latency (confounds per-query cost unless warmed explicitly); hidden cache inside a retriever, which the interface map rejects |
| C | `bm25(q, scope=Scope(collection_ids={c}), viewer=reader, k=5)` | as B1 or B2; C changes the argument's shape, not the index problem | scope recorded per call |
| D | `idx = BM25Index.build(store, collection_id=c, viewer=reader, settings=HIPPORAG1)`; `bm25 = BM25(idx, store)` | index object; explicit build step; can be persisted and loaded (BE17 separate index-build runs) | `idx.fingerprint()` = settings + content digest: content-addressed as AGENTS requires for expensive stages |
| E | `reader_c = Viewer(principals={"public"}, collection_ids={c})`; `BM25(store, viewer=reader_c)`; call with `viewer=reader_c` | as A | collection recorded as part of viewer |
| F | `BM25(store.collection(c), viewer=reader)`; call unchanged | as A | as A |
| H | `BM25.from_sources(corpus, settings)` | BM25 object from dataset | identity = corpus dataset fingerprint + settings; no store read at build |

Observation: for a single-collection benchmark all designs are equivalent in results; they
differ in where the collection id is written and whether index build is a visible step.

### (b) Dense retriever with a persistent vector index holding several collections

Hypothetical storage (DF2 not designed): one table or per-collection tables of
`(chunk_id, source_id, collection_id, vector[, principals])`, filled by an indexing pipeline
`chunks -> EmbeddingText -> Embedder -> vectors.add(...)` that runs separately from retrieval.

- **A**: `Dense(vectors, embedder, collection_id=c)`; call `(q, viewer, k)` runs
  `vectors.search(embed(q), where collection_id = c AND source visible, k)`. Constructor only
  binds a predicate: no content snapshot, cheap. One object per collection; an application with
  N collections holds N bound objects (or creates them per request, which is cheap).
- **B**: `Dense(vectors, embedder)`; `dense(q, collection_id=c, viewer=v, k=5)`. Closest to the
  database APIs (filter or partition per query); one object serves every collection.
- **C**: as B with `scope`; the store query is assembled from all scope fields. Each implementation
  must honour or reject every scope field, otherwise an unsupported field silently widens results
  (*inferred*).
- **D**: per-collection index handles: `registry[c] -> table/partition/tenant handle`;
  `Dense(handle, embedder)`. Natural if Q13 chooses tables or partitions per collection.
- **E**: viewer carries collection; store query filters on `viewer.collection_ids`. Dense code
  sees one object to forward.
- **F**: `Dense(vectors.collection(c), embedder)`: the vector store hands out collection handles.

Facts that matter here (*inferred* from definitions): dense scores do not depend on other
indexed rows, so "optimized per collection" for dense is about filtered-ANN recall and latency
(partition/tenant layout), not about score comparability. Persistent indexes are usually live
(new rows searchable after write or refresh), unlike today's BM25 snapshot. Viewer filtering in a
persistent vector index requires either denormalized principals in vector rows, passing the
visible source-id set from `store.sources(collection_id, viewer)` as a prefilter (fine for 10^4
sources, heavy for 10^6), or a join in the same database (pgvector next to `source_access`).
That choice belongs to the storage interfaces.

### (c) RRF fusion of BM25 + dense

- **A / D / F**: `rrf = RRF([BM25(store, collection_id=c, viewer=v), Dense(vectors, emb,
  collection_id=c)], depth=100, constant=60)`; `rrf(q, viewer=v, k=5)` calls each component with
  `k=depth` and fuses ranks. Keeping components on the same collection is the caller's
  construction-time obligation. RRF can check it only if retrievers expose a `collection_id`
  attribute, which the protocol does not require and external retrievers may lack. Run identity:
  RRF fingerprint can nest component fingerprints (the mixin supports nested `fingerprint()`
  values, observed in its docstring); each component's content identity still has to be recorded.
- **B / C**: `RRF([BM25(store, ...), Dense(vectors, emb)])`; `rrf(q, collection_id=c, viewer=v,
  k=5)` forwards the same collection to every component: consistent by construction, fusion
  needs no collection logic beyond forwarding.
- **E**: viewer is already forwarded; fusion code identical to today; consistent by construction.
- Mixed staleness (all designs, *inferred*): a snapshot BM25 fused with a live dense index ranks
  newly ingested sources only in the dense list. See (f).

### (d) Application querying two of its collections in one request

Owner constraint: optimized per collection, hits only from their own collection. A request over
`{a, b}` therefore needs a merge rule, and BM25 scores from two collections are not comparable
(different idf and average length). Dense cosine scores are comparable across collections, so a
single dense query with `collection_id IN (a, b)` is valid where a single BM25 query over the
union would mean union statistics (*inferred*).

- **A / D / F + I**: application keeps `retrievers: dict[UUID, Retriever]` built per collection;
  per request `AcrossCollections([retrievers[a], retrievers[b]], merge=RRF(...))(q, viewer=v,
  k=10)`. Merge policy lives in one composite block and applies to every technique alike. The
  `dict[UUID, Retriever]` is the registry of D, held in application code.
- **B**: call shape becomes `collection_ids: frozenset[UUID]` (or the single id widens later, a
  breaking change to every implementation). Each implementation then decides the multi-collection
  semantics internally: BM25 per-collection-then-merge or union statistics; dense one query. The
  merge rule is duplicated in or diverges between implementations unless the protocol specifies it.
- **C**: `Scope(collection_ids={a, b})`: same as B; the set type exists from day one, so no
  later signature change, but the semantics question is identical.
- **E**: `Viewer(collection_ids={a, b})`; an index built for that viewer would hold the union
  (union statistics) unless BM25 keeps per-collection indexes internally.
- Store side: `sources(collection_ids=...)` (owner's "maybe later") is a listing question,
  independent of how retrieval merges.

### (e) User with access to part of a collection; per-viewer statistics later

Today (RT7 (c)): index over the construction viewer's chunks, statistics over that set, mask per
call by the query viewer; scores leak term statistics of hidden sources (documented).

- **A**: `BM25(store, collection_id=c, viewer=corpus_viewer)`; `bm25(q, viewer=alice, k=5)`
  masks. Per-viewer statistics later: `BM25(store, collection_id=c, viewer=alice)` per principal
  set; the application keeps them keyed by `(c, alice.principals)`. The construction viewer is the
  statistics scope; nothing new in the protocol.
- **B**: per-viewer statistics means the retriever keys internal indexes by `(collection_id,
  principals)`: a growing hidden cache with invalidation on grant changes.
- **C**: if Scope holds principals too (C''), the scope is the natural key of a per-scope index
  (frozen, hashable), but it mixes authorization (who reads, trusted from auth) with selection
  (what the user asked for, untrusted input).
- **D**: registry keyed by `(collection_id, principals)`; explicit build/load/refresh per key;
  persistence per key possible. Equivalent to Elasticsearch index-per-tenant versus one index with
  document-level security (section 5).
- **E**: the viewer is already the statistics scope at construction, so per-viewer and
  per-collection scope are one key. Cost: a viewer is no longer "who is reading" alone; the store
  must interpret `collection_ids` in every read, including id reads (`source(id)` of another
  collection would raise `KeyError`).
- Graph (later): AGENTS requires kernels on the viewer's projection; a per-collection graph plus a
  per-viewer projection is the same `(collection, principals)` key question.

### (f) Ingestion adds sources to a collection after a retriever exists

- **A / E / F**: BM25 is a snapshot; the caller rebuilds. A dense retriever bound only to a filter
  over a live table sees new rows at once. Construction therefore means "content fixed" for BM25
  and "predicate fixed" for dense. Options: pin the vector table version at construction (LanceDB
  has table versions, see section 5), give BM25 a refresh, or declare live semantics per
  implementation.
- **B2 / C lazy**: a cached per-collection index silently serves old content unless invalidated.
  Invalidation needs a content fingerprint of the collection (computing it costs about a rebuild's
  reads) or a store generation counter (AGENTS forbids manually maintained counters for ids and
  fingerprints; a cache-invalidation counter is a related but different use; *inferred* to be
  contentious).
- **D**: `BM25Index.build(...)` again, or `index.refresh(store)` returning a new index with a new
  content fingerprint; the registry swaps the entry. Old and new index states are distinct
  identities, so runs referencing them stay unambiguous.
- Later persistent BM25 (SQLite FTS5, tantivy, Elasticsearch; RT8 mentions database-level
  analysis) is live as well, so the snapshot guarantee is a property of today's in-memory
  implementation, not of retrieval in general (*inferred*).

---

## 4. Tradeoffs

| Criterion | A construction | B per call | C scope per call | D index objects + routing | E in Viewer | F store handle |
| --- | --- | --- | --- | --- | --- | --- |
| Protocol change | none (P8 call kept) | every Retriever, Fuser components, oracle | every Retriever; new type | none for Retriever; new index types | Viewer and every store read | new store method; Retriever unchanged |
| Local reasoning | object = one collection's index; simple | one object, many indexes; behaviour depends on hidden state (B2) | as B, plus field-support rules | index lifecycle explicit and separate from query | access and selection in one object; harder to audit | selection visible at call site |
| Per-collection BM25 statistics | natural | B1 dict / B2 cache | as B | natural | natural with one collection | natural |
| Fusion consistency | caller obligation; uncheckable without an attribute | by construction | by construction | caller obligation | by construction | caller obligation |
| Persistent shared index | thin bound filter, fine | matches DB APIs | matches filter APIs | matches table/partition-per-collection | filter from viewer | handle per collection, matches Weaviate/LanceDB style |
| Run identity | fixed per object, record once | per call; lazy/live state may change mid-run | per call | content-addressed index fingerprint | in viewer | as A |
| Several collections later | composite block (I) | signature widens; semantics per implementation | set from day one; semantics per implementation | router + merge | set in viewer; union statistics by default | handle over several, semantics open |
| Access control | unchanged (viewer per call) | unchanged | risk if principals move into scope | unchanged | conflates trust levels | unchanged |
| Per-viewer statistics later | app-held map | hidden cache | scope key | explicit registry | viewer key | handle per (c, viewer) |
| Index build cost measurement | constructor | first call (B2) | first call | build step | constructor | constructor |
| Testing | per-collection fixtures, few cases | cross-collection routing, lazy build, invalidation | plus field support | registry and router tests | every store test gains collection dimension | handle semantics tests |
| BE11 per-question eligibility | not covered; needs separate filter | could add per-call ids | natural field | not covered | awkward | not covered |
| Graph PPR later | graph per object | route to graph per call | as B | graph index object | as A | as A |

Design J (shared index, per-query statistics corpus) in brief: per-call shape like B/C; one index; per-collection and per-viewer statistics at per-query cost; no bm25s precomputed scores; run identity per call; fusion consistent if the scope is forwarded.

---

## 5. External evidence

Collected by a web-research subagent on 2026-11-08 through WebFetch summaries of the pages (quotes
are as summarised, not diffed against raw HTML). I re-fetched the Elasticsearch rrf `filter`
wording and the Qdrant statistics-corpus and collection-per-tenant wording myself; both match.
Facts carry URLs; inferences are marked.

### 5.1 Vector databases: collections, tenants, partitions

- **Qdrant** (https://qdrant.tech/documentation/guides/multiple-partitions/): "Creating a separate
  collection for each tenant is rarely the most efficient approach"; recommended: one collection,
  payload field plus filter per query, keyword index with `is_tenant: true` (v1.11+) to co-locate
  a tenant's vectors; `shard_key` for few large tenants; tiered multitenancy (v1.16+). BM25 and
  IDF-modified sparse scoring use statistics "computed across the entire shard being queried"; a
  per-query `idf` parameter narrows the "statistics corpus" independently of the retrieval filter
  (verified myself). Freshness: with `wait=true` points are searchable when the write returns;
  unindexed segments are brute-forced (https://qdrant.tech/documentation/concepts/optimizer/).
- **Weaviate** (https://docs.weaviate.io/weaviate/manage-data/multi-tenancy): "Each tenant is
  stored on a separate shard"; queries bind a tenant through a handle,
  `collection.with_tenant("tenantA")`; queries on a multi-tenant collection require the tenant.
  No official statement found on per-tenant BM25 statistics (*inferred* per tenant, since one
  tenant is one shard with its own inverted index; unverified).
- **Milvus** (https://milvus.io/docs/multi_tenancy.md): database (64 default), collection (65,536),
  partition (up to 1,024 per collection), partition key (hashed into 16 partitions). Scalability
  "Partition Key > Partition > Collection > Database"; RBAC only at database and collection
  level; only partition and partition-key strategies allow cross-tenant queries.
- **LanceDB** (https://docs.lancedb.com/search/filtering): prefiltering is the default and
  restricts eligible rows before candidate selection; postfiltering can return fewer than `limit`
  rows; "On hybrid queries, the filter applies to both the vector and full-text searches."
  Appended rows stay searchable by flat scan until `optimize()`
  (https://docs.lancedb.com/indexing/reindexing). Every change, including `optimize()` and
  compaction, creates a table version; `checkout(version|tag)` pins reads
  (https://docs.lancedb.com/tables/versioning). *Inferred*: a tag can pin an index snapshot for a
  run, but version numbers are not data identity.
- **pgvector** (https://github.com/pgvector/pgvector, README 0.8.x): "With approximate indexes,
  filtering is applied after the index is scanned"; iterative scans are off by default
  (`hnsw.iterative_scan`); partial indexes for few filter values, `PARTITION BY LIST` for many.
  *Inferred*: a collection filter on a shared HNSW table can under-fill top-k unless configured,
  which collides with the owner's "full eligible top k" rule.
- **sqlite-vec** (https://alexgarcia.xyz/sqlite-vec/features/vec0.html, v0.1.10-alpha): partition
  key columns shard the vector index; an `=` constraint restricts search to that partition; at
  most 4 partition keys, roughly hundreds of vectors per value recommended; up to 16 filterable
  metadata columns.
- **Pinecone** (https://docs.pinecone.io/guides/index-data/implement-multitenancy): namespaces
  give physical isolation; each query targets one namespace; SDK `query_namespaces(...)`
  (https://sdk.pinecone.io/python/how-to/vectors/namespaces.html) fans out client-side and merges
  by raw score, requiring the metric.

### 5.2 Elasticsearch and OpenSearch

- `search_type` (https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-search):
  default `query_then_fetch` scores "using local term and document frequencies for the shard";
  `dfs_query_then_fetch` uses global frequencies across shards, slower. Background:
  https://www.elastic.co/blog/practical-bm25-part-1-how-shards-affect-relevance-scoring-in-elasticsearch.
- Document-level security
  (https://www.elastic.co/docs/deploy-manage/users-roles/cluster-or-deployment-auth/controlling-access-at-document-field-level):
  "Document level security doesn't affect global index statistics that relevancy scoring uses."
  This is the precedent already cited for RT7 (c).
- Multi-index search in one request is supported
  (https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-multiple-data-streams-indices),
  with `indices_boost`; the page does not discuss cross-index score comparability (*inferred*: raw
  BM25 scores from indices with different statistics are merged as if comparable).
- Near-real-time refresh every second on recently searched indices
  (https://www.elastic.co/docs/manage-data/data-store/near-real-time-search).
- No current official Elastic or OpenSearch page recommending index-per-tenant versus shared index
  was found; only secondary sources (e.g. AWS Prescriptive Guidance,
  https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/build-a-multi-tenant-serverless-architecture-in-amazon-opensearch-service.html).
  Treat that framing as weaker evidence.

### 5.3 Fusion with filters

- Elasticsearch `rrf` retriever
  (https://www.elastic.co/docs/reference/elasticsearch/rest-apis/retrievers/rrf-retriever):
  `filter` "Applies the specified boolean query filter to all of the specified sub-retrievers"
  (verified); `rank_constant` default 60, `rank_window_size` default 10.
- OpenSearch `hybrid` query (https://docs.opensearch.org/latest/query-dsl/compound/hybrid/): a
  top-level `filter` since 3.0 applies to all subqueries; before 3.0 it had to be repeated per
  subquery.
- *Inferred*: the engines converged on one scope given to the fusion node and pushed into each
  leg before that leg's top-k. That is the per-call shape (B, C, E) or a factory that builds every
  leg from one scope (D); A leaves consistency to whoever builds the legs.

### 5.4 Retriever frameworks

- **LlamaIndex**: `BaseRetriever.retrieve(str_or_query_bundle)` takes no filter
  (https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/base/base_retriever.py);
  `VectorIndexRetriever.__init__(..., filters: MetadataFilters | None, node_ids, doc_ids, ...)`
  fixes filters at construction, e.g. `index.as_retriever(filters=...)`
  (https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/indices/vector_store/retrievers/retriever.py).
  Pure construction binding (design A).
- **Haystack 2.x**: `InMemoryBM25Retriever` takes `filters` in `__init__` and in
  `run(query, filters=None, top_k=None, ...)`; `filter_policy` defaults to `REPLACE` ("Overrides
  the initialization filters with the filters specified at runtime"); `MERGE` AND-combines
  (https://github.com/deepset-ai/haystack/blob/main/haystack/components/retrievers/in_memory/bm25_retriever.py,
  https://github.com/deepset-ai/haystack/blob/main/haystack/document_stores/types/filter_policy.py).
  The in-memory store filters documents, then scores with store-wide idf and average length
  (subagent's reading of
  https://github.com/deepset-ai/haystack/blob/main/haystack/document_stores/in_memory/document_store.py),
  i.e. filtered BM25 with global statistics. *Inferred*: this is design G, and its default shows
  the hazard: a per-call value silently replaces the construction scope.
- **LangChain**: `BaseRetriever.invoke(input, config=None, **kwargs)`
  (https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/retrievers.py);
  `as_retriever(search_kwargs={"filter": ...})` binds at construction and per-call kwargs override
  key by key (`self.search_kwargs | kwargs`,
  https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/vectorstores/base.py).
  Also G-like.

### 5.5 Benchmark tooling

- **Pyserini** (https://github.com/castorini/pyserini): one index per corpus,
  `LuceneSearcher(index_dir)` or `LuceneSearcher.from_prebuilt_index(name)`; prebuilt indexes map
  one-to-one to corpora (MS MARCO, each BEIR dataset, MIRACL).
- **BEIR** (https://github.com/beir-cellar/beir/blob/main/beir/retrieval/search/dense/exact_search.py):
  `search(corpus, queries, top_k, score_function, ...)`: the corpus is an argument, one per
  dataset.
- **ir_datasets** (https://ir-datasets.com/python.html): `docs_iter()`, `queries_iter()`,
  `qrels_iter()` per dataset; subsets inherit the parent's documents
  (https://ir-datasets.com/msmarco-passage.html).
- *Inferred*: benchmark tooling treats a collection as one index built from one corpus and never
  filters by collection per query; several query sets reusing one corpus suggests that the index
  identity should be the corpus content, not the benchmark (design D or H).

### 5.6 What the evidence does and does not settle (inferred)

- Systems separate *which documents may be returned* from *which documents define statistics*
  (Qdrant explicitly; Elastic DLS and Haystack implicitly by using global statistics). triplum's
  owner already chose per-collection statistics, so a shared index needs either per-collection
  index objects or per-query statistics (J).
- Database layers put selection per query or per handle; frameworks bind at construction and often
  allow per-call overrides. No source argues the Retriever step itself must take the collection.
- Construction binding is the norm for benchmarks; per-call scope is the norm for fusion in
  engines. These pull in different directions for triplum, which needs both.
- Per-call override of a construction scope (G; Haystack REPLACE, LangChain merge) is a documented
  way to widen scope silently.
- Not verified: Weaviate per-tenant BM25 statistics; official Elastic index-per-tenant guidance;
  Vespa, Tantivy, MTEB.

---

## 6. Open sub-questions for the owner, with dependencies

Grouped by what they unblock. "Storage" marks a dependency on the storage-interfaces topic.

**Semantics (decide first; they constrain every design)**

1. **Several collections in one request.** Per-collection retrieval then merge (RRF, interleave,
   per-collection quotas), or one ranking with union statistics? Owner's "optimized per
   collection only" points to the former for BM25; dense could use one query either way. Is the
   "several collection ids later" remark about `sources()` listing only, or also retrieval?
2. **Snapshot or live.** Does a retriever answer from content at construction, or at call time?
   Today's BM25 is a snapshot; persistent dense and future database BM25 are live (5.1, 5.2).
   Fusion mixes them. Options: per-implementation statement, protocol rule, or pinned versions
   (LanceDB tags) for benchmark runs.
3. **Is collection an authorization boundary?** Today grants are per source and collection is a
   selection. Design E makes it authorization-like; a per-call collection is untrusted input.
   Can a viewer ever be denied a whole collection?
4. **Unknown collection id.** P14 returns no sources silently. Under per-call designs, a typo in a
   library id gives `[]` per query. Raise once collections are stored records (Q13)?

**Index ownership and lifecycle (storage)**

5. **Are indexes store capabilities or step-owned?** `store/protocols.py` intends one Protocol per
   capability; a `TextIndex`/`VectorIndex` capability with a per-call collection filter (DB-style)
   could sit under a construction-bound Retriever. Choosing per layer is possible.
6. **Q13 layout.** One table with a collection column (filter, partition key, J) versus tables,
   partitions or tenants per collection (handles, D/F). Backend facts: pgvector filters after the
   ANN scan unless iterative scan or partitions are configured; sqlite-vec partition keys
   pre-filter by equality; Qdrant recommends one collection with tenant payload.
7. **Index identity (BE6, BE17).** Does an index state get its own content fingerprint (settings
   plus digest of indexed chunk fingerprints, which already implies the collection), computed at
   build? Can index building be a separate run whose output a retrieval run references?
8. **Refresh.** Rebuild-only, explicit `refresh` returning a new index state, or live writes? Who
   triggers it after ingestion (scenario f)?

**Access and statistics**

9. **Viewer filtering in a persistent vector index.** Denormalize principals into vector rows,
   pass visible source ids from `store.sources(collection_id, viewer)`, or join in one database?
   Interacts with future revoke and time axes.
10. **Per-viewer statistics key.** When RT7's viewer-scoped indexes arrive, is the key the exact
    principal set, and who holds the map (application, registry, retriever)? Same question for
    graph projections.

**Composition**

11. **Fusion consistency under construction binding.** If components bind their own collection,
    does fusion check it (requires a protocol attribute), or is it documented as the caller's job?
12. **Fusion component depth.** RRF calls components with a window larger than final `k`
    (Elasticsearch default 10, constant 60); independent of RT10 but in the same declaration.
13. **Other per-query filters.** BE11 per-question eligible documents and bi-temporal "as of"
    retrieval are per-query by nature. Should they share a mechanism with collection selection
    (C), or stay separate so collection remains an index-scope choice? Sequencing: if a per-call
    filter object is coming for time anyway, deciding RT10 first may force a second protocol
    change.
14. **Graph retrieval.** One graph per collection, with no cross-collection entity linking?
    (Follows from Q33 but not stated.)

