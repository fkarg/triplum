# Record types (draft for owner review)

Status: proposal. Nothing here is approved until the owner decides each item; decisions are
recorded under "Decisions" as they are made.

## Research summary

Primary sources fetched for the original draft (the research summary itself was not peer-reviewed):

| System | Data model essentials | Sources |
|---|---|---|
| Microsoft GraphRAG | documents, text_units (one document each since v3), entities (merged by title, LLM description), relationships, covariates/claims (only valid-time notion), communities (hierarchical Leiden: hard partition per level, one parent), community_reports. Default vectors: entity description, text unit, community report. No namespace field. | [outputs](https://microsoft.github.io/graphrag/index/outputs/), [breaking changes](https://github.com/microsoft/graphrag/blob/main/breaking-changes.md), [local](https://microsoft.github.io/graphrag/query/local_search/), [global](https://microsoft.github.io/graphrag/query/global_search/), [DRIFT](https://microsoft.github.io/graphrag/query/drift_search/) |
| RAPTOR | Tree of LLM summaries over 100-token leaves; soft clustering (several parents); per-node dict of embeddings by model; best mode is the collapsed tree (summaries and chunks in one vector space). | [paper](https://arxiv.org/html/2401.18059) |
| LightRAG | KV/vector/graph/doc-status storages; chunk `{content, full_doc_id, chunk_order_index}`; entities merged by name; edges with keywords for high-level retrieval; `workspace` string for isolation; descriptions rewritten in place. | [paper](https://arxiv.org/html/2410.05779) |
| HippoRAG 2 | Phrase and passage nodes; relation, synonym (similarity ≥ 0.8) and context edges; Personalized PageRank; entities never merged, linked by synonym edges. | [paper](https://arxiv.org/html/2502.14802) |
| Zep/Graphiti | Episodes (raw input, `valid_at`), entities, fact edges with `valid_at/invalid_at` (valid time) and `created_at/expired_at` (transaction time), communities per `group_id`; invalidation does not point at the invalidating fact. | [paper](https://arxiv.org/html/2501.13956), [namespacing](https://help.getzep.com/graphiti/core-concepts/graph-namespacing) |
| LlamaIndex | Node relationships SOURCE/PREVIOUS/NEXT/PARENT/CHILD; hierarchical parser indexes leaves, auto-merging retriever swaps in parents; property graph with MENTIONS edges. | [schema](https://developers.llamaindex.ai/python/framework-api-reference/schema/), [property graph](https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/) |
| LangChain | ParentDocumentRetriever (children in vector store, parents in KV store); MultiVectorRetriever indexes each extra representation as its own vector. | `langchain_classic/retrievers/` source |
| Qdrant / Weaviate / pgvector | Qdrant: one collection with an indexed tenant field, named vectors per point. Weaviate: shard per tenant, no cross-tenant queries. pgvector: filtering happens after the approximate index scan unless partitioned, partial-indexed or iterative. | [Qdrant partitions](https://qdrant.tech/documentation/guides/multiple-partitions/), [Qdrant vectors](https://qdrant.tech/documentation/concepts/vectors/), [Weaviate](https://docs.weaviate.io/weaviate/manage-collections/multi-tenancy), [pgvector](https://github.com/pgvector/pgvector) |

Unverified: DRIFT's exact inputs; whether GraphRAG isolates indexes by output directory; Mem0
record fields.

### Where systems disagree

| Axis | Positions | Consequence |
|---|---|---|
| Entity identity | merge by name (GraphRAG, LightRAG); LLM + embedding merge (Graphiti); never merge, synonym edges (HippoRAG 2) | keep per-chunk mentions as atoms; resolution is a separate, replaceable layer |
| Community membership | hard partition per level (Leiden); soft, several parents (RAPTOR); flat incremental (Graphiti) | many-to-many membership table |
| Summary storage | separate table (GraphRAG); in the chunk space (RAPTOR); field on entity/community (Graphiti) | separate Summary record that can be indexed alongside chunks |
| Time | claims only (GraphRAG); bi-temporal facts (Graphiti) | Graphiti's model plus `invalidated_by` |
| Mutation | in-place rewrites (GraphRAG, LightRAG); expire, never delete (Graphiti) | only the latter fits "rows are never overwritten" |
| Namespace | none; `workspace`; `group_id` on every row; tenant shards | `collection_id` on every row, separate from ACL |

## Proposed types

| Type | Key fields | Links | Input / derived |
|---|---|---|---|
| Collection | `id`, `name` | – | input (configuration) |
| Source | + `collection_id`, `acl`, `reference_time?`, `metadata`, `supersedes?` | Collection | input |
| Chunk | + `collection_id`, `parent_id?`, `level?` | Source, parent Chunk | derived; ACL from source |
| ChunkText | `chunk_id`, `kind`, `text`, `produced_by` | Chunk | derived |
| EmbeddingConfig | model, dimensions, preparation recipe | – | configuration |
| Vector | `owner_id`, `owner_kind`, `config_id`, `vector`; unique (owner, config) | any embeddable record | derived |
| Mention | `chunk_id`, `surface`, `type`, `span?`, `description`, `produced_by` | Chunk, Entity | derived |
| Entity | `collection_id`, `name`, `type`, `resolution_run` | Mentions | derived |
| Relation | `subject_id`, `object_id`, `predicate`, `fact`, valid and recorded intervals, `invalidated_by?`, `support` | Entities, Chunks | derived |
| EntityLink | `a`, `b`, `kind`, `score` | Entities | derived, optional |
| Group | `collection_id`, `algorithm_run`, `level`, as-of time | membership `(group, member, kind)` | derived |
| Summary | `kind`, `text`, `inputs`, `subject_id?`, `acl`, `valid_as_of?` | inputs, Group/Entity | derived |

Derived records carry `recorded_at` and `produced_by` (step or run fingerprint).

ACL of derived content: the intersection of its inputs' allow-sets (a viewer must see every
input). Community reports and merged descriptions therefore need ACL-homogeneous inputs,
per-ACL-class precomputation, or query-time summarisation over the viewer's projection.

Breaks later if deferred: `collection_id` on Source and Chunk, `acl` on Source, the Vector
keying convention, and the definition that offsets index the post-preprocessing `Source.text`.
Everything else can arrive as new tables or optional fields.

## Decisions

- Collection membership is exclusive: each Source belongs to exactly one collection; derived
  records remain in that scope. Collection scope is separate from access permissions.
- The baseline `Collection` is a plain Pydantic model with a generated UUIDv7 `id` and a required
  string `name`. Names are human-readable labels and need not be unique. `CollectionRow` maps
  the same fields, with `id` as primary key. Collection ids are persisted, not derived; benchmark
  record ids need not be reproducible across installations (Q23). Collection store operations are
  deferred.
- Peer review was skipped for the collection baseline only, at the owner’s request.
  Later interfaces follow the review gate in AGENTS.md.
- Implemented: `Source` and `Chunk` are frozen Pydantic models whose `id` is a deterministic
  UUIDv8, derived during validation by `triplum.datatype.ids`. A supplied id must equal the
  derived one, otherwise validation fails. No timestamp enters an id or fingerprint (Q22), and
  text changing A → B → A recovers the original Source id. `model_copy(update=...)` skips
  validation and would keep a stale id; changes construct a new record.
- Source: required `collection_id: UUID`. The id digest is
  `content_key("source-id", [collection_id, origin, text])`; the payload is
  `[collection tag 24][scoped source digest 98]`, the tag being leading bits of
  `content_key("collection-tag", [collection_id])`. Origin and text enter exactly as given.
- Chunk: required `collection_id` (its source's), `source_id`, `origin`, `ordinal`, `start` and
  `text`. The ordinal counts chunks in one chunking result contiguously from zero; it is neither
  a character offset nor a relative-position bucket, and validation restricts it to 0–65,535.
  The payload is `[collection tag 16][source prefix 42][ordinal 16][chunk digest 48]`: the source
  prefix copies the leading 42 bits of the scoped source digest, and the chunk digest hashes
  `[collection_id, source_id, ordinal, start, text]`. Chunker identity does not enter: equal output gives equal
  ids, whichever chunker produced it. `FixedSize` copies the source's collection and numbers its
  chunks.
- Tags and prefixes are locality hints only. The full collection id enters both digests and
  the full source id the chunk digest, so prefix collisions never merge records; short prefixes
  are never authoritative identity or ACL checks. UUID ordering does not cluster table rows or
  replace source indexes; no speedup has been measured.
- Fingerprints have the same dependencies as the ids (Q9): Source
  `content_key("source", [collection_id, origin, text])`, Chunk
  `content_key("chunk", [collection_id, source_id, ordinal, start, text])`. `Chunk.origin` is
  determined by its source and does not enter. Model dumps/JSON omit the fingerprint; stores fill
  their indexed columns explicitly. Equal fingerprints imply equal ids and parent references, so
  cached complete records keep correct parents; cross-collection or position-independent reuse
  takes an explicit smaller payload.
- Producers take a keyword-only `collection_id` (`Utf8File`, `MarkdownFolder`,
  `MultiHopRAGCorpus`) and include it in their fingerprints. The `index_folder` prototype uses a
  fresh UUIDv7 collection per call.
- SQL `source` and `chunk` rows carry `collection_id`, and `chunk` rows `ordinal`. Reads rebuild
  records through validation, so a row whose fields do not match its id is rejected. There are no
  migrations; tables created by the earlier layout are not updated.
- Groups use many-to-many membership, allowing multiple parents; graph/entity implications remain
  for review.
- Computation reuse is separate from record identity, provenance and permissions. Identical
  payloads may reuse work across Sources, but complete cached records must preserve the correct
  parent references. The [identity/cache analysis](cached-pipeline.md) records the approved
  Bazel-style computation/output identity separation. See [cache interfaces](cache-interfaces.md)
  for the current contract. A benchmark bypass is intended; its interface remains deferred.

## Remaining ID decisions

- Store write semantics (Q25): stores still replace by id. With derived ids this is reachable
  only for equal records, barring bugs, truncated-hash collisions or future fields outside the
  id. Insert-if-absent with equal duplicates as no-ops and unequal duplicates raising is the
  recommendation, not an approved contract.
- Several chunkings of one Source (Q24): `chunks(source_id)` returns the union of every stored
  chunking, and nothing identifies which ordered result a chunk belongs to or records an empty
  result. One chunking per collection versus an ordered membership record remains open.
- Chunking results over 65,536 chunks currently fail Chunk validation; the intended behavior is
  unspecified.
- Temporal history: text versions of a document share (collection, origin) but have unrelated
  ids, with no supersession link, validity interval or invalidation record.
- Origin normalization: ids use origin as given; which normalization producers apply is open.
- Collection storage operations: creating and reading collection records, store methods, and
  scoping reads to a collection.
- IDs for additional record types follow their own interface reviews. Multi-source records must
  not be forced into a single-source prefix.

Source ACL/time/metadata/supersession fields, Chunk hierarchy and dropping Chunk.origin remain
open.
