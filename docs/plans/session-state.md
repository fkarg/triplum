# Session state (2026-10-07)

Continue the rebuild on `main` in the existing checkout. The owner is moving to another machine.
The next discussion is **Source equality and identity inputs**, then Chunk equality, then caching,
then the missing record types. The UUID allocation is decided; its implementation is not authorized
by that decision alone. Keep the owner involved one interface at a time.

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
- Reusing computation across collections can be considered later; it does not require sharing
  record identity across collections.

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
5. **Source layout and encoding.** Proposed Source payload: `[collection tag 16][scoped source
   fingerprint 106]`, with the Chunk copying its first 42 fingerprint bits. Define canonical hash
   inputs, record-kind separation, prefix derivation and packing around reserved UUID bits.
   Hash the full collection ID into source identity and full source ID into chunk identity; using
   shortened prefixes alone would conflate scopes. Hashing the collection UUID into a tag is
   proposed; copying the leading bits of a UUIDv7 would mostly copy its timestamp.
6. **Construction and writes.** When are IDs generated? Are supplied IDs validated? What happens
   when identity-bearing fields change? Current recommendation: equivalent existing identity is
   reusable; conflicting identity under the same ID is rejected rather than silently overwritten.
   Mutation, collision and overflow behavior still need approval.

After Source/Chunk identity, discuss **caching**, then missing elements: representations and vector
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

- Fast, focused design discussion; mostly skip peer reviews for now. Do not launch a long review
  or implementation merely because the next design question is open.
- Owner approves core interfaces; record assumptions as proposals. Implement only approved scope.
- Keep hand-written docs synchronized; use a docs subagent after interface changes. Published
  pages must not link to specs/plans; these development records remain excluded from the site.
- Commit when asked. Preserve concurrent changes and stay in the existing branch/checkout.
- The collection baseline passed 61 Python tests, ty, Ruff, Cargo check/test, strict MkDocs and
  pre-commit gates at its commit. Python store tests emitted SQLite connection cleanup warnings.
- Current handoff changes only this session note and `docs/specs/record-types.md`. Run strict
  MkDocs and the staged pre-commit gates for the handoff; no new ID implementation is being tested.

The record-type proposal and accepted decisions are in `docs/specs/record-types.md`.
