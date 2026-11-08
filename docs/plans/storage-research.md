# Store-managed indexing and retrieval: external research

Research record for the storage topic (2026-11-08), written by a research subagent. Claims are graded observed (primary page read) or reported (summary or secondary source). Options only; recommendations live in the question file.

Research for triplum (2026-11-08). Read-only; no repo changes. Local context read: `AGENTS.md`,
`docs/goals.md`, `docs/plans/rt10-collection-scope.md` (not repeated: tenancy/partition handles,
filtered-ANN basics, ES shard statistics, framework filter binding), `src/triplum/steps/retrieval.py`,
`src/triplum/store/`.

Grading: **observed** = read in a primary source this session (URL given); **reported** = from a
search-engine summary or secondary source I did not open, treat as weaker; **inferred** = my
reasoning, with the facts it rests on.

---

## 1. Facts: how much "the same technique" differs across backends

### 1.1 BM25 / lexical

| Backend | Is it BM25? | k1/b | Tokenization defaults | Statistics scope / quirks | Source |
|---|---|---|---|---|---|
| SQLite FTS5 `bm25()` | Yes | **Hard-coded** k1=1.2, b=0.75 ("k1 and b are both constants"); only per-column weights configurable | `unicode61` default: letters/numbers are tokens, Unicode 6.1 case folding, **diacritics removed by default**; `porter` wraps another tokenizer (English only); `trigram`, `ascii` | Score **negated** (lower = better) | observed: https://www.sqlite.org/fts5.html |
| Postgres `ts_rank`/`ts_rank_cd` | **No.** "the ranking functions do not use any global information" (no IDF); length normalization is an opt-in bit flag, default ignores length | n/a | text search config (`english` etc.: stemming, stopwords) | per-document only | observed: https://www.postgresql.org/docs/current/textsearch-controls.html |
| Postgres + pg_textsearch (Tiger Data, v1.5.1, PostgreSQL licence) | Yes, `bm25` index, `<@>` operator | k1 default 1.2 (0.1-10), b 0.75, set in index `WITH` | Postgres `text_config` | "BM25 statistics are local to each partition"; **"corpus statistics include all indexed rows, including rows hidden by RLS"**; with `ORDER BY` via BM25 scan other WHERE conditions are post-filters (batch grows until LIMIT filled); scores negated | observed: https://github.com/timescale/pg_textsearch |
| Postgres + ParadeDB pg_search (tantivy) | Yes | per-field k1 (0-100, default 1.2) and b (default 0.75) set **at index creation** via tokenizer options, e.g. `description::pdb.simple('k1=0.9','b=0.3')`; query-time boosts only | tokenizer chosen per field | "scores ... may be influenced by dead rows that have not been cleaned up by the VACUUM process"; ties not deterministic without a tiebreak column | observed: https://www.paradedb.com/docs/documentation/sorting/score ; reported (search summary of) https://www.paradedb.com/docs/reference/indexing/create-index |
| Postgres + VectorChord-bm25 | BM25 over a `bm25vector` sparse type, Block-WeakAnd | not documented on README | separate `pg_tokenizer` extension | index returns at most `bm25_catalog.bm25_limit` rows (default 100) to Postgres, so selective filters can starve results | observed: https://github.com/tensorchord/VectorChord-bm25 |
| DuckDB FTS | Yes, `match_bm25` macro | **query-time** `k:=1.2, b:=0.75`, `conjunctive` | defaults: `stemmer='porter'`, `stopwords='english'` (571 words), `ignore='(\\.|[^a-z])+'`, `strip_accents=1`, `lower=1` | "By default, the FTS index will not update automatically when the input table changes" (`incremental=1` opt-in); docs example filters *after* scoring in an outer query | observed: https://duckdb.org/docs/2.0/core_extensions/full_text_search.html |
| ClickHouse text index | GA since 26.2 as **filter only** (`hasToken`, `hasAllTokens`, ...); no ranking in a release | BM25 PR #117519 (`_bm25_score` virtual column, `bm25([k1[, b]])`) is **still open** (GitHub API: state=open, not merged) | many tokenizers (`splitByNonAlpha`, `ngrams`, `icu`, ...) | in the PR: "Collection statistics come from the parts the query reads"; shards score independently; doc lengths quantized to one byte | observed: https://clickhouse.com/docs/engines/table-engines/mergetree-family/textindexes ; https://github.com/ClickHouse/ClickHouse/pull/117519 |
| Elasticsearch / OpenSearch (Lucene) | Yes, default similarity | k1 1.2, b 0.75, `discount_overlaps` true; changing similarity on an existing index requires close/update/reopen | `standard` analyzer | per-shard stats unless `dfs_query_then_fetch` (see RT10 record) | observed: https://www.elastic.co/docs/reference/elasticsearch/index-settings/similarity |
| Lucene `BM25Similarity` | Yes | defaults k1=1.2, b=0.75, discountOverlaps=true | analyzer chosen by app | doc length stored as a lossy one-byte norm (reported, see 1.3) | observed: https://lucene.apache.org/core/9_12_0/core/org/apache/lucene/search/similarities/BM25Similarity.html |
| tantivy | Yes | **constants** `K1 = 1.2`, `B = 0.75` in source; `Bm25StatisticsProvider` trait lets callers supply their own corpus statistics | app-defined | `total_num_docs` sums `max_doc()` per segment (includes deleted docs until merge); doc length quantized to 256 fieldnorm buckets (`compute_tf_cache` over `[Score; 256]`) | observed: https://github.com/quickwit-oss/tantivy/blob/main/src/query/bm25.rs |
| Qdrant full-text index | Yes, scored search | **query-time** `k` 1.2, `b` 0.75, "adjusted without rebuilding the index" | configurable | "each shard uses its own statistics" | observed: https://qdrant.tech/documentation/search/text-search/full-text-search/ |
| Qdrant sparse `Qdrant/bm25` | BM25-shaped sparse vectors + IDF modifier at query time | `k`, `b`, **`avg_len` default 256, supplied by the user** | English: lowercase, stopwords, stemming | docs: "We recommend running BM25 on a full-text index rather than on sparse vectors"; forgetting `modifier=IDF` silently gives TF-only scoring (reported) | observed: https://qdrant.tech/documentation/search/text-search/sparse-vector-search/ |
| Pinecone | Full-text fields with "BM25 ranking and Lucene query syntax"; also learned sparse (`pinecone-sparse-english-v0`) | not stated on page | not stated | not stated | observed: https://docs.pinecone.io/guides/search/lexical-search |
| bm25s (triplum today) | Five variants from Kamphuis et al., exact (no norm quantization), eager sparse scores | user-set | user tokens | statistics fixed at index time | observed: https://arxiv.org/abs/2407.03618 |

### 1.2 Dense retrieval

- **pgvector**: exact by default; "you will see different results for queries after adding an
  approximate index"; with approximate indexes "filtering is applied *after* the index is scanned";
  iterative scans (0.8.0+) in strict or relaxed order; `hnsw.ef_search` default 40. observed:
  https://github.com/pgvector/pgvector
- **ClickHouse** vector similarity index (GA from 25.8): HNSW with M=32, ef_construction=128,
  **graph quantization default bf16**; post-filtering by default, "may return less than the number
  of rows requested in the LIMIT"; `vector_search_filter_strategy='prefilter'` and
  `vector_search_index_fetch_multiplier` to compensate; indexes are local to parts. observed:
  https://clickhouse.com/docs/engines/table-engines/mergetree-family/annindexes
- **Elasticsearch**: a `filter` inside `knn` is applied during the HNSW search (pre-filter);
  `post_filter` can return fewer than k; `num_candidates` per shard (max 10,000); current docs add an
  adaptive switch to post-filtering above a selectivity threshold
  (`index.dense_vector.post_filter_selectivity_threshold`). reported (search summary of)
  https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-knn-query
- **Qdrant**: filterable HNSW gains filter-aware edges only if payload indexes exist before the graph
  is built; query planner picks payload-index scan vs HNSW from cardinality estimates. observed:
  https://qdrant.tech/documentation/concepts/indexing/
- **sqlite-vec**: stable releases are brute force (exact); ANN (DiskANN, rescore, experimental IVF)
  only in v0.1.10 alphas. reported: https://github.com/asg017/sqlite-vec/releases ,
  https://github.com/asg017/sqlite-vec/issues/25
- LanceDB/Pinecone filtering and partition behaviour: see RT10 record section 5.1.

### 1.3 What the research community does to keep comparability

- **Kamphuis, de Vries, Boytsov, Lin, "Which BM25 Do You Mean?" (ECIR 2020)**: compared BM25
  variants in Lucene/Anserini; concluded effectiveness differences are "unlikely an effect of the
  choice of the BM25 variant", including Lucene's lossy norms vs "accurate" BM25. reported (abstract
  and search summary): https://cs.uwaterloo.ca/~jimmylin/publications/Kamphuis_etal_ECIR2020_preprint.pdf
- **bm25s paper (Lù 2024)**: on BEIR, most implementations average nDCG@10 39.7-40 with Elasticsearch
  marginally higher (42.0 as extracted); stemming changes the average (39.7 vs 38.4 without),
  stopwords matter little on average but strongly on some datasets (TREC-COVID, ArguAna); subword
  tokenizers explain BM25-PT differences. observed (via HTML render): https://arxiv.org/html/2407.03618
- **Anserini/Pyserini**: one toolkit, pinned Lucene version, regression docs with expected scores;
  each Lucene major upgrade (7→8, 8→9) "changed slightly" all regression results; old numbers need
  old releases. reported: https://github.com/castorini/anserini (regressions, issue #1952),
  https://github.com/castorini/pyserini
- **MTEB**: dense retrieval evaluated by **exact** full-corpus search (`SearchEncoderWrapper`,
  chunked full-corpus top-k merge), not ANN. reported (issues):
  https://github.com/embeddings-benchmark/mteb/issues/5843 ,
  https://github.com/embeddings-benchmark/mteb/issues/4450 ; BEIR exact search: see RT10 record.
- **ann-benchmarks**: treats the ANN index as the object under test: per-library `config.yml`
  parameter grids, Docker per library, results per (dataset, algorithm, parameters), comparison on
  the recall/QPS Pareto frontier against exact ground truth. observed:
  https://github.com/erikbern/ann-benchmarks
- **HippoRAG 2**: holds the retriever fixed across structure-augmented baselines (NV-Embed-v2),
  reports passage recall@5, and uses **bm25s** for the BM25 baseline. observed:
  https://arxiv.org/html/2502.14802 (triplum's `HIPPORAG1` preset instead approximates HippoRAG 1's
  Elasticsearch analyzer.)

---

## 2. Facts: libraries that put search in the store

- **Haystack**: the `DocumentStore` Protocol has only `to_dict/from_dict`, `count_documents`,
  `filter_documents`, `write_documents`, `delete_documents`; **no search method**. Search lives on
  concrete stores (`InMemoryDocumentStore.bm25_retrieval(...)`), and each retriever is bound to one
  store class (`if not isinstance(document_store, InMemoryDocumentStore): raise TypeError`). Docs:
  "Retrievers are tightly coupled with Document Stores." observed:
  https://github.com/deepset-ai/haystack/blob/main/haystack/document_stores/types/protocol.py ,
  https://github.com/deepset-ai/haystack/blob/main/haystack/components/retrievers/in_memory/bm25_retriever.py ,
  https://docs.haystack.deepset.ai/docs/retrievers
  - Same-name-different-technique example: `PgvectorKeywordRetriever` ranks with Postgres
    `ts_rank_cd` (no IDF), unlike `ElasticsearchBM25Retriever`. observed:
    https://docs.haystack.deepset.ai/docs/pgvectorkeywordretriever
  - Hybrid in Python: `DocumentJoiner` modes concatenate, merge, RRF, distribution-based rank
    fusion; RRF uses `k = 61` ("60 was suggested by the original paper, plus 1 as python lists are
    0-based"). observed: https://github.com/deepset-ai/haystack/blob/main/haystack/components/joiners/document_joiner.py ,
    https://github.com/deepset-ai/haystack/blob/main/haystack/utils/misc.py
- **LlamaIndex**: one `VectorStoreQuery` object for all stores with `mode` in
  {default, sparse, hybrid, text_search, semantic_hybrid, svm, logistic/linear regression, mmr} and
  backend-specific fields accreting into it: `alpha` ("only for hybrid search"), `sparse_top_k`
  ("currently only used by postgres hybrid search"), `hybrid_top_k`. observed:
  https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/vector_stores/types.py
  - Postgres integration: `HYBRID` runs dense + `ts_rank` sparse, **concatenates and dedups by node
    id with no fusion scoring**; `alpha` is ignored with a warning ("postgres hybrid search does not
    support alpha parameter"); unsupported modes raise `ValueError`. observed:
    https://github.com/run-llama/llama_index/blob/main/llama-index-integrations/vector_stores/llama-index-vector-stores-postgres/llama_index/vector_stores/postgres/base.py
- **LangChain**: `VectorStore.search(query, search_type)` accepts only `similarity`,
  `similarity_score_threshold`, `mmr`; score normalisation via per-store relevance functions;
  filters and hybrid are per-integration kwargs. Hybrid in Python via `EnsembleRetriever`
  (weighted RRF, `c = 60`). observed:
  https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/vectorstores/base.py ,
  https://github.com/langchain-ai/langchain/blob/master/libs/langchain/langchain_classic/retrievers/ensemble.py
- **txtai**: scoring methods `bm25|tfidf|sif|pgtext|sparse|custom`; `pgtext` delegates to Postgres
  `ts_rank(vector, plainto_tsquery(...))`; hybrid fetches `limit * 10` from each leg and fuses in
  Python with weights. observed: https://neuml.github.io/txtai/embeddings/configuration/scoring/ ,
  https://github.com/neuml/txtai/blob/master/src/python/txtai/scoring/pgtext.py ,
  https://github.com/neuml/txtai/blob/master/src/python/txtai/embeddings/search/base.py
- **Vespa**: ranking is declared in the schema's rank profiles: first phase on content nodes,
  optional second phase over top hits, global phase in the container over the global top
  `rerank-count` (default 100) with `normalize_linear`, `reciprocal_rank`, `reciprocal_rank_fusion`.
  Hybrid and reranking are backend-native. observed: https://docs.vespa.ai/en/ranking/phased-ranking.html
- **Weaviate**: hybrid native; default fusion `relativeScoreFusion` since 1.24 (alt.
  `rankedFusion`); `alpha` 0 = keyword, 1 = vector; BM25 k1/b in the collection's
  `invertedIndexConfig`. observed: https://docs.weaviate.io/weaviate/search/hybrid
- **Elasticsearch** RRF retriever: `rank_constant` default 60, `rank_window_size` per-leg depth
  (page as extracted says default 10; I believe it tracks `size`, unverified), weighted RRF.
  observed: https://www.elastic.co/docs/reference/elasticsearch/rest-apis/retrievers/rrf-retriever
- **Pyserini**: separate searcher classes per index type (Lucene, Faiss), `HybridSearcher(dense,
  sparse)` with `alpha`, `k0` candidate depth and optional normalisation; and a fusion CLI over
  **TREC run files** (`--method rrf|interpolation|average|normalize`, `--rrf.k 60`, `--depth 1000`).
  observed: https://github.com/castorini/pyserini/blob/master/pyserini/fusion/__main__.py ,
  https://github.com/castorini/pyserini/blob/master/pyserini/search/hybrid/_searcher.py

---

## 3. Facts: ranked lists as the interchange

- **TREC run format** (trec_eval `trec_results`): `qid iter docno rank sim run_id`. trec_eval
  **ignores the rank column** and re-sorts by `sim`, "higher for the docs to be retrieved first",
  ties broken deterministically by docno. observed:
  https://github.com/usnistgov/trec_eval/blob/main/formats.c
- **ranx**: `Run` from dict `{qid: {docid: score}}` or files (TREC, JSON, Parquet, LZ4); `fuse()`
  over runs with 25 methods (RRF, CombSUM/MNZ, Borda, Condorcet, weighted sum, ...) and
  normalisations; `optimize_fusion()` tunes against train qrels. observed:
  https://amenra.github.io/ranx/run/ , https://amenra.github.io/ranx/fusion/
- **ir_metadata** (SIGIR 2022): metadata schema for run files organised by PRIMAD (Platform,
  Research goal, Implementation, Method, Actor, Data), embedded as `#` comment headers that
  trec_eval tolerates. observed: https://www.ir-metadata.org/ ; paper
  https://dl.acm.org/doi/10.1145/3477495.3531738
- Pyserini fusion consumes run files (above); Haystack/LangChain/txtai fuse in-process lists.

---

## 4. Inferences

**4.1 "BM25 on backend X" is not one technique.** (from 1.1) The sources show four independent
axes that change rankings: (a) the scoring function itself (ts_rank vs BM25; Qdrant sparse BM25
with a user-supplied `avg_len`); (b) where k1/b are fixed (hard-coded in FTS5/tantivy, at index
build in ParadeDB/pg_textsearch, per query in DuckDB/Qdrant full-text); (c) analysis (FTS5 strips
diacritics, DuckDB stems + 571 stopwords + drops non `[a-z]`, ES `standard` does neither);
(d) statistics scope and freshness (partition/shard/part-local, RLS-hidden rows counted, dead rows
and deleted docs counted until VACUUM/merge, one-byte length norms). Several backends cannot be
configured to match triplum's current `BM25Settings` at all (FTS5 and tantivy fix k1/b; ClickHouse
has no released ranking).

**4.2 Identical results across backends are achievable only in narrow cases.**
- Dense **exact** search: yes up to float precision and tie-breaking (scores are corpus-independent;
  MTEB's sharded-merge argument relies on this).
- Dense **ANN**: no by design; results depend on index params, build order, quantization defaults
  (ClickHouse bf16), and filter strategy. The community answer (ann-benchmarks) is to measure ANN
  as a recall-vs-cost tradeoff against exact ground truth, not to treat it as the same retriever.
- BM25: identical *effectiveness* within noise is plausible if analysis is controlled (Kamphuis;
  bm25s Table 3); identical *rankings* are not realistic across engines (norm quantization,
  IDF variants, deleted-doc counting). Pre-tokenizing in Python and feeding tokens (e.g. a
  whitespace tokenizer in the backend) removes axis (c) only where the backend allows it.
- Research practice therefore pins **one implementation and version** per baseline (Anserini's
  Lucene version, bm25s in HippoRAG 2) rather than claiming portability.

**4.3 The owner's hypothesis is supported, with a split.** Store-level choices determine first-stage
candidate generation, its filter semantics and its statistics; frameworks that hide this
(LlamaIndex's shared query object, LangChain's search_type) either accrete backend-specific fields or
silently degrade (LlamaIndex Postgres "hybrid" without fusion; `alpha` ignored). Haystack avoids
lossy shared query objects by giving each store its own retriever classes and keeping only CRUD in
the common protocol. The common surface that *does* survive across all of them is the output: a
ranked list of ids with scores.

**4.4 What composes over ranked lists, and the hidden couplings.**
- Backend-independent: rank fusion (RRF, CombSUM etc.), cross-encoder/LLM reranking (needs text, so
  hydrate by chunk id from the record store), evaluation (trec_eval/ranx/pytrec_eval over runs),
  oracle-passage (a run built from qrels, no retrieval), closed-book (empty run).
- Still coupled to retrieval: candidate depth per leg (`k0`, `depth`, `rank_window_size`,
  txtai's `limit*10`) changes fusion and reranking results and must be part of identity; score-based
  fusion needs comparable score scales (FTS5/pg_textsearch negate scores; ts_rank has no IDF);
  RRF constants differ (60 vs Haystack's 61) and so do tie rules; trec_eval re-sorts by score and
  breaks ties by docno, so a run file must carry "higher is better" scores and the producer's tie
  order is lost unless scores are made strictly decreasing.
- Not composable afterwards: viewer/ACL and collection eligibility (must be inside the index before
  ranking, per AGENTS.md and RT10), and statistics scope.

**4.5 Run files are a credible decoupling point for evaluation; less so for online pipelines.**
TREC/ranx runs are the de facto interchange between retrieval systems and evaluation/fusion tools
(trec_eval, ranx, Pyserini fusion), and ir_metadata shows how to attach run identity. For in-process
pipelines the same shape is just `list[RetrievalHit]` per query; the file is a serialisation.

**4.6 Experiment identity for backend retrieval should record** (from 1.1-1.3): backend and
extension/server version (Anserini's Lucene-upgrade drift), index build parameters (tokenizer,
k1/b if build-time, HNSW M/ef_construction, quantization), query-time parameters (k1/b if query-time,
ef_search, num_candidates, filter strategy), exact vs approximate, statistics scope, candidate depth,
and the indexed content digest. Hosted backends (Pinecone, ClickHouse Cloud) cannot pin versions;
that matches goals.md's "components that cannot honour a seed are recorded as such".

---

## 5. Candidate shapes for triplum (no recommendation)

All shapes keep `RecordStore` for records and the existing `Retriever` output (`list[RetrievalHit]`).
They differ in where indexes live and what is shared.

### S1. Backend-named retrievers, no shared index abstraction (Haystack-like)
Each technique+backend pair is its own class with its own settings model: `BM25s(store, settings)`,
`Fts5BM25(sqlite_store, Fts5Settings(tokenizer=..., column_weights=...))`,
`PgTextsearchBM25(pg_store, ...)`, `ExactDense(...)`, `PgvectorHNSW(..., ef_search=...)`. Only the
`Retriever` call is shared. A retriever may require a concrete store type.
- For: no lossy common settings; fingerprints carry exactly the backend's knobs; matches 4.1.
- Against: N×M classes; no machine check that `Fts5BM25` and `BM25s` mean "the same"; store-type
  coupling is explicit but rigid.

### S2. Indexes as store capabilities with backend-specific index specs
Stores implement extra capability Protocols beside `RecordStore` (e.g. lexical search, vector
search), each with a minimal call (`query, viewer, k` plus scope), while index *creation* takes a
backend-specific spec (`store.create_lexical_index(Fts5Spec(...))`) that the store owns and
fingerprints. Retrievers become thin or vanish.
- For: ACL/collection filters push down into one query naturally; index lifecycle and freshness
  belong to the component that sees writes; fits "store-managed indexes".
- Against: capability Protocols drift toward a lowest common denominator or toward LlamaIndex's
  accreting query object; several index configs per store need names; the Python reference (bm25s)
  becomes "a store" too, or stays outside the pattern.

### S3. Ranked list (run) as the only cross-backend contract
First-stage retrieval is backend-native and may be anything (Python, SQL, hosted). Its product is a
run: per query, ranked chunk ids with higher-is-better scores, plus run identity (ir_metadata-like).
Fusion, reranking (hydrating text from `RecordStore`), oracle, closed-book and evaluation consume
runs; benchmark tables are computed from runs.
- For: evaluation and late stages fully decoupled; interop with trec_eval/ranx/Pyserini for free;
  baselines (oracle/closed-book) are just runs.
- Against: does not by itself say how first-stage backends are built or configured (combine with
  S1 or S2); native in-backend hybrids (Vespa global phase, ES RRF retriever, ParadeDB SQL) are
  either one opaque first stage or reimplemented over runs; candidate depth must be explicit.

### S4. Reference semantics plus conformance tests
One Python reference per technique defines its meaning (bm25s with given tokens; numpy exact
cosine). Backend implementations declare which reference they claim and must pass an agreement
test on the 20-question fixture (identical top-k, or a stated tolerance) with tokenization applied
in Python where the backend permits. Non-conforming backends (ts_rank, Qdrant sparse with fixed
`avg_len`, FTS5 when k1/b differ) are labelled as distinct techniques.
- For: makes "same technique" a measured claim, not a name; catches silent degradations like the
  LlamaIndex hybrid example.
- Against: test and maintenance cost; tolerance choice is a judgment call; some useful backends never
  conform and need their own baseline rows.

### S5. Backend-native pipeline units (Vespa/ES-style)
A whole retrieval plan (filter, first stage, hybrid, maybe rerank) runs inside one backend and is
treated as one opaque retriever whose full plan/config is the identity; triplum recombines only
across units (fusion of units, external rerank, evaluation).
- For: realistic for deployment; best performance; uses backend strengths (filtered HNSW,
  global-phase fusion).
- Against: weak attribution of deltas to individual techniques, which is the project's research
  question; harder to hold the embedder/tokenizer fixed across compared pipelines.

Shapes combine: S3 is orthogonal to S1/S2 (how runs are produced), and S4 can sit on top of S1 or
S2.

---

## 6. Gaps and caveats

- ClickHouse BM25 (PR #117519) state checked via GitHub API today: open, unmerged.
- ES `rank_window_size` default and the adaptive kNN post-filter switch are from a search summary,
  not an opened page.
- ParadeDB statistics scope with filters/RLS was not found in docs; unknown.
- Kamphuis et al. conclusions are from abstract/summary; the full table was not read.
