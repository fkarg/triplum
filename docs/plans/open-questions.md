# Open questions

Cross-session record of design questions for the owner: open questions first, then answered ones.
The owner's answers are authoritative. Specs record the resulting contracts once written; this page
records the questions and answers, and links to the spec that takes over.

## Process

- Append new open questions as they arise, including questions left over from a session.
- After each owner answer, derive what follows: answers it implies for other questions (mark them
  "derived" and name the source answer) and new questions it raises. Derive carefully; when an
  implication is uncertain, ask it as a new question instead of recording it as an answer.
- Before presenting a question, ask a peer for an independent answer with `peer-review` (see
  AGENTS.md), without showing it our suggestion. Present both suggestions and name who chose what.
  Record the peer model, the review ID and any divergence.
- Number questions once and never reuse a number. Move a question to "Answered" when the owner
  answers it; keep the suggestions there for context.

## Open

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

### Q9. What Source and Chunk fingerprints cover

Derived from Q2: origin and collection leave fingerprints. Source fingerprint: text only. Chunk
fingerprint: text only, or text plus `start`?

Peer (same review): Source = text; Chunk = text + start, since `start` is an observable field and
equal text at different offsets is a different excerpt. Position-independent work can take a
text-only value. Claude (formed after reading the peer): agrees.

### Q10. Cached steps whose output depends on origin

Derived from Q2. With origin outside the fingerprint, a cached block that behaves differently by
origin (say a chunker that treats `.md` specially) returns a wrong hit for equal text at another
origin.

Peer (same review): a cached block receives an explicit input value containing every field it
uses. Content-only blocks take a text value; origin-sensitive blocks include origin,
or a derived selector such as the format, in that input. `Source.fingerprint()` is therefore not a
safe key for arbitrary Source consumers. Claude raised the hazard but had no answer of its own;
it agrees with the peer.

Fresh Claude Opus 5.5 review `aa313bda22954ce2a606bb20021b48c4` recommends deciding this
before deterministic IDs: a bound-output block input includes full binding identity plus all
effective semantic data. Deterministic IDs improve reuse across runs; they do not repair an
incomplete key. This is a proposal. Q10 does not require Q9's global record projection first.

### Q11. How a cached block returns records

Derived from Q1 and Q3. A cached block (say Source → chunks with vectors) must return records whose
ids and parent references belong to the current input.

- (a) The cached block returns an id-free payload (ordered starts, texts, vectors); ordinary pipeline
  code builds records from the payload and the current source, on hits and misses alike.
- (b) A step-type-specific cache adapter (`cached_chunker`, …) stores id-free content and rebuilds
  records inside the cache layer.
- (c) A rebinding hook on the decorator, or a codec that receives the input.

Claude originally proposed (b). Peer (same review): (a); record construction stays in pipeline code,
not in cache behavior, and benchmark runs use the same construction without the cache.
**Divergence:** Claude now prefers (a), since Q3 makes user-composed blocks, not single steps, the
caching unit.

Current grill-me workstream: [ingress and caching](../brainstorms/2026-10-12-ingress-caching.md).
Fresh independent Claude Opus 5.5 review `81713a89b1084c74ac68588bf02f30f7` also recommends
(a), with complete explicit computation inputs and identical binding on hits/misses. It exposed
the span-coordinate question Q16. This is still a proposal, not an owner decision; detailed peer
dispositions are in the capture.

Owner's latest direction: chunking itself is cheap and not a priority to cache; later blocks
may reasonably be collection-dependent. A is acceptable in principle, but the owner leans
toward bound-record reuse (C in the current round) with mostly deterministic identities for
practical experimentation. Exact contracts remain open. Fingerprints and database IDs retain
distinct, partially overlapping purposes; this does not make database IDs generic cache keys.

### Q12. Deterministic record ids

Derived from Q1/Q2. Ids either derive fully from their inputs or are random and recomputed per run.

- (a) Deterministic UUIDv8 ids from the agreed layouts ([record types](../specs/record-types.md)):
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

### Q18. Shared fingerprint interface: method or property

Owner: proceed with both Source and Chunk adopting fingerprint methods via subagent. This
accepts P1's method compatibility correction, preserving current record digest inputs and
removing computed-field serialization. RecordDataset digests consequently change; its wider
identity semantics remain Q14. Deterministic IDs and digest-field changes remain unapproved.

Session and Claude Opus 5.5 (`58c7c321353e42869071e7f4f9ce1b77`) recommend methods. Peer
additionally recommends preserving dataset digests with an explicit projection; session
recommends no compatibility projection. Owner accepted the bounded correction. Implementation
and verification are tracked in the [capture](../brainstorms/2026-10-12-ingress-caching.md).

### Q4. Application classes and output models in computation identity

Owner: use existing class-definition hashing for referenced application classes and document
the limits. The cache is intended to help quick experimentation, not guarantee discovery of
every behavior change. Comprehensive output-model contract hashing is not required.
Python `__hash__` was raised as a possible fallback; it is not a persistent definition identity.
Implementation details and verification are tracked in
[referenced class identity](referenced-class-identity.md).

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
