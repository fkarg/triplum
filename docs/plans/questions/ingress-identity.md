# Ingress, record identity and cache binding

Questions use the `Q` prefix. Process: [questions index](README.md).

## Open

Round 4 (identity basics), peer gpt-6.1-sol review `46079fc7b277487abf9b2966b4ffd738`; detail in the
[benchmark baseline capture](../../brainstorms/2026-10-12-benchmark-baseline.md).

### Q22. What a Source id identifies

Owner (answered): one id per exact text version; the fingerprint may share behaviour or build on
it. No timestamp fields in ids or fingerprints.

Claude and peer: one exact prepared text of one origin in one collection;
`content_key("source-id", [collection_id, origin, text])` packed into the proposed Source UUIDv8.
A→B→A recovers A. Versions of a document group by (collection, origin). Temporal occurrences need
their own key.

### Q23. Collection reference and creation

Owner (answered): deterministic benchmark record ids across installations are not a requirement.
Collection ids are persisted UUIDv7.

`Source.collection_id: UUID`; collection ids persisted UUIDv7. Divergence on benchmarks: Claude
derives from corpus identity (needs Q14); peer publishes fixed ids in a benchmark manifest.

### Q7. Representing gold evidence in benchmarks

"Gold evidence" is a benchmark's annotation of which passages support each answer. HotpotQA marks
supporting facts as (article title, sentence index); MultiHop-RAG lists evidence as URL plus fact
text. Retrieval recall (R@2, R@5) asks whether the top-k retrieved chunks contain that evidence.
The old fixtures store gold as old integer chunk ids, which can never match now: chunk ids are
random, and chunking is itself an experimental variable.

- (a) Document key plus character span in the prepared source text; recall from retrieved spans.
- (b) Document key only: document-level recall.
- (c) Evidence text, matched as a substring of retrieved chunks.

Claude: (a) with any-overlap matching, falling back to (b) for datasets without spans. Peer
(same review): (a), but an evidence span counts only when the union of retrieved spans from that
document covers it **completely** (complementary chunks may cover it jointly). Any-overlap would
credit a one-character sliver. Keep unresolvable annotations in the denominator. **Divergence:**
Claude now prefers the peer's complete-coverage rule.

Owner agrees with span-based evidence and wants the full (or mostly full) span retrieved, and
raised proportional partial credit as a possibility. Owner deferred exact counting until benchmark
design; Q7 is not a blocker for the current cache work. No partial-credit metric is approved.

### Q24. Several chunkings of one Source

Owner (answered 2026-10-29): (a). A source has one current chunking; `chunks(source_id)` returns
only that chunker's chunks, ordered by ordinal, which is unique per source. Changing the chunker
clears the source's existing chunks and recomputes them (cached if configured), giving fast
reproduction of expensive state. A membership-style option (b) may return later with benchmark
run design, randomness and variability.

Owner (round 4): agreed chunker identity is not stored; questioned the intermediate record and
asked for full context. Re-presented in round 5 (peer `4254cb6d42c34fce9021d55e9c5dea3b`).

Context: `chunks(source_id)` returns every stored chunk of a source sorted by start. Chunking the
same Source with FixedSize(500) and FixedSize(1000) into one store returns both mixed together; nothing
says which chunk belongs to which run, and an empty result leaves no trace.

- (a) One chunking per Source per collection: compare chunkers in separate collections. No new
  record; Sources are duplicated per collection (their ids differ by collection).
- (b) An ordered membership record `ChunkingResult(source_id, chunk_ids)` (no chunker identity);
  reads name a result. Equal chunks are shared; a small extra record and completion boundary.
- (c) Callers keep the chunk ids of each run in their experiment output; the store keeps the union.

Claude: (a). Peer: (b); (a) duplicates Sources and cannot hold two chunkings of the same Source.

### Q25. Store writes once ids are deterministic

Owner (answered 2026-10-29): agrees with (c) for the record store; the cache is unaffected.
Derived with Q24: chunk writes replace a source's complete chunk list; see P3 in the capture.

Owner (round 4) asked whether this is the cache or the store. It is the record store; the cache is
unaffected (equal key is a hit, writes replace). Context: today the store replaces a record whose id
already exists. With derived ids, re-running ingestion writes records whose ids already exist, and
an equal id normally means equal content. Remaining cases: a different value under an existing id
(bug, truncated-hash collision, or a future field outside the id) and records a re-run no longer
produces (old text versions, old chunks).

- (a) Keep replace-by-id.
- (b) Insert if absent, ignore any duplicate.
- (c) Insert if absent; equal duplicate is a no-op; unequal duplicate raises; nothing is deleted.

Claude and peer: (c). Owner's expectation that pipelines cannot conflict holds for (c) in normal
operation; the error only surfaces bugs or collisions.

### Q26. Where the collection enters construction

Found while implementing deterministic ids (round 5, peer `4254cb6d42c34fce9021d55e9c5dea3b`).
Claude and peer: producers of Sources (`Utf8File`, `MarkdownFolder`, `MultiHopRAGCorpus`) take a
keyword-only `collection_id`; Source requires it; chunkers copy it from the Source. Implemented
under the owner's "go ahead with deterministic ids"; reopen if the owner prefers a later binding step.

### Q27. How the derived id is attached

Claude and peer: the id is derived during validation, a supplied id must match, and records are
frozen. Implemented on the same basis as Q26. `model_copy(update=...)` bypasses validation; SQL
reads re-validate.

### Q9. What Source and Chunk fingerprints cover

Owner (answered): whole-record fingerprints with the same dependencies as the ids.

Round 4: Claude revised to peer: whole-record fingerprints include context (Source collection,
origin, text; Chunk source, ordinal, origin, start, text); cross-context reuse caches explicit
smaller payloads. Current Chunk fingerprint can replay another collection's parent ids.

Q2 permits fingerprints to omit origin/collection; it does not prescribe a universal projection.
Review Source text-only versus the current origin/text projection, then Chunk text-only versus
text/start or its current origin/start/text projection, independently of database ID semantics.

Peer (same review): Source = text; Chunk = text + start, since `start` is an observable field and
equal text at different offsets is a different excerpt. Position-independent work can take a
text-only value. Claude (formed after reading the peer): agrees.

### Q12. Deterministic record ids

Derived from Q1/Q2. Ids either derive fully from their inputs or are random and recomputed per run.

- (a) Deterministic UUIDv8 ids from the agreed layouts ([record types](../../specs/record-types.md)):
  Source from full collection identity, exact origin and text; Chunk from full source identity,
  ordinal, start, excerpt and the chunking computation's identity. Requires a persisted collection id.
- (b) Random UUIDv7, rebuilt per run.

Peer (same review): (a); rerun
insertion without duplicates and A → B → A recovery follow, but conflict handling, obsolete chunk
removal and the 65,536-chunk ordinal limit still need specifying. Claude (formed after reading the
peer): (a), decided together with the storage backbone (Q13).

Fresh review `aa313bda22954ce2a606bb20021b48c4` and local interface exploration remove that
table-layout dependency: full collection-scoped Source identity works with shared or separate
tables. Review Source semantic inputs first, then where collection enters construction, with
Chunk identity as a later contract. Keep ID derivation independent of record fingerprint inputs.

### Q13. Storage backbone: one table for many collections, or tables per collection

Owner, while answering Q2: to be rethought soon. Benchmarking one table holding several collections
requires ids that include collection and origin. Not yet put to a peer.

### Q14. Dataset fingerprints and record ids

Derived from Q2. `RecordDataset.fingerprint()` hashes full records, including random ids, so equal
content gives different dataset identities. Delegate to record fingerprints, or keep full records
once ids are deterministic (Q12)? Not yet put to a peer.

### Q15. Cache entry points

`@cached`, `@cache.cached` and `CachedStep` overlap. The owner asked for both decorators. Whether
`CachedStep` remains depends on Q11. Not yet put to a peer.

### Q16. Span coordinates across preprocessing

Derived from fresh Q11 review: Chunk text must be a verbatim slice of Source.text. Normalization
inside a cached block can shift offsets. Decide which text spans address and where text-changing
preprocessing sits when reviewing the concrete payload contract. No offset-map type or restriction
has been approved. Held until that review; main session owns preparation.

### Q17. Mutable external inputs at the conversion/cache boundary

Utf8File reads a Path's current bytes; a path alone does not identify that content. MarkdownFolder
fingerprinting and later item reading are separate observations. Decide the snapshot boundary
and effective input for cached parsing/OCR without assuming that a dataset-wide fingerprint
pins later reads. Held for upstream interface review; main session owns preparation.

## Answered

### Q20. Refreshing changed effective global context

Owner requires changed effective globals/configuration to change computation identity, and
approved P3 option A. Implemented and verified: automatic static decorators and the computation
mixin reread the existing bounded definition/settings projection each lookup. Code/disassembly
caches remain; overrides and discovery limits are unchanged. Q21 defines the stable-during-call
boundary. [Context refresh](../../specs/cache-context-refresh.md) owns the resulting contract.

### Q21. Post-computation context validation

Owner selects A: context remains stable during identity calculation and execution; no second
identity check after a miss. A computation observing intermediate changes may mix A and B, so
neither fingerprint describes it fully. Document this limit; do not expand into dynamic mutation
tracking. Session favored A, Claude Opus 5.5 favored a partial after-miss guard (review
cdf47cadbb9c4b89821f95251cb40a8e); owner rejected that extra mechanism.
[P3 contract](../../specs/cache-context-refresh.md) records the authoritative boundary.

### Q19. Multiargument cache decorator

Owner accepted P2: "P2 sounds good, proceed." Both decorators now normalize positional/keyword
arguments and current defaults into one input digest, preserving legacy sole-fingerprintable
keys. [Call arguments](../../specs/cache-call-arguments.md) owns the implemented contract;
[the plan](../cache-call-arguments.md) records verification. Global-context refresh remains Q20.

### Q10. Effective inputs of cached functions

Owner: functions may take multiple arguments; normalize by parameter name into deterministic
input-data identity. Effective globals/configuration belong in computation identity and changes
must be reflected. No mandatory user-authored input wrapper or new key callback is requested.
The cache can retain one input digest. Implementation follows Q19/P2 and context refresh Q20.
Prior peer options and the repeated-question correction are in the ingress/cache capture.

### Q11. Cached results and record bindings

Owner: equal text can reuse cross-source computation and IDs/records can be reconstructed from
current context where needed. Such reuse is expected to be rare and is not worth optimizing for.
Prefer practical later-block caching, potentially collection-dependent, with mostly deterministic
IDs; do not mandate a payload/binding split or reopen this direction. Concrete record identity
contracts remain Q12; Q1's no-wrong-source-reference requirement stands. Prior alternatives and
peer dissent are preserved in the capture rather than treated as pending owner choices.


### Q18. Shared fingerprint interface: method or property

Owner: proceed with both Source and Chunk adopting fingerprint methods via subagent. This
accepts P1's method compatibility correction, preserving current record digest inputs and
removing computed-field serialization. RecordDataset digests consequently change; its wider
identity semantics remain Q14. Deterministic IDs and digest-field changes remain unapproved.

Session and Claude Opus 5.5 (`58c7c321353e42869071e7f4f9ce1b77`) recommend methods. Peer
additionally recommends preserving dataset digests with an explicit projection; session
recommends no compatibility projection. Owner accepted the bounded correction. Implementation
and verification are tracked in the [capture](../../brainstorms/2026-10-12-ingress-caching.md).

### Q4. Application classes and output models in computation identity

Owner: use existing class-definition hashing for referenced application classes and document
the limits. The cache is intended to help quick experimentation, not guarantee discovery of
every behavior change. Comprehensive output-model contract hashing is not required.
Python `__hash__` was raised as a possible fallback; it is not a persistent definition identity.
Implementation details and verification are tracked in
[referenced class identity](../referenced-class-identity.md).

Owner requested clarification of the current mechanism before deciding: computation selects
the table, input fingerprint selects the row, and the value is the computed result. The output
fingerprint is not a lookup key. The open issue is incomplete computation dependency discovery,
not a proposed change to this key structure.

Original question: static identity followed functions in the application, but an application
**class** used by a cached function contributed only its name. Example: a cached function calls
`Folder().run(x)`, with `Folder` defined in the same package. Editing `Folder.run` left the fingerprint
unchanged, so the cache kept returning results computed by the old `run` (reproduced). The return model is
the same case: adding a field to the output Pydantic model leaves identity unchanged; old results
decode with the new default, or raise a raw `ValidationError` for a new required field.

- (a) Classes referenced by the computation, and its effective output model, contribute their
  definitions: methods (including inherited application methods), validators, serializers,
  default factories, and field contracts including nested models.
- (b) Raise `UnsupportedFingerprint` for application classes. Breaks every function that
  constructs its own output model.
- (c) Document the limit only.

Claude: (a). Peer (gpt-6.1-sol, review `4e752214c2144f13b6021c9dcbb48679`): (a), and stresses that
field schema alone misses behavior (validators, default factories), and that an explicit
`output_type` must select the same output contract as the annotation, for decorators and
`CachedStep` alike. The owner chose a narrower best-effort class extension, retaining documented
output-model limits; this supersedes both earlier comprehensive-hashing recommendations.

### Q1. Records returned from the cache

Owner: ids are either fully dependent (deterministic) or fully independent; in the latter case,
recompute them for the actual source/collection after loading from cache. Never return another
source's ids. Follow-ups: Q11, Q12.

### Q2. Fingerprints versus ids

Owner: ids and fingerprints serve different, overlapping purposes and may behave differently. Ids
must distinguish origin and collection (one-table, multi-collection benchmarks); fingerprints need
not include origin or collection. The storage backbone needs rethinking soon. Follow-ups: Q9, Q10,
Q13, Q14.

### Q3. Caching embeddings

Owner: embedding alone is too cheap to cache. The intended caching unit is a block of several
preprocessing steps ending with embedding, before storing. Users may wrap smaller calls; not
recommended.

Derived (Q3): no per-text embedding cache or per-step cache adapters. A block's cached output
includes vectors, so the cache still needs a payload codec for arrays.

### Q5. Runtime dependency tracing

Owner: keep it; it is not integrated anywhere yet.

### Q6. Background cache writer

Owner: keep it; a synchronous write might affect timing more; revisit eventually.

Derived (goals): benchmark runs neither read nor write the cache, so the writer cannot affect
benchmark timings, only experimentation latency.

### Q8. Cache documentation structure

Owner: agreed. Concept pages: getting started, value fingerprints, computation fingerprints,
administration. Advanced: tracing, serialization, storage backends, ownership/write policy (done).
Merge the top-level Fingerprints page into the cache fingerprint pages: pending, because its record
section changes with Q9.

## Review backlog not yet posed as questions

From the library review; promote to numbered questions when they come up.

- Traced mode silently declines admission (e.g. output models with application validators);
  no counter or log reveals it.
- `process_id` with `dependency_mode="traced"` does not key tables as the docs and CLI describe.
- `examples/cached_pipeline.py` uses `process_id=definition_hash(...)`, which the guide says is
  unnecessary.
- `MemoryStore` stores references while the SQL store copies; records are mutable.
- Re-running ingestion duplicates records (Q12); replacing a source keeps stale chunks.
- No Question/QA dataset, retriever or text index, retrieval result type, Viewer, metrics or run
  loop: the path to a BM25 baseline on the fixtures (needs Q7).
- `Embedder` has no query/passage split; `EmbeddingText` sees only a chunk.
- `datasets/manifest.json` and `tests/fixtures/ATTRIBUTION.md` reference removed tooling.
- `steps/ingestion.py` (comment only) and `steps/indexing.py` (a pipeline) sit in `steps/`.
- `docs/concepts/decisions.md` publishes replace-by-ID as a store contract.
