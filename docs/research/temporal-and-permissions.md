# Bi-temporal facts and provenance-derived permissions in `triplum`

Research notes for the two first-class requirements: (1) bi-temporal facts with as-of queries on both
axes, (2) user visibility derived from document provenance, enforced in the store.

Status: research + recommendation. Nothing here is implemented yet.


> **Reconciliation with [`design.md`](design.md) (2026-09-16).** All ten recommended decisions below
> were adopted, with two adjustments: open interval ends use a max sentinel instead of NULL (see
> [`storage-sqlite.md`](storage-sqlite.md)), and invalidation is additionally *viewer-relative*: an
> older fact counts as invalidated only for viewers who can see the invalidating fact, otherwise a
> private correction would delete a public fact. Entity names, types, aliases and resolution merges
> are provenance-bound facts rather than columns, for the same reason.

---

## A. Temporal KG modelling in practice

### Graphiti / Zep — the reference implementation of bi-temporal edges

Zep (arXiv:2501.13956, Rasmussen et al., Jan 2025) is the paper most directly on point. Its engine
Graphiti stores four timestamps **on the edge**, not on the node, and the edge *is* the fact. Reading
`graphiti_core/edges.py` directly, `EntityEdge` carries:

```
uuid, group_id, source_node_uuid, target_node_uuid
name, fact, fact_embedding, attributes
episodes: list[str]          # provenance: which episodes produced this edge
created_at: datetime         # transaction time, open
expired_at: datetime | None  # transaction time, close
valid_at: datetime | None    # world time, open
invalid_at: datetime | None  # world time, close
reference_time: datetime | None
```

`valid_at`/`invalid_at` are extracted by an LLM from episode text against a `reference_time`, so
relative expressions ("two weeks ago") resolve. `created_at`/`expired_at` are set by the system.
Invalidation is non-destructive: on contradiction, `edge.invalid_at` is set to the new edge's
`valid_at` and `expired_at` is stamped once, but the edge and its embedding are retained so both
sides of a disagreement stay retrievable.

What it gets wrong or leaves out, for our purposes:

- **Invalidation has no provenance.** The invalidated edge records *that* it was invalidated, not
  *by what*. An edge closed by contradiction is indistinguishable after the fact from one whose
  validity simply lapsed; downstream code resorts to heuristics like pairing `a.invalid_at == b.valid_at`.
  This is reported as an open gap in the project's own issue tracker.
- **No as-of query on transaction time.** Graphiti documents point-in-time retrieval on the *valid*
  axis. `expired_at` exists but the retrieval path is not built around "reconstruct what the graph
  believed on date S", which is exactly the audit question bi-temporality is supposed to answer.
- **Provenance is a flat list.** `episodes: list[str]` cannot express that a fact required *two*
  sources jointly versus being supported by *either* one. That distinction is load-bearing once
  provenance drives visibility (see §C).
- **No permission model at all.** `group_id` is a partition, not an ACL; a partition is per-graph,
  not per-principal, and it does not compose (a document readable by two overlapping groups has no
  representation).

### ATOM — dual-time 5-tuples

ATOM (arXiv:2510.22590, Lairgi et al., Oct 2025; v2 Jan 2026), from the iText2KG authors and shipped
in the same repo (`AuvaLab/itext2kg`), decomposes documents into *atomic facts* first, then extracts
5-tuples, and explicitly does "dual-time modeling that distinguishes between when information is
observed and when it is valid" — i.e. observation time vs validity time, which is our recorded-vs-valid
split. It merges per-document "atomic TKGs" in parallel, targeting exhaustivity, stability and latency
against iText2KG and Graphiti, which it criticises for splitting entity and relation extraction into
separate LLM passes.

The atomic-fact decomposition step is the transferable idea: a compound sentence yields one tuple per
atomic claim, which makes both the validity interval and the supporting span unambiguous. It is hard
to attach a single `valid_from`/`valid_to` to a fact extracted from a sentence asserting three things.

### Temporal QA / TKG benchmarks worth tracking

| Benchmark | What it tests | Reference |
|---|---|---|
| TimeQA | as-of correctness over time-evolving WikiData facts; best model 46% vs human 87% | arXiv:2108.06314 (NeurIPS 2021 D&B) |
| TempReason | L1/L2/L3 temporal reasoning tiers, 998–2023 range, built to defeat TempLAMA's shortcut bias | arXiv:2306.08952 |
| TIQ | 10k questions with *implicit* time constraints ("during the Cold War") over KB + text + infobox | WWW '24 Companion, doi:10.1145/3589335.3651895 |
| ComplexTempQA | ~100M QA pairs; across-time comparison, temporal aggregation, multi-hop ordering | arXiv:2406.04866 (EMNLP) |
| Test of Time (ToT) | fully synthetic, so no pretraining contamination; isolates graph structure, fact order, question type | arXiv:2406.09170 |
| TGB 2.0 | future-link prediction on large multi-relational temporal graphs (up to 53M edges); fixes inconsistent TKG evaluation | arXiv:2406.09639 (NeurIPS 2024 D&B) |
| ECT-QA (TG-RAG) | time-sensitive QA over earnings calls with an **incremental update protocol**: evaluate before and after ingesting a new time slice; released as HF `austinmyc/ECT-QA` (MIT, ungated): 480 transcripts split old/base/new, 1,005 local + 100 global questions, 261 unanswerable | arXiv:2510.13590 |

ECT-QA's incremental protocol is the one closest to our episodic-ingestion requirement: split the
corpus into a base period and an increment, then measure both answer quality and update cost/stability
across the boundary. For orientation across the field, Piryani et al.'s temporal IR/QA survey
(arXiv:2505.20243, rev. 2026) is the current map.

None of these evaluate transaction-time as-of ("what did the system believe last March"), and none
model a viewer. Viewer-conditional benchmarks do exist in adjacent modalities (GateMem for
conversational memory, RBAC-Text2SQL for SQL); see [`benchmarks.md`](benchmarks.md) §4.2.

### Standards and store conventions

- **SQL:2011** is the right design reference. It defines application-time periods (valid time) and
  `PERIOD FOR SYSTEM_TIME` (transaction time); a table with both is bitemporal. Crucially it models
  periods as *metadata over two ordinary columns*, not a new period datatype — which is exactly what
  we should do in SQLite, which has no interval type. Its update semantics are the ones to copy:
  system-time rows are never overwritten; an update closes the old version's period and inserts a new
  one. Implemented in SQL Server, DB2, MariaDB; absent in PostgreSQL and SQLite.
- **RDF 1.2 / RDF-star** now routes statement-level annotation through *triple terms* used as the
  object of an `rdf:reifies` triple, whose subject is a *reifier*; you attach `valid_from` to the
  reifier, not to the triple. This is a clean formal model for "annotate an edge with validity and
  provenance", and it is the interoperability target if we ever export RDF. But the specs are still
  Working Drafts (Turtle WD dated 2026-09-14) with open semantics issues about what reifiers mean, so
  it is an export format, not an internal model.
- **Property graphs (Neo4j/Cypher)** just store `validFrom`/`validTo` as `ZONED DATETIME` properties
  on relationships — no reification needed, which is the practical convention. One real footgun:
  named IANA zones are resolved to a UTC instant at write time, and if the zone database changes the
  local rendering shifts. Store UTC instants; keep the original zone as a separate string if needed.

**Common failure mode across existing systems:** invalidation without provenance, and validity without
a transaction axis. Systems record that a fact stopped being true but not who said so or when we
learned it, which makes the history unauditable and — more importantly for us — makes it impossible to
recompute visibility, because visibility depends on which *documents* supported the fact.

---

## B. Permission-aware retrieval

### How production systems actually do it

The industry converges on one pattern: **denormalise principals onto the indexed unit and filter
inside the search, never after it.**

- **Elasticsearch/OpenSearch DLS/FLS**: a role carries a Query-DSL filter, optionally Mustache-templated
  with `{{_user.username}}`, matched against an `acl` field on the document. Multiple roles combine with
  OR. Two traps: a role with no DLS clause grants access to *everything*, and FLS that hides the ACL
  field silently breaks the DLS query that reads it.
- **Azure AI Search**: the classic form is "security trimming" — a filterable `group_ids` field ANDed
  into the query filter. Since 2025-05-01-preview there is a native `permissionFilter` field type
  (`userIds`, `groupIds`, `rbacScope`) plus `permissionFilterOption` at index level; the caller's Entra
  token goes in `x-ms-query-source-authorization` and the service appends the trim filter itself. Their
  doc guidance — `filterable: true`, `retrievable: false` — is worth copying: permissions should be
  filterable but never selectable.
- **Qdrant / Weaviate**: tenant/ACL values as payload, with the filter evaluated *inside* HNSW
  traversal. Qdrant recommends a single collection with an indexed tenant payload (`is_tenant=true`
  builds per-tenant sub-indexes and physically co-locates) over collection-per-tenant. Weaviate makes
  isolation structural — shard per tenant — and explicitly advises against hand-rolled filtering in
  application code. Both vendors are clear that tenant partitioning is *not* an authorization system.
- **Neo4j**: role-based sub-graph privileges on label/relationship-type/property, plus property-based
  access control (`GRANT READ {*} ON GRAPH g FOR (n:Post) WHERE n.secret <> true`). Note `TRAVERSE`
  gates `READ` — you cannot read properties on nodes you cannot find, which is the right default.
  As of the 2026.07 docs PBAC supports READ privileges only, and is unsupported on sharded property
  databases.
- **Zanzibar / OpenFGA / SpiceDB** are the right model when permissions are *relational* (folder
  inheritance, group nesting, sharing) rather than a flat list. The retrieval integration has two
  shapes: `BatchCheck` post-filter (over-fetch 2–3× and drop), or `ListObjects` pre-filter (materialise
  the accessible set, intersect). Pinecone's guidance: post-filter when hit-rate is high, pre-filter
  when the corpus is large and hit-rate low, noting `ListObjects` is the more expensive call. Ory's
  `rerag-rebac` is an existing Zanzibar-style + SQLite-vector implementation worth reading.

Academically the space is thin. The clearest paper is *Permission-Aware RAG: IAM-Based Access Filtering
in Multi-Resource Environments* (Jeong & Lee, IEEE Access 13:192819–192835, 2025), which validates each
retrieved document against the source provider's native IAM rather than merging RBAC/ABAC policies into
one store — arguing policy merging is where leakage gets introduced. They explicitly note the KG
approach requires continuous synchronisation of node-level access attributes, which is precisely the
problem §C tries to eliminate by *deriving* visibility instead of storing it.

### Leakage channels

1. **Embeddings.** An embedding of a restricted chunk is, for practical purposes, the chunk. Vec2Text
   (Morris et al., arXiv:2310.06816) reconstructs text from black-box embeddings — reported ~92% exact
   recovery at 32 tokens — and the reproducibility study (arXiv:2507.07700) confirms it. Consequence:
   embeddings are not a safe projection, the vector must be excluded from any filtered-out row's
   response, and embeddings must never be `retrievable` to a client.
2. **Graph neighbours.** The one channel a document-level ACL misses entirely. If an entity node is
   returned because a *visible* fact touches it, but its neighbourhood/degree/type were computed over
   the union graph, the shape of the graph leaks restricted facts. Everything returned must be derived
   only from visible facts.
3. **Community summaries.** GraphRAG (arXiv:2404.16130) pregenerates Leiden-community summaries over
   the whole corpus and answers global queries by map-reducing over them. A summary computed over the
   union graph is an aggregate of documents the viewer cannot read; so is the community *partition*
   itself. There is no post-hoc fix — the summary text is already contaminated.
4. **Corpus statistics.** Global BM25/IDF over a mixed corpus leaks the existence and rough frequency
   of restricted terms. Qdrant documents this for payload-filtered multitenancy and exposes an `idf`
   parameter to narrow the statistics corpus.
5. **LLM-side caches and memory.** Prompt caches keyed across users, and agent memory that writes
   conclusions derived from privileged context back into a shared graph. Rule: extracted output
   inherits the ACL of its inputs and may never widen it.

### Filtered-ANN performance cliffs

Restrictive filters fragment the HNSW graph and break traversal connectivity. Post-filtering fails
first — Weaviate's own experiments concluded it "is not viable if you want to address filters of all
levels of restrictiveness". ACORN-style search-time expansion (stepping through filtered-out neighbours)
fails second: Vespa reports that from 80–95% filtered they avoid the latency spike with no significant
recall drop, but from 95–99% latency stays low "at the cost of a significant drop in recall". The robust
combination is index-time edge augmentation (Qdrant's filterable HNSW builds per-payload-value subgraphs
and merges them, ≤2× edges regardless of category count) plus a cardinality-aware planner that falls
back to brute force below a threshold.

For us this is less acute than it sounds: **sqlite-vec has no ANN — it brute-force scans** — so
pre-filtering is not a recall risk, it is the only performance lever. Its `PARTITION KEY` columns are
pre-filtered before any vector comparison; ordinary metadata columns still visit every row.

---

## C. Recommendation for `triplum`

### Schema

```
document(doc_id PK, uri, source_type, content_hash,
         doc_time,            -- world time the document is about/published
         recorded_at,         -- system time we ingested it
         superseded_by,       -- nullable doc_id
         acl_hash)            -- hash of sorted principal set, for bucketing

doc_grant(doc_id, principal_id, granted_at, revoked_at NULL, PRIMARY KEY(doc_id, principal_id, granted_at))
         -- ACLs are themselves system-versioned; revocation closes, never deletes

chunk(chunk_id PK, doc_id FK, ordinal, char_start, char_end, text, recorded_at)
chunk_vec(chunk_id, embedding)          -- sqlite-vec vec0, partition key = acl_hash

entity(entity_id PK, canonical_name, type, recorded_at)
       -- NO acl column. Visibility is derived, never stored on the entity.

fact(fact_id PK, subject_id, predicate, object_entity_id NULL, object_literal NULL,
     fact_text, confidence,
     valid_from, valid_to,               -- world time; NULL = unbounded
     recorded_at, invalidated_at,        -- system time; NULL = still believed
     invalidated_by_fact_id,             -- provenance of the invalidation
     support_group_count)

fact_support(fact_id, group_no, chunk_id, extractor, extracted_at,
             PRIMARY KEY(fact_id, group_no, chunk_id))
       -- a fact is supported by ANY group; a group requires ALL its chunks
```

Three deliberate departures from Graphiti:

- `invalidated_by_fact_id` — closes the invalidation-provenance gap.
- `fact_support.group_no` — a single-source fact has one group of one chunk; a fact inferred by joining
  two documents has one group of two chunks. Visibility is then **ANY group fully visible**, which is
  the only correct semantics: if a fact only exists because you combined a public and a secret document,
  the public document alone does not justify showing it.
- `acl_hash` on document and vector rows — the pre-filter key.

### Visibility predicate (SQLite)

```sql
-- Facts visible to :principals (JSON array), as believed at :as_of_system,
-- about the world at :as_of_valid.
WITH viewer(principal_id) AS (SELECT value FROM json_each(:principals))
SELECT f.*
FROM fact f
WHERE f.recorded_at    <= :as_of_system
  AND (f.invalidated_at IS NULL OR f.invalidated_at > :as_of_system)
  AND (f.valid_from    IS NULL OR f.valid_from     <= :as_of_valid)
  AND (f.valid_to      IS NULL OR f.valid_to        > :as_of_valid)
  AND EXISTS (                                   -- some support group fully visible
        SELECT 1 FROM fact_support fs
        WHERE fs.fact_id = f.fact_id
        GROUP BY fs.group_no
        HAVING COUNT(*) = SUM(
          EXISTS (SELECT 1
                  FROM chunk c
                  JOIN doc_grant g ON g.doc_id = c.doc_id
                  JOIN viewer v    ON v.principal_id = g.principal_id
                  WHERE c.chunk_id = fs.chunk_id
                    AND g.granted_at <= :now
                    AND (g.revoked_at IS NULL OR g.revoked_at > :now)))
      );
```

Note the asymmetry, which is the single most important correctness point here:
**`:as_of_system` rewinds the fact timeline; `:now` is used for ACLs.** Rewinding transaction time must
not resurrect a revoked grant. Use `:now = :as_of_system` only in an explicit, separately authorised
audit mode.

Entity visibility follows for free — `SELECT DISTINCT subject_id/object_entity_id FROM <visible facts>` —
and is never stored.

### Making it fast enough to be the filter, not a post-filter

Materialise the predicate's ACL half as a closure table, refreshed on ingest and on grant change:

```
fact_principal(principal_id, fact_id)   -- PK(principal_id, fact_id), covering index
```

This is the Zanzibar `ListObjects` / Elasticsearch-DLS-terms pattern. Retrieval then becomes:

- **Vector**: sqlite-vec `vec0` table partitioned by `acl_hash`, `WHERE acl_hash IN (:viewer_buckets)`
  so the scan is pre-filtered, then join `fact_principal` for exactness. Partition key is a coarse,
  sound over-approximation; the join is the authoritative check.
- **BM25 (FTS5)**: keep a dedicated `acl` column in the FTS5 table containing principal tokens, and AND
  it into the query: `MATCH '(' || :q || ') AND acl:(p_alice OR g_eng)'`. Same idea as Azure's
  `group_ids` filter, but it rides the existing inverted index. Cost: an ACL change reindexes that row.

Both are store-layer. No path returns a row the predicate excludes, and no embedding leaves the store
for an excluded row.

### Communities and summaries

Do not build principal-scoped communities in v1. The options, in order of what we should actually do:

1. **v1: no global/community summaries.** Ship fact-level + entity-neighbourhood retrieval only, where
   the predicate is exactly enforceable. This is the honest position — a GraphRAG global summary over a
   permissioned corpus is unfixable after the fact.
2. **v2: bucket by `acl_hash` closure.** Real corpora have far fewer distinct principal sets than
   principals. Compute communities and summaries per distinct ACL bucket (or per union-closure of the
   buckets a viewer can reach), cache keyed on the hash of the visible fact-id set. Bounded by the
   number of *observed* ACL sets, not by `2^principals`. We must measure the bucket cardinality on real
   data before committing.
3. **Rejected: summarise once, redact at query time.** The summary already mixes restricted content;
   redaction is post-hoc filtering, which the requirement forbids.

### Evaluating this

No published benchmark combines valid time, transaction time and a viewer, and none applies a
viewer predicate to *documents under retrieval*. The closest artefacts: ECT-QA's incremental-update
protocol (temporal only); TIQ/TimeQA/ToT (temporal only); ARBITER (Lorenzo et al.,
arXiv:2512.20535, Dec 2025), which builds a *synthetic* RBAC corpus precisely because real
enterprise data cannot be shared and existing NLP datasets lack role–permission structure, and
evaluates role-aware retrieval on 389 queries (85% accuracy / 89% F1 on query filtering), but has
released no data and by its own statement covers neither temporal access restrictions nor role
inheritance; and GateMem (arXiv:2606.18829, CC BY 4.0, released), which is conversational memory
rather than document retrieval but already has principals with roles, an `as_of_turn_id` prefix
cut that behaves like transaction time within an episode, canary `leak_targets`, and
answer/refuse/answer_redacted/no_memory as four distinct expected actions. Four of the design
points below therefore have prior art in GateMem and should cite it rather than claim novelty. So
we build one, for the document-retrieval modality and the bi-temporal axis that nothing covers.

**Generator.** Scripted entity timelines (employer, role, price, address) with state changes at known
world times. Each change is reported by 1–3 documents at *report* times that lag, and sometimes
retro-correct, the world time. Each document gets a principal set drawn from a small lattice
(individuals, groups, nested groups) so `acl_hash` cardinality is controlled and measurable. Every
restricted document carries a unique **canary nonce** — exact leakage detection, no judge needed.

**Question families**, each with a gold answer that is a function of `(as_of_valid, as_of_system, viewer)`:

1. World-time as-of: "who was X's employer in March 2024?"
2. System-time as-of: "what did we believe about X on 2024-06-01?" — answer differs from (1) wherever a
   later document retro-corrected.
3. Viewer-conditional: identical question, different gold answer per principal, because the supporting
   document differs.
4. Must-refuse: answer derivable only from invisible documents → gold is "I don't know".
5. Joint-support: fact requires chunks from a visible *and* an invisible document → gold is refuse.
   This is the test that catches the flat-`episodes` model.
6. Revocation: grant revoked after ingestion; a question answerable last week must now refuse.
7. Invalidation-provenance: "why do we no longer believe Y?" → requires `invalidated_by_fact_id`.

**Metrics.**

- *Retrieval-level leakage rate* — did any chunk failing the predicate enter the candidate set? This is
  the metric that matters for the store layer, it is LLM-independent, and its target is exactly zero.
- Canary leakage rate in generated answers.
- As-of accuracy, separately per axis (a system that only does valid time scores ~0 on family 2).
- Refusal precision and over-refusal rate on families 4–6 — over-refusal is a real regression, not a
  safe default.
- Viewer-consistency: for a fixed question, the set of answers across viewers must be monotone in the
  principal lattice (more permissions ⇒ superset of derivable facts). A violation is a bug even when no
  single answer looks wrong.
- Incremental-update cost, ECT-QA style, measured before and after ingesting a new time slice.

---

## Decisions we recommend

1. **Four timestamps on the fact, SQL:2011 semantics.** `valid_from`/`valid_to` (world), `recorded_at`/
   `invalidated_at` (system). Closed-open intervals, UTC instants, NULL = unbounded. Never delete,
   never overwrite.
2. **`invalidated_by_fact_id` is mandatory** whenever invalidation is caused by a contradiction. Fixes
   the gap Graphiti has.
3. **Provenance as support groups, not a flat list.** Visible iff ANY group is FULLY visible.
4. **No ACL column on entities or facts.** Visibility is derived from `fact_support → chunk → document
   → doc_grant`, and materialised into `fact_principal` purely as an index.
5. **System-versioned grants; as-of rewinds facts, not permissions.** `:now` for ACLs unless in an
   explicitly authorised audit mode.
6. **Filter in the store.** sqlite-vec partitioned on `acl_hash` + `fact_principal` join; FTS5 with an
   `acl` token column ANDed into the MATCH. Never post-filter, never return embeddings for excluded rows.
7. **No community summaries in v1.** Fact-level and entity-neighbourhood retrieval only. Revisit with
   `acl_hash`-bucketed summaries once we have measured bucket cardinality on real data.
8. **Atomic-fact decomposition before tuple extraction** (ATOM's Module-1), so validity intervals and
   supporting spans are unambiguous.
9. **Build the synthetic temporal+ACL benchmark before the retrieval layer**, and gate on
   retrieval-level leakage = 0.
10. **RDF 1.2 reifiers as an export target only**, not the internal model — the spec is still a WD.

## Open questions

- **ACL-bucket cardinality.** The v2 community plan lives or dies on how many distinct principal sets a
  real corpus has. Unknown; needs measurement before design.
- **Do we need ReBAC?** Flat principal lists cover "document carries principals". Folder inheritance,
  sharing and nested groups push toward Zanzibar. Do we expand relationships into principal sets at
  ingest (simple, stale on group change) or call out to an OpenFGA-style service at query time
  (correct, adds a dependency and a `ListObjects` cost)?
- **ACL change amplification.** Revoking a group grant invalidates `fact_principal` rows, the FTS5 `acl`
  column, and `acl_hash` partitions. What is the acceptable propagation latency, and is it allowed to be
  eventually consistent? (It probably is not.)
- **Do we need transaction-time as-of on the ACL at all**, or is audit mode a separate offline tool?
- **Conflicting valid intervals from equally-trusted sources** — Graphiti resolves by recency. Do we
  keep both and return a disagreement, which the schema permits but the retrieval contract does not yet?
- **Corpus-statistics leakage** via global IDF: real risk or acceptable? Qdrant treats it as real.
- **Rust boundary.** Interval-overlap indexing and the `fact_principal` closure maintenance are the two
  plausible hot spots; neither is proven hot yet.

---

## Sources

Temporal modelling and systems
- Zep: A Temporal Knowledge Graph Architecture for Agent Memory — https://arxiv.org/abs/2501.13956
- Graphiti source, `graphiti_core/edges.py` — https://github.com/getzep/graphiti/blob/main/graphiti_core/edges.py
- Graphiti bi-temporal data model docs — https://docs.getzep.com/graphiti/core-concepts/temporal-model
- Zep blog, "Beyond Static Knowledge Graphs" — https://blog.getzep.com/beyond-static-knowledge-graphs/
- Graphiti issue #1489, historical-backfill temporal-correctness gaps — https://github.com/getzep/graphiti/issues/1489
- ATOM: AdapTive and OptiMized dynamic temporal KG construction using LLMs — https://arxiv.org/abs/2510.22590
- iText2KG / ATOM code — https://github.com/AuvaLab/itext2kg
- RAG Meets Temporal Graphs (TG-RAG, ECT-QA) — https://arxiv.org/abs/2510.13590 · code https://github.com/hanjiale/Temporal-GraphRAG
- From Local to Global: A Graph RAG Approach (GraphRAG) — https://arxiv.org/abs/2404.16130

Benchmarks
- TimeQA — https://arxiv.org/abs/2108.06314
- TempReason — https://arxiv.org/abs/2306.08952
- TIQ — https://dl.acm.org/doi/10.1145/3589335.3651895 · code https://github.com/zhenjia2017/TIQ
- ComplexTempQA — https://arxiv.org/abs/2406.04866
- Test of Time — https://arxiv.org/abs/2406.09170 · data https://huggingface.co/datasets/baharef/ToT
- TGB 2.0 — https://arxiv.org/abs/2406.09639
- It's High Time: A Survey of Temporal QA — https://arxiv.org/abs/2505.20243

Standards and stores
- SQL:2011 temporal features survey — https://illuminatedcomputing.com/posts/2019/08/sql2011-survey/
- SQL Server temporal tables — https://learn.microsoft.com/en-us/sql/relational-databases/tables/temporal/overview
- MariaDB bitemporal tables — https://mariadb.com/docs/server/reference/sql-structure/temporal-tables/bitemporal-tables
- RDF 1.2 Concepts and Abstract Syntax — https://www.w3.org/TR/rdf12-concepts/
- RDF 1.2 Turtle (WD 2026-09-14) — https://www.w3.org/TR/rdf12-turtle/
- Cypher temporal values — https://neo4j.com/docs/cypher-manual/current/values-and-types/temporal/
- sqlite-vec metadata, partition keys, auxiliary columns — https://alexgarcia.xyz/blog/2024/sqlite-vec-metadata-release/index.html
- sqlite-vec + FTS5 hybrid search — https://alexgarcia.xyz/blog/2024/sqlite-vec-hybrid-search/index.html

Permissions and retrieval
- Elasticsearch document-level security — https://www.elastic.co/docs/deploy-manage/users-roles/cluster-or-deployment-auth/controlling-access-at-document-field-level
- Azure AI Search document-level access control — https://learn.microsoft.com/en-us/azure/search/search-document-level-access-overview
- Azure AI Search Entra-based document security announcement — https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/announcing-enterprise-grade-microsoft-entra-based-document-level-security-in-azu/4418584
- Qdrant multitenancy — https://qdrant.tech/documentation/manage-data/multitenancy/
- Weaviate multi-tenancy architecture — https://weaviate.io/blog/weaviate-multi-tenancy-architecture-explained
- Neo4j property-based access control — https://neo4j.com/docs/operations-manual/current/authentication-authorization/property-based-access-control/
- Neo4j read privileges — https://neo4j.com/docs/operations-manual/current/authentication-authorization/privileges-reads/
- Zanzibar (USENIX ATC 2019) — https://www.usenix.org/system/files/atc19-pang.pdf
- OpenFGA RAG authorization — https://openfga.dev/docs/use-cases/rag-authorization
- Pinecone, RAG with access control — https://www.pinecone.io/learn/rag-access-control/
- Ory rerag-rebac (Zanzibar-style ReBAC + SQLite vectors) — https://github.com/ory/rerag-rebac
- Permission-Aware RAG (IEEE Access 2025) — https://ieeexplore.ieee.org/document/11224764/

Leakage and filtered ANN
- Text Embeddings Reveal (Almost) As Much As Text (vec2text) — https://arxiv.org/abs/2310.06816 · code https://github.com/jxmorris12/vec2text
- Reproducibility study of vec2text — https://arxiv.org/abs/2507.07700
- Weaviate, effects of filtered HNSW searches on recall and latency — https://towardsdatascience.com/effects-of-filtered-hnsw-searches-on-recall-and-latency-434becf8041c/
- Qdrant, filterable HNSW without recall loss — https://qdrant.tech/articles/filterable-hnsw/
- Qdrant, what ACORN fixes and what fixes ACORN — https://qdrant.tech/articles/filtered-vector-search-acorn/
- Vespa, ACORN-1 and adaptive beam search — https://blog.vespa.ai/additions-to-hnsw/
- ARBITER: AI-Driven Filtering for Role-Based Access Control — https://arxiv.org/abs/2512.20535
