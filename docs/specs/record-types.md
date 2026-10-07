# Record types (draft for owner review)

Status: proposal. Nothing here is approved until the owner decides each item; decisions are
recorded under "Decisions" as they are made.

## Research summary

Primary sources, fetched and read for this draft (no peer review run):

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
  the same fields, with `id` as primary key. These declarations are implemented; membership
  fields and collection store operations are deferred.
- Peer review is skipped for the collection baseline at the owner's request for fast, small steps.
- The agreed Chunk UUIDv8 payload allocation is `[collection tag 16][source prefix 42]
  [ordinal 16][identity fingerprint 48]`. Any later adjustment considered here moves bits from
  the source prefix to the fingerprint; the collection and ordinal allocations stay fixed.
  This is a design decision, not implemented behavior.
- The ordinal counts chunks in one chunking result contiguously from zero. It is neither a
  character offset nor a relative-position bucket. The 16-bit field represents 0 through 65,535;
  behavior for larger results remains to be specified.
- Equivalent Source and Chunk records within the same collection should reproduce their IDs,
  provided this does not impose unreasonable costs. Exact equivalence and digest inputs remain
  open. Cache identity is a separate, subsequent discussion; reusing record IDs is a weak
  preference when appropriate, not a requirement driving this layout.
- The owner confirmed that text changing A → B → A should recover the original Source ID.
  Creation/change timestamps do not contribute to this identity. The owner now prefers at least
  24 collection-tag bits for Source; this does not revise the agreed Chunk allocation.

## Remaining ID decisions

- Source identity inputs: collection, origin, prepared text, and the treatment of future fields.
  Origin normalization and the identity consequences of edited text remain open.
- Chunk identity inputs: full source identity, ordinal, exact excerpt, and whether processing
  configuration contributes. Multiple chunking results also need a way to identify their members;
  distinct Chunk IDs alone do not distinguish which ordered result is being read.
- Collection generation: UUIDv7 is implemented; optionally seeding a persisted collection ID
  once from a suitable upstream dataset fingerprint remains a proposal.
- Source UUIDv8 layout: `[collection tag 24][scoped source fingerprint 98]` is the current proposal
  following the owner's preference for at least 24 collection-tag bits. The exact width remains
  to be finalized. This replaces the earlier 16/106 proposal. It is the proposed
  companion to the agreed Chunk layout. Prefix derivation and exact digest encoding need a
  specification, including full scope identities in hashes so prefix collisions cannot erase scope.
- Construction and storage: when IDs are generated, handling supplied IDs and later field edits,
  equal-ID/equal-record versus equal-ID/different-record writes, and oversized chunking results.
- IDs for additional record types follow their own interface reviews. Cache identity is discussed
  before those missing record types.

The next proposed example and the independent review of identity/cache interactions are recorded
in `docs/specs/cached-pipeline.md`.
