# Session state (2026-10-07)

Continue the rebuild on `main` in the existing checkout. The owner is moving to another machine.
The current discussion connects **Source identity and caching** to a small example pipeline.
The owner confirmed A → B → A should recover the original Source ID and prefers at least 24
collection-tag bits for Source, with remaining bits a fingerprint excluding creation/change time.
The Chunk UUID allocation is decided; the Source allocation and exact hash inputs are still under
discussion. No new ID or pipeline implementation has been authorized through the interface review
yet. The owner approved reuse of identical intermediate content across different upstream
processes, with Bazel's cache design as orientation. See `docs/specs/cached-pipeline.md` for the
identity discussion and earlier example; `docs/specs/cache-interfaces.md` is the proposed next
interface review, not an implemented API.

Latest performance requirements: cache target is dozens to hundreds of GB with room to grow;
lookup-first low overhead and deferred background writes. Cached calls require fingerprintable
input AND output values, and our intermediate types should provide that contract. Both decorators
and a `CachedStep` mixin are requested; manual get/put remains available. Individual steps or
larger blocks opt in, and multiple backends are acceptable. The final queue-full default is
**skip and count**, configurable per run/task/step; the brief block-default choice was retracted.
Exact declarations, codecs, resource ownership and backend selection remain under review.

## Implemented state

- `datatype.Collection`: plain Pydantic model with a generated UUIDv7 `id` and required string
  `name`; names need not be unique. SQL `CollectionRow` maps those fields. Added in `7a2858f`.
  Stores do not yet create or manage collections. Source/Chunk collection membership is not wired.
- `datatype.Source` and `datatype.Chunk`: plain Pydantic models, still generating UUIDv7 IDs.
  Both still expose `fingerprint` as a computed field. Source has `origin: str` and `text`;
  Chunk has `source_id`, `origin: Path | str`, `start` (character offset) and `text`.
  **There is no chunk ordinal field or UUIDv8 generation yet.**
- Step Protocols and trivial implementations: Converter / `Utf8File`, Chunker / `FixedSize`,
  EmbeddingText / `OriginalText`, Embedder / `ZeroEmbedder`. Our implementations also use
  `Fingerprinted`.
- `RecordStore`: `MemoryStore` and `SQLAlchemyStore`, with hand-written mappings in
  `store/sql/tables.py`. Current writes replace records by ID. Current reads do not take a Viewer.
  `store/graph/` is an empty placeholder.
- Utilities: configured-object fingerprints; dataset/loading utilities; SHA-256 `content_key`;
  a disk cache with an explicit directory and one file per entry (the current cache is not SQLite).
- Datasets: `FrameDataset`, `MarkdownFolder`, `MultiHopRAGCorpus` with `download()`.
- Owner prototypes `steps/indexing.py`, `steps/ingestion.py`, `examples/naive.py` and
  `tests/test_indexing_prototype.py` are committed, but remain prototypes under owner review.
- Python minimum is 3.14. Python packaging is independent of the Rust workspace.

## Decisions to carry forward

### Collections

- Each Source belongs to exactly one collection; its derived records stay in that scope.
- Collection scope is separate from permissions. Overlapping membership was rejected because
  it complicates indexing strategies and ownership of derived outputs.
- Reusable computation payloads can be shared when their actual inputs are identical, without
  sharing record identity across collections. Scope, provenance and permissions remain distinct.

### Chunk IDs: agreed allocation

The UUIDv8 **122-bit payload** is:

```text
[collection tag 16][source fingerprint prefix 42][chunk ordinal 16][identity fingerprint 48]
```

- The owner fixed this split. A later adjustment may move bits from the 42-bit source prefix
  into the 48-bit fingerprint; collection and ordinal allocations remain fixed.
- **Ordinal means chunk #0, #1, #2, ... contiguously within one chunking result.** It does not
  mean character offset or a relative-position bucket. Earlier bucket proposals were an assistant
  misunderstanding; do not revive them as the owner's intent.
- Sixteen bits represent ordinals 0 through 65,535. Handling larger results is still open;
  rejecting them explicitly is the current recommendation, not an approved contract.
- Distinct ordinals distinguish chunks within one result. The tail distinguishes different
  records at the same ordinal and protects against source-prefix collisions when its inputs
  include full source identity. Exact hash inputs remain open.
- The owner tolerates source-prefix collisions as a locality issue, while wanting complete-ID
  collisions to be very unlikely. Short prefixes must not become authoritative identity or ACL
  checks. Prefix collisions are harmless only if remaining bits adequately distinguish records.
- Equivalent Source/Chunk records within the same collection should reproduce IDs when reasonably
  achievable. Reconstructing records with their IDs from cache is also acceptable.
- Caching/reproducibility is a separate concern. Reusing IDs as cache identities is welcome when
  appropriate but only a weak constraint on this design.

The layout provides ordering in the ID index. It does not automatically cluster table rows or
replace the existing source lookup index. No database speedup has been measured.

### Caching: approved direction

- Identical intermediate values may reuse downstream computation even when different upstream
  processes produced them. Cache inputs reflect the actual immediate data, not upstream
  computation history. The current operation and its effective configuration still distinguish
  computations.
- Exclude bookkeeping timestamps from reusable value identity. A separate explicit benchmarking
  bypass is intended; benchmark methodology, including whether benchmarks should always disable
  caching, is deferred. Do not add time to fingerprints to force misses.
- Use Bazel's separation of computation lookup and output content identity as orientation. The
  concrete encoding, storage arrangement and example remain proposals, not implemented contracts.
- Record IDs and reusable payloads serve different purposes. Equal embedding text can reuse a
  vector computation without merging Sources or copying another Source's Chunk references.
  Cache complete records only when the inputs account for the references they carry; otherwise
  reuse an identity-free payload and bind it to the current record separately.
- Cached calls require fingerprintable inputs and outputs. Our intermediate types should support
  the protocol; custom types may implement it or remain uncached. Concrete datatype changes still
  need review. Cache handles, backend selection and queue/policy settings are outside semantic
  fingerprints.
- Decorators, a `CachedStep` mixin and manual access are requested. Steps and larger composed
  blocks opt in. Embedding-only caching remains an earlier example option, not a universal
  boundary. Record UUID changes and caching whole records remain separate interface reviews.
- Queue-full policy is configurable per run/task/step. The latest owner decision is skip new
  cache writes and count them by default; blocking remains an option, not the default.
- An optional Bloom filter below the interface is accepted for consideration. It must use the
  full computation key and have coverage of the backend read view before a negative can skip
  lookup. Accepted pending writes must remain visible. No filter implementation is approved.

### Other earlier decisions

- Step behavior uses Protocols; type aliases are only for data shapes.
- Store and cache are separate. Store implementations are grouped by backend; one Protocol per
  capability. SQL backends share hand-written row mappings; specialized stores can come later.
- Record `fingerprint` should become a plain method; stores populate their column from that method.
  Agreed but not implemented.
- Groups use many-to-many membership, allowing multiple parents. Graph/entity implications remain
  for the later record review.

## Resume here: open ID questions

These are proposals and unresolved decisions, **not approved schema changes**.

1. **Source equality.** Proposed identity inputs: full collection ID, origin and prepared text.
   This would give changed text a new ID. Decide origin normalization and how future fields affect
   identity. Source versioning/history semantics are not settled by the bit allocation.
2. **Chunk equality.** Proposed inputs: full Source ID, ordinal, character offset and text.
   Should otherwise identical outputs from different chunkers share an ID, or should configuration
   also contribute? The ordinal already makes identical excerpts at different ordinals distinct.
3. **Chunking-result membership.** Several strategies can produce distinct chunks at ordinals
   #0, #1, etc. Distinct IDs do not tell `chunks(source_id)` which complete ordered result to return.
   We need to decide how result membership is represented; this may involve a missing record type.
4. **Collection initialization.** UUIDv7 is implemented. Optional one-time seeding of a UUIDv8
   from an upstream dataset fingerprint is proposed. The chosen ID would then persist as the
   collection grows. Same seed means same collection identity; independent copies need an explicit
   distinguishing input or a fresh ID. The seed must exist before collection-scoped IDs, avoiding
   circularity. Current `RecordDataset.fingerprint()` includes generated record IDs and is not
   automatically a stable seed for reconstructed equivalent text.
5. **Source layout and encoding.** Current proposed Source payload: `[collection tag 24][scoped source
   fingerprint 98]`, with the Chunk copying its first 42 fingerprint bits. The owner requested at
   least 24 tag bits; the exact width remains open. Chunk's agreed 16-bit tag remains unchanged.
   Define canonical hash
   inputs, record-kind separation, prefix derivation and packing around reserved UUID bits.
   Hash the full collection ID into source identity and full source ID into chunk identity; using
   shortened prefixes alone would conflate scopes. Hashing the collection UUID into a tag is
   proposed; copying the leading bits of a UUIDv7 would mostly copy its timestamp.
6. **Construction and writes.** When are IDs generated? Are supplied IDs validated? What happens
   when identity-bearing fields change? Current recommendation: equivalent existing identity is
   reusable; conflicting identity under the same ID is rejected rather than silently overwritten.
   Mutation, collision and overflow behavior still need approval.

Continue the **identity/caching contract review**, then missing elements: representations and vector
configuration, mentions/entities/relations, groups/summaries and any processing-result records.
Do not force every future record into a single-source prefix: some records will combine sources.
Source ACL/time/metadata/supersession fields, Chunk hierarchy and dropping Chunk.origin remain open.

## Known issues and deferred work

- Reconstructed records currently get fresh IDs. Rerun insert behavior is not yet settled.
- `RecordDataset.fingerprint()` includes record IDs. Dataset fingerprint semantics need rethinking;
  the owner has expressed interest in lazy fingerprints available after consumption.
- Replacing a source retains its old chunks and can break their source-text correspondence.
  Replace-by-ID and reads without a Viewer do not meet the stated history/access requirements.
- `utils.data.Source` is a dataset type alias that clashes in name with `datatype.Source`.
- A `(source_id, start)` index was proposed before ordinal was clarified; revisit access/index
  choices with the actual ordinal and result-selection contracts.
- `SQLAlchemyStore.sources()` loads everything; row-by-row merging is slow.
- Manual docs examples are not tested automatically. The owner considers the Collection guide
  improvable and deferred further work on it.

## Working agreements and verification

- Keep design discussions focused. The owner endorsed the independent peer review of the cache
  proposal; the earlier blanket note to mostly skip reviews no longer applies. Reviews do not
  authorize implementation of unapproved core interfaces.
- Owner approves core interfaces; record assumptions as proposals. Implement only approved scope.
- Keep hand-written docs synchronized; use a docs subagent after interface changes. Published
  pages must not link to specs/plans; these development records remain excluded from the site.
- Commit coherent, verified changes periodically, as the owner reiterated. Preserve concurrent
  changes and stay in the existing branch/checkout.
- The collection baseline passed 61 Python tests, ty, Ruff, Cargo check/test, strict MkDocs and
  pre-commit gates at its commit. Python store tests emitted SQLite connection cleanup warnings.
- Branch/prototype status corrections were committed in `cbf6d7c`; strict MkDocs and staged
  pre-commit gates passed. The cached-pipeline proposal adds no ID or caching implementation.

The record-type proposal and accepted decisions are in `docs/specs/record-types.md`.
