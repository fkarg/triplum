# SQLite versus Neo4j for triplum: benchmark methodology

**Research cutoff: 2026-09-16.** Find the crossover across corpus size, query shape and permission selectivity; do not assume one exists. This compares storage implementations of the same GraphRAG pipeline, not whether GraphRAG beats ordinary RAG. Recommendations below are experimental choices, not measured results.

## 1. Neo4j baseline in 2026

Pin **Neo4j Community 2026.08.1**, released September 10, by Docker digest. Calendar versioning began in 2025.01; `2026.02` denotes a monthly release, not Cypher's version. [Releases](https://neo4j.com/deployment-center/), [versioning](https://neo4j.com/docs/operations-manual/current/introduction/).

| Component | Relevant boundary |
|---|---|
| Database editions | Community is GPLv3; Enterprise includes commercially licensed components. Community has one user database plus `system`. RBAC, property-based access control, multiple user databases, pipelined and parallel runtimes are Enterprise-only; Community uses the slotted runtime. Keep Enterprise an optional, separately labelled arm. |
| Python | Official `neo4j` driver **6.3.1**, September 15: license expression `Apache-2.0 AND Python-2.0`. `neo4j-graphrag` **1.19.0**, August 26: Apache-2.0. Use the driver underneath Store; importing this GraphRAG package must not change the comparison's retrieval pipeline. |
| Graph Data Science | GDS Community offers PageRank, personalised PageRank through `sourceNodes`, and Leiden, with a four-core limit and separate in-memory projections. OpenGDS source is GPLv3; distributed GDS also incorporates closed code. Check the actual plugin's bundled license and server compatibility. |

Sources: [database licensing](https://github.com/neo4j/neo4j), [edition matrix](https://neo4j.com/docs/cypher-manual/25/introduction/cypher-neo4j/), [driver](https://pypi.org/project/neo4j/6.3.1/), [GraphRAG package](https://pypi.org/project/neo4j-graphrag/1.19.0/), [GDS editions](https://neo4j.com/docs/graph-data-science/current/introduction/), [PPR](https://neo4j.com/docs/graph-data-science/current/algorithms/page-rank/), [Leiden catalog](https://neo4j.com/docs/graph-data-science/current/algorithms/community/), [GDS licensing](https://github.com/neo4j/graph-data-science).

Native vectors use HNSW. `SEARCH` appeared in 2026.01; filtered search became GA in 2026.02. Its internal `WHERE` filters declared indexed scalar properties; `IN` arrived in 2026.06. Conjunctions work, arbitrary `OR`/`NOT`, principal-list intersections and provenance traversals do not. An outer `WHERE` post-filters ANN candidates and can underfill top-k. Community stores embeddings as numeric lists; persisted native `VECTOR` properties require Enterprise/block format. Pin provider, quantization and search-expansion settings. [Vector indexes](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/), [SEARCH restrictions](https://neo4j.com/docs/cypher-manual/25/clauses/search/), [GA announcement](https://neo4j.com/blog/genai/vector-search-with-filters-in-neo4j-v2026-01-preview/).

Full-text indexes use Lucene, whose default scoring is BM25; this inference does not establish exact FTS5 scoring parity. Cypher 25 debuted in 2025.06, adding `LET`, `FILTER`, `NEXT`, conditional queries and repeatable-element matching; `ACYCLIC` followed in 2026.03. Explicitly select `CYPHER 25`. [Full-text](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/full-text-indexes/), [Lucene default](https://cwiki.apache.org/confluence/spaces/LUCENE/pages/119540990/LuceneFAQ), [Cypher changes](https://neo4j.com/docs/cypher-manual/25/deprecations-additions-removals-compatibility/).

Run one official Community Docker container with persistent `/data` and `/logs`, localhost Bolt and fixed CPU/RAM limits. Replace learning-oriented memory defaults: use `neo4j-admin server memory-recommendation --memory=<budget> --docker`, then tune heap and page cache. Reserve OS cache for vector/Lucene indexes and budget GDS projections separately. [Docker](https://neo4j.com/docs/operations-manual/current/docker/introduction/), [sizing command](https://neo4j.com/docs/operations-manual/current/configuration/neo4j-admin-memrec/), [memory guidance](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/).

## 2. What previous comparisons establish

| Evidence | Useful finding; limit on interpretation |
|---|---|
| [GRainDB, PVLDB 2022](https://www.vldb.org/pvldb/vol15/p1011-jin.pdf) | One-hop experiments sweep vertex/edge selectivity from 0.01–100%. Selective starting vertices favour Neo4j adjacency access; selective edges can favour relational joins. Filter placement and execution plans matter, not percentage alone. |
| [DuckPGQ, CIDR 2023](https://vldb.org/cidrdb/papers/2023/p66-wolde.pdf) | Analytical relational execution beats Neo4j on many pattern and batched shortest-path workloads. However, this used Neo4j 4.4.2 Enterprise, 48 vCPUs, 248 GB RAM and 16K endpoint pairs: not a small interactive SQLite comparison. |
| [Train Benchmark, 2017](https://d-nb.info/1125422319/34) | Real SQLite/MySQL/Neo4j graph-pattern and incremental-validation comparison. SQLite was competitive, but versions are obsolete and SQLite was excluded from its Java-heap memory comparison. |
| [rbench, 2019](https://dbs.informatik.uni-halle.de/rbench/) | SQLite/PostgreSQL/Neo4j recursive-query implementations and synthetic graph shapes; transitive closure is not bounded k-hop retrieval. |

SQL/PGQ does not imply recursive SQL execution: [DuckPGQ's VLDB demonstration](https://www.vldb.org/pvldb/vol16/p4034-wolde.pdf) combines relational pattern joins with on-demand CSR path kernels. This supports separating storage from graph-algorithm choice. Historical and system-author/vendor benchmarks motivate hypotheses; they cannot establish triplum's crossover. No contemporary controlled SQLite–Neo4j temporal/ACL crossover was verified.

[LDBC SNB Interactive](https://ldbcouncil.org/benchmarks/snb/interactive/) measures transactional neighbourhood workloads and updates; BI covers analytical patterns. Its audited table reports GraphScope Flex SF100 throughput of 79,244 on 2025-04-21, but this is a disclosed system result, not a portable baseline. The fetched Interactive and [BI](https://ldbcouncil.org/benchmarks/snb/bi/) tables contain no Neo4j result. Use their query definitions and disclosure discipline; do not invent an audited Neo4j-versus-Postgres ranking or compare unmatched machines.

[Han et al., “RAG vs. GraphRAG”, v3, March 2026](https://arxiv.org/html/2502.11371v3), Table 4, reports MultiHop-RAG storage of **127 MB RAG, 117 MB KG-GraphRAG, 165 MB Community-GraphRAG**. These compare representations, not database overhead. [Fan et al., “Do We Still Need GraphRAG?”, April 2026](https://arxiv.org/html/2604.09666v1), Appendix E, measures construction hours/dollars, retrieval time and context tokens; no disk-footprint measurement was found. Neither supplies a store crossover.

## 3. Workloads, equivalence and measurement

### Corpus and sweeps

Freeze 1,000 HotpotQA distractor questions and pool their ten passages each: approximately 10k passage occurrences, fewer unique passages after deduplication. Publish IDs and actual counts; this pooled task differs from the official ten-paragraph setting. Extract once, freeze provenance and bi-temporal facts, and load identical logical records and embeddings into both stores. [HotpotQA](https://hotpotqa.github.io/).

Generate approximately **100k and 1M passages** with fixed seeds. Disjoint ID-remapped copies are footprint/tie-stress controls only. For substantive vector/BM25 scaling, generate fresh text and embed once with a pinned model; publish duplicate rates, nearest-neighbour distance distributions and term-frequency distributions against HotpotQA. Separately generate cross-component links and degree-skew variants. Report document/chunk/entity/fact/support counts, degree quantiles, components and version multiplicity. Preserve original QA evidence; use synthetic variants primarily for performance, not new quality claims.

Define ACL selectivity as **fraction visible**, at **1%, 10%, 50%, 100%**, plus an unfiltered baseline. Apply permissions at documents; report resulting chunk/fact fractions. Cross random grants with community-correlated and hub-correlated grants, including queries whose best matches are hidden. Sweep 1/8/32 viewer principals and 1/4/16 supports per fact. Separate simple scalar tenant filters from full provenance-derived permissions.

| Query family | Concrete parameters and output |
|---|---|
| Vector chunks | Top-k 10/50/100; dimensions 384/768/1536; all ACL fractions and no ACL; exact versus HNSW, with ANN tuning curves. |
| BM25 chunks | Top-k 10/50/100; rare/common terms, conjunctions, short/long queries; same ACL sweep and fixed lexical contract. |
| Entity neighbourhood | Unique reachable entities/facts within 1/2/3 logical hops; incoming/outgoing/both; low/median/p99-degree seeds; predicate-restricted/unrestricted; current/historical as-of on both axes. |
| Seeded PPR | 1/8/32 seeds, uniform/weighted seeds; fixed damping 0.85 and residual target; full visible projection versus explicitly labelled bounded projection. |
| Predicate patterns | Fixed endpoint pair joined by 2/3/5 predicate steps; chains, diamonds and cycles; positive/negative cases. Return bindings or existence as distinct workloads. |
| Shortest path | Separate bounded shortest-distance queries at caps 3/6/10, including unreachable pairs; do not substitute enumeration of all paths. |
| Ingest | Full corpus; episodes of 1/100/1,000 documents; transaction batches of 100/1,000/10,000 records; isolated and concurrent-reader runs. |
| Invalidation | Close/replace 1/100/10,000 fact versions; revoke grants/remove supports; single-support versus multiple-support facts; measure commit and searchable/projection-ready time. |

### Equivalence gates

**Exact track:** compare both backends against an independent reference evaluator, not merely each other. Canonicalize IDs, endpoints, predicates, time intervals and visible support IDs; sort and compare sets/multisets according to the declared query contract. Fail on missing/extra records. Resolve top-k ties by stable ID; normalize numeric scores and use preregistered tolerances, initially `atol=1e-6, rtol=1e-5`. PPR must share transition weights, dangling-node handling and convergence semantics.

Use exact cosine over eligible vectors in both stores. For lexical equivalence, normalize tokens and use one BM25 formula/statistics policy over all eligible matching candidates; include this work in timings. Native FTS5 and Lucene differ in tokenization, IDF and score conventions, so common reranking of only their top-k cannot guarantee equivalence. [FTS5 BM25](https://www.sqlite.org/fts5.html#the_bm25_function), [Lucene BM25](https://lucene.apache.org/core/10_1_0/core/org/apache/lucene/search/similarities/BM25Similarity.html).

**Native-search track:** measure HNSW recall@k against exhaustive eligible-vector truth, underfilled-result rate, ranking overlap and QA differences. Synthetic copies introduce duplicate embeddings: report strict ID recall and tie-aware recall accepting eligible vectors at the kth-distance boundary. Native BM25 is also a separate ranking comparison. These results cannot be labelled identical-result speedups. Permission violations remain failures in both tracks.

Canonicalize context ordering and hold prompts, reranker, context budget and generator fixed. Replay cached generation for identical prompts; compare answer EM/F1 and supporting-passage recall. For native search, report paired confidence intervals and a preregistered quality margin, rather than claiming parity from nonsignificance. ACL cases lacking visible gold support are evaluated for correct abstention separately.

### Fair execution and crossover presentation

Use the same machine, storage and total RAM/CPU budget, one backend at a time. Prefer Linux or put both inside the same VM. Include client/serialization costs: Bolt versus embedded access is part of the deployment comparison; report server-only timing secondarily. Tune both using official guidance, with indexed IDs/endpoints/support/grants, SQLite statistics and deliberate WAL/durability settings. [SQLite tuning](https://www.sqlite.org/pragma.html#pragma_optimize), [WAL](https://www.sqlite.org/wal.html).

Warm indexes, OS caches, JVM and connections; exclude warm-up samples. Randomize paired query order, use five independent runs and at least 1,000 samples per read-query cell; repeat full builds separately. Sweep concurrency 1/4/16 and offered load; report p50/p95, completed queries/second, queueing, errors/timeouts, idle/peak process memory and total memory including filesystem cache. Measure database/index/log bytes, peak ingest disk, index-build time and time until fully queryable. Match durability; separate common transactional ingest from fastest bulk-loader arms. Exclude shared LLM extraction cost.

For PPR, first feed the **same CSR/petgraph kernel** from both stores; time visibility filtering, adjacency export, projection construction and kernel separately. Compare GDS additionally, including four-core restrictions and algorithm-equivalence checks. Sweep projection reuse 1/10/100 queries and cold/rebuilt projections after updates; charge cache maintenance and memory. Also replay fixed uniform and hot-viewer/as-of traces and report observed hit rates; controlled reuse sweeps alone do not predict operational cost.

Plot SQLite/Neo4j p95 ratios with confidence intervals against scale, faceted by hops, degree and ACL selectivity. Publish separate exact-scan/traversal crossovers and quality-gated native-search crossovers; ANN acceleration is not evidence of faster graph traversal. Add memory/disk and latency–recall frontiers. Preregister a primary query mix and material improvement, for example ≥20% lower p95 with the confidence interval excluding parity, at equivalent quality and resource budget. Treat other sweeps as exploratory; confirm selected crossings with held-out queries at adjacent scales and bootstrap whole runs. Publish the bracket and SLO, not a universal passage threshold.

## 4. Store protocol and visibility

Use stable application IDs and typed records/batches, not Cypher fragments, SQL expressions, Neo4j node IDs or GDS graph names. Require `Viewer(principals, valid_at, recorded_at, permission_revision)` on reads: `visible_facts(viewer)`, `neighbors(seeds,k,direction,predicates,viewer)`, `adjacency_batches(viewer)`, `vector_search(vector,k,filter,viewer)` and `bm25(query,k,filter,viewer)`. A typed predicate-path request handles patterns. Capabilities describe exactness/filter support; unsupported filters must fail or use a correct measured fallback.

A fact is visible iff both half-open time intervals contain the requested instants and at least one supporting document grants access. Each immutable fact version owns its support links; later evidence must not appear retroactively in earlier recorded views. The primary policy uses current grants: `permission_revision` validates the current ACL snapshot, not a historical permission request. SQL below assumes matching committed revisions and a request-local `viewer_principals` relation:

```sql
WHERE f.valid_from <= :v AND (f.valid_to IS NULL OR :v < f.valid_to)
  AND f.recorded_from <= :r AND (f.recorded_to IS NULL OR :r < f.recorded_to)
  AND EXISTS (
    SELECT 1 FROM fact_support s
    JOIN chunks c ON c.id = s.chunk_id
    JOIN document_grants g ON g.document_id = c.document_id
    JOIN viewer_principals p ON p.principal = g.principal
    WHERE s.fact_id = f.id
  )
```

An equivalent Cypher predicate on a reified `Fact` node is:

```cypher
WHERE f.valid_from <= $v AND (f.valid_to IS NULL OR $v < f.valid_to)
  AND f.recorded_from <= $r AND (f.recorded_to IS NULL OR $r < f.recorded_to)
  AND EXISTS {
    MATCH (f)-[:SUPPORTED_BY]->(:Chunk)<-[:HAS_CHUNK]-(d:Document)
          -[:GRANTED_TO]->(p:Principal)
    WHERE p.id IN $principals
  }
```

Use UTC integer timestamps consistently. Apply visibility at every expansion and before ranking/limiting; filter returned provenance too. Entities, names and aliases inherit visible-fact semantics. Count `Entity → Fact → Entity` as one logical hop. SQL recursive CTEs and Cypher quantified/variable-length paths have different duplicate and path-uniqueness semantics: explicitly bound depth and distinguish reachable sets from path enumeration. [SQLite recursion](https://www.sqlite.org/lang_with.html), [Cypher path modes](https://neo4j.com/docs/cypher-manual/25/patterns/acyclic-paths/).

Neither `SEARCH` nor sqlite-vec metadata filtering automatically pushes arbitrary ACL joins into vector ranking. Use a verified eligible-ID filter or exact scoring over eligible rows; measure permission compilation/materialization. Overfetch-and-postfilter is not a correctness guarantee. [sqlite-vec metadata](https://alexgarcia.xyz/sqlite-vec/features/vec0.html), [exact distance queries](https://alexgarcia.xyz/sqlite-vec/features/knn.html).

Batch writes and avoid unbounded path materialization: Neo4j transaction memory limits can terminate queries. Invalidation must atomically preserve recorded history, update support/grants and retire cached projections. Cache keys include graph revision, permission revision, viewer and both times. Validate monotonic graph/ACL revisions before and after concurrent retrievals; retry on change and charge retries. Compare results at replayed committed checkpoints. Test interval boundaries, revocation, hidden intermediates and read-after-write visibility; count stale retrieval as failure.

## 5. Decisions we recommend

- Community baseline; optional Enterprise and native-GDS arms clearly separated.
- Exact-result conformance gates before speed claims; native-search quality curves alongside them.
- Shared PPR kernel and full provenance ACLs as primary workloads.
- Controlled topology growth and measured projection lifecycle costs.

## 6. Open questions

- What latency SLO, concurrency, hardware budget and QA equivalence margin matter operationally?
- Should historical queries use current grants or historical grants? Recommend current grants so revocation persists.
- Must hidden documents also have zero influence on BM25 corpus statistics? That requires viewer-scoped statistics/indexes, beyond filtering returned rows.
- Verify the downloaded GDS artifact's exact license. Leiden availability is confirmed by the official algorithm catalog; its detailed page could not be fetched. Lucene BM25 use is inferred from documented defaults, not verified against the pinned Neo4j binary. No measured contemporary crossover is available from this research.

## Sources

Primary sources, accessed 2026-09-16; rolling documentation must be archived with the eventual benchmark manifest.

1. Neo4j: [releases](https://neo4j.com/deployment-center/), [versioning](https://neo4j.com/docs/operations-manual/current/introduction/), [license](https://github.com/neo4j/neo4j), [editions](https://neo4j.com/docs/cypher-manual/25/introduction/cypher-neo4j/).
2. Indexes: [vectors](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/), [SEARCH](https://neo4j.com/docs/cypher-manual/25/clauses/search/), [filtered-search GA](https://neo4j.com/blog/genai/vector-search-with-filters-in-neo4j-v2026-01-preview/), [full-text](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/full-text-indexes/).
3. Cypher: [changes](https://neo4j.com/docs/cypher-manual/25/deprecations-additions-removals-compatibility/), [path semantics](https://neo4j.com/docs/cypher-manual/25/patterns/acyclic-paths/).
4. GDS: [editions](https://neo4j.com/docs/graph-data-science/current/introduction/), [source/licensing](https://github.com/neo4j/graph-data-science), [PageRank/PPR](https://neo4j.com/docs/graph-data-science/current/algorithms/page-rank/), [Leiden catalog](https://neo4j.com/docs/graph-data-science/current/algorithms/community/) (catalog fetched; detailed algorithm page unavailable).
5. Python releases: [neo4j 6.3.1](https://pypi.org/project/neo4j/6.3.1/), [neo4j-graphrag 1.19.0](https://pypi.org/project/neo4j-graphrag/1.19.0/).
6. Operations: [Docker](https://neo4j.com/docs/operations-manual/current/docker/introduction/), [memory sizing](https://neo4j.com/docs/operations-manual/current/configuration/neo4j-admin-memrec/), [memory/transaction limits](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/).
7. Search implementations: [FTS5](https://www.sqlite.org/fts5.html#the_bm25_function), [Lucene default](https://cwiki.apache.org/confluence/spaces/LUCENE/pages/119540990/LuceneFAQ), [BM25Similarity](https://lucene.apache.org/core/10_1_0/core/org/apache/lucene/search/similarities/BM25Similarity.html), [sqlite-vec metadata](https://alexgarcia.xyz/sqlite-vec/features/vec0.html), [KNN](https://alexgarcia.xyz/sqlite-vec/features/knn.html).
8. SQLite: [recursive CTEs](https://www.sqlite.org/lang_with.html), [optimization](https://www.sqlite.org/pragma.html#pragma_optimize), [WAL](https://www.sqlite.org/wal.html).
9. Jin et al., 2022: [Making RDBMSs Efficient on Graph Workloads Through Predefined Joins](https://www.vldb.org/pvldb/vol15/p1011-jin.pdf).
10. Ten Wolde et al., 2023: [DuckPGQ analytical evaluation](https://vldb.org/cidrdb/papers/2023/p66-wolde.pdf), [SQL/PGQ demonstration](https://www.vldb.org/pvldb/vol16/p4034-wolde.pdf).
11. Szárnyas et al., 2017: [Train Benchmark](https://d-nb.info/1125422319/34); Brass/Wenzel, 2019: [rbench](https://dbs.informatik.uni-halle.de/rbench/).
12. LDBC: [SNB Interactive results](https://ldbcouncil.org/benchmarks/snb/interactive/), [SNB BI results](https://ldbcouncil.org/benchmarks/snb/bi/).
13. Han et al., 2026 revision: [RAG vs. GraphRAG](https://arxiv.org/html/2502.11371v3).
14. Fan et al., 2026: [Do We Still Need GraphRAG?](https://arxiv.org/html/2604.09666v1).
15. Yang et al.: [HotpotQA dataset and evaluation](https://hotpotqa.github.io/).
