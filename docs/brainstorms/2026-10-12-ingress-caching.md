# Ingress pipeline and caching

## Workstream

- Owner request: grill-me on ingress and caching, emphasizing interfaces while examining implementations.
- Execution: sequential; accepted proposals finish and are reviewed before another ordinary round.
- Owner exploration preference: default to read-only subagents for exploratory tasks; main session synthesizes and inspects critical code. Recorded after the owner's follow-up before further round preparation.
- Follow-up checkpoint: owner asks whether the shared interface should instead be a fingerprint property, but considers the distinction minor and tentatively favors the method as more generally correct. No property migration approved. Main assessment: method is consistent with current computation/dataset/cache surfaces and explicit digest recomputation; properties are possible but changing the shared protocol would enlarge the fix.
- Checkout: existing checkout and branch, per AGENTS.md rebuild gate. No worktrees or branch switches.
- Scope: loading/conversion, Source, chunking/enrichment/embedding, cache boundaries and record construction. Storage identity is relevant at the boundary; retrieval and benchmark metrics remain separate.
- P1 accepted: owner explicitly says proceed via subagent with both Source and Chunk fingerprint methods. This expands the Source-only draft to the same bounded conversion for both records and authorizes completing both interfaces together. No ID/digest-field migration approved.

## Architecture and evidence

- Dataset/IterableDataset own access and logical identity; DataLoader lazily consumes/batches items (`src/triplum/utils/data/`).
- `Converter[A].__call__(item: A, /) -> list[Source]`; Utf8File reads bytes from a Path and creates a fresh Source.
- `Chunker.__call__(source: Source, /) -> list[Chunk]`; FixedSize attaches the current source ID and origin to exact text slices.
- Source/Chunk are mutable Pydantic records with UUIDv7 IDs and plain `fingerprint()` methods after P1. Digests omit IDs/bindings; method compatibility does not establish safe general bound-record caching. ID/membership migration remains unapproved.
- `cached` accepts one fingerprintable input and returns a fingerprintable output; a hit decodes the stored output without input-aware rebinding (`cache/steps.py`).
- Indexing/ingestion code remains under review. This map describes the local checkout, not verified upstream absence.
- Cache-disabled execution must work; benchmark runs must neither read nor write cache. Storage and cache are separate.

## Settled owner decisions

- Q1: never return another source's IDs; IDs are fully dependent or fully independent and recomputed for the current source/collection.
- Q2: record IDs distinguish origin/collection; fingerprints need not.
- Q3: recommended cached unit is a composed preprocessing block ending in embeddings before storage, rather than embedding alone. Smaller user-selected calls remain possible.
- Existing cache decorators and configured computation identity remain authorized. No record identity migration is implied.

## Decision frontier

IDs reference `docs/plans/open-questions.md`; avoid renumbering existing questions.

| ID | Decision | Prerequisites | Status |
| --- | --- | --- | --- |
| Q11 | Ownership of record construction after cached computation | Q1, Q3 settled; exploration/research completed | Ready, presented in round 1 |
| Q9 | Source/Chunk semantic fingerprint fields | Existing Q2; input boundary review | Ready, held for focused round |
| Q10 | Complete effective input and binding identity of cached blocks | Current cache contract; owner direction | Ready, next recommended round |
| Q12 | Source semantic identity, then construction and Chunk identity | Settled collection scope / A→B→A; separate declaration review | Source inputs ready; later contracts blocked |
| Q13 | Collection storage layout | Dedicated storage review | Ready, outside first round |
| Q14 | Dataset identity semantics | Promise can be decided now; projection may depend on Q9/Q12 | Ready promise; projection held |
| Q15 | CachedStep versus decorator entry points | Ergonomics review | Ready, held |
| Q16 | Which text chunk spans address across preprocessing | Q11 and exact payload review | Blocked |
| Q17 | Snapshot boundary for mutable file/URL conversion inputs | Upstream interface review | Held |

Additional candidates: laziness and converter cardinality. Assign stable new IDs only after investigations establish the questions.

## Round 1: Q11 (pre-peer assessment)

Context: existing Chunker creates storage records, whereas generic caching restores a stored value. Equal text may occur under different source IDs/origins. Any reusable preprocessing output must avoid leaking old record bindings.

Session options and original recommendation:

1. Cache an explicit ID-free result containing the reusable computation output; ordinary pipeline code creates records for the current source on both hits and misses. Recommended: separates reusable values from storage binding, uses identical construction with cache disabled, and leaves generic cache behavior unchanged. Concrete payload fields and the relationship to Chunker still require their own declaration review.
2. Cache record-shaped output with a step-specific adapter that strips and rebinds identity. Preserves record-facing step signatures but adds cache-specific behavior and a second binding path.
3. Include complete source/collection identity in the cached input and store bound records. Simplifies binding but loses reuse across origins and still needs a policy for independent IDs.

### Owner reply / checkpoint

- Fingerprint method compatibility: owner calls the missing Source/Chunk methods a defect to fix. Existing record spec already agrees that fingerprint becomes a method; investigate why that migration was left out. No digest-field decision is implied by the fix.
- Chunking: fast, deterministic and cheap; do not center cache design on caching it. Later processing is the expected caching target.
- Q11: agrees with A in principle but questions its practicality; leans toward C with mostly deterministic identities. This is a direction, not approval of a concrete identity layout or cache wrapper. Record-free blocks remain available, not mandatory.
- Scope/reuse: later blocks may reasonably depend on collection. Optimize experimentation across ingress/retrieval options; exhaustive independent-computation reuse is not the objective.
- Identity: fingerprints and database IDs have distinct, partially overlapping goals. Do not conflate them or automatically make a database ID the generic cache key.

Session revised assessment: prioritize existing record-facing steps and later caching; deterministic bound outputs may be practical. Earlier recommendation A overemphasized maximal cross-source reuse relative to the owner's goal. Complete binding identity still matters when restoring bound records, regardless of best-effort computation discovery. Q11 remains open for exact contracts.

### Independent peer and disposition

Claude Opus 5.5 (`claude-opus-5-5`), review `81713a89b1084c74ac68588bf02f30f7`, full JSON read. Recommended record-free cached output, explicit effective input, and ordinary uncached binding on both hits and misses. Suggested keeping the existing record-facing Chunker as convenience around a split/bind decomposition; this is a proposal, not permission to refactor it.

Attempted falsifications: equal text across origins; omitted title/context in key; UUIDv7 keys; deterministic-ID dependency; normalization changing span coordinates; using record fingerprints; differing hit/miss binding paths; whether split/bind preserves FixedSize behavior.

Impact: added verification requirements (complete effective input, both hit/miss paths, original-source slice correspondence); found a unique design hazard in text normalization changing offset coordinates, promoted to Q16. No change to session's recommended binding location. Peer introduced alternatives of leaving record-facing chunking uncached, including full identity in keys, input-aware cache hooks, or ID-less record migration. The latter is deferred/unapproved; no need to decide it now.

Peer claims rejected/narrowed:

- "UUIDv7 means never hits" is overbroad: repeated processing of the same existing Source can hit. Freshly reconstructed sources cannot share that ID-based entry, and cross-source reuse is lost.
- "ID-less records are then safe" omits copied origin and other provenance; dropping IDs alone does not make source-bound metadata portable.
- "Record fingerprints only lose performance" holds for the peer's narrow text/position example, not arbitrary record consumers that read omitted fields. Explicit block inputs must contain all effective data regardless of Q9.
- Peer's catch-all context dictionary, concrete vector encoding, global ban on caching records, automatic FixedSize refactor and span-only block restriction are not adopted. Concrete types and their tradeoffs wait for interface review; source-specific caching remains a possible use case.

Merged Q11 choices: explicit reusable value output plus pipeline binding (session and peer recommendation); preserve record-facing chunking and put the cached boundary later around projected preprocessing/embedding values (smaller change, narrower reuse); keep bound records and key on full binding identity (same-source reuse, no cross-origin reuse). Input-aware cache hooks are a materially different owner-selectable option, with extra generic-cache contract cost.

Round requests a boundary decision only. Exact declarations, input fields, spans, vector encoding, and whether Chunker changes remain unsettled. No P task is offered.

## Investigations and flags

- Main session: critical interfaces/tests inspected; verify concrete declaration drafts against actual implementations before presenting them.
- Ingress explorer: confirmed the distinction between DataLoader batching and document conversion; mutable Path contents are external effective input, and dataset fingerprint reads can diverge from later reads. Upstream/OCR remains deferred.
- Cache explorer: confirmed that neither raw record properties, lists nor ndarray implement the callable cache fingerprint contract. Excluded fields still serialize, so excluding origin/IDs alone cannot make restored record metadata safe. Q9 need not block an explicit value-to-payload boundary. Q15 is an ergonomics decision, not necessarily dependent on rebinding; revisit its dependency rather than presuppose removal.
- External researcher: completed official comparisons, below.
- Owner: Q9–Q17 remain design decisions; Q18 answered and method correction accepted.
- Main session: P1 under verification/review; independent frontier preparation may proceed, next ordinary interview waits for P1 completion.

## Implementation proposals

### P1 — Source and Chunk fingerprint method compatibility (accepted, implemented and reviewed)

Acceptance checkpoint: owner requests both records via subagent. Q18 answered: use methods.
The approved scope includes the discussed removal of computed fields from dumps and resulting
RecordDataset digest change; do not add a dataset compatibility projection. Owner combines
both records in this slice, overriding the earlier Source-first proposal.

Chunk declaration: `def fingerprint(self) -> str`, preserving exactly
`content_key("chunk", [self.origin, self.start, self.text])`. Inputs origin/start/text; output
SHA-256 hex string; ignores id/source_id and recomputes on calls. Example:
`Chunk(source_id=source.id, origin=source.origin, start=0, text="hello").fingerprint()`.

Approach: replace Source's computed property with `def fingerprint(self) -> str`, retaining
exactly `content_key("source", [str(self.origin), self.text])`. Purpose: supply the existing cache
protocol and SQL fingerprint column without changing identity semantics. Inputs: current
origin/text; output: SHA-256 hex string. Guarantees: ignores record ID, reflects mutation,
retains current digest values. Example: `Source(origin="x", text="hello").fingerprint()`.

Removing the computed field removes fingerprint from Pydantic model dumps; SQL still stores
the explicitly computed column. RecordDataset JSON-based identity changes as a consequence;
its broader semantics stay open. Avoid a compatibility shim with two public fingerprint names.

Files/ownership: scoped worker owns `datatype/source.py`, Source write in `store/sql/generic.py`,
Source-related tests, relevant Source/fingerprint guides and record spec. Docs sync delegated
and inspected by main session. Existing checkout; preserve all concurrent changes.

Checks: real temporary SQLite source round-trip and stored fingerprint; real cache hit/reopen
using Source as an input to a safe fingerprintable output, codec Source round-trip, mutation
and ID exclusion. Test that model dumps no longer contain computed fingerprint. Full checks
from CONTRIBUTING, branch coverage/durations, teaching examples affected, strict MkDocs,
review and coherent commit. No push/PR requested; CI not run.

Budget: callable compatibility for both records and necessary call-site/serialization/docs
updates only. No digest-field change, deterministic IDs, collection fields, cache input-policy
change, chunker refactor or performance work.

Main assessment before peer: recommend this bounded correction now; hash-field semantics
and bound-record cache safety should not be silently resolved in a method fix. Peer pending.

P1 peer: Claude Opus 5.5 (`claude-opus-5-5`), `a7ded2dbeb404c2e97a3b1114351c5d1`;
full JSON read. Recommends method conversion with explicit admission changes: Source becomes
accepted by static/traced cache paths and nested data/computation projections. Added verification
for nested Source and identity exclusion on cache hits; this is not a behavior-neutral rename.
Attempted attacks: current cache acceptance, nested projection, existing unsafe consumers,
origin coercion, old JSON decoding and RecordDataset coupling. No existing unsafe cached Source
consumer found. Old JSON decoding remained unexecuted. Disposition: unique missing nested-value
surface added to plan; other hazards already recorded, strengthened explicit guarantees.
Retain `str(self.origin)` in the final method body to avoid gratuitously changing post-construction
coercion; digest field decisions remain Q9. SQL column migration on future digest changes belongs
to Q9's plan, not P1. Do not add a compatibility shim or nested-value rejection special case.

### Q18 — Shared fingerprint shape (follow-up preparation)

Owner raises property versus method; prior method agreement reopened for this narrow discussion.
Session pre-peer options: retain method and migrate record declarations (recommended; local,
consistent, explicit computation); migrate shared consumers to properties (coherent but much
wider change); support both (extra dispatch, inconsistent surface, not recommended). Serialization
inclusion is independent: an ordinary property does not imply Pydantic computed-field output.
Neutral brief `/tmp/triplum-fingerprint-shape.txt` excludes session options/recommendation;
includes owner's tentative preference and facts. First host call did not start: automatic
permission review timed out; one permitted retry issued. No implementation launched.

Official external evidence: [Python descriptors](https://docs.python.org/3/howto/descriptor.html#properties)
permit computed property access; [PEP 8](https://peps.python.org/pep-0008/#designing-for-inheritance)
advises against expensive properties. [Pydantic computed fields](https://docs.pydantic.dev/latest/concepts/fields/#the-computed_field-decorator)
make serialization inclusion separate from ordinary properties; no automatic cache invalidation.

Q18 peer: Claude Opus 5.5 (`claude-opus-5-5`), review `58c7c321353e42869071e7f4f9ce1b77`;
complete JSON read. Recommends methods; property direction changes shared consumers and mixins
to accommodate two records. Tested Protocol property rejection, codec and nested projection
failure, old JSON extra-key acceptance, dataset digest change/restoration, method comparison
pitfalls, and ordinary-property serialization. Impact: no change to method recommendation;
added verification on comparisons/example output and old JSON; dissent on dataset preservation.

Peer additionally recommends explicitly inserting the digest into RecordDataset's projection
to preserve its current digest. Main session rejects adopting that automatically: owner's
request did not require persistence of current dataset keys, and adding a dataset compatibility
projection expands a Source method correction into the open Q14 surface. Preserve Source's
digest, disclose the one-time dataset digest change, and leave Q14 for its own review. This is
an explicit recommendation disagreement, not an owner decision. Owner may require preservation,
in which case amend/review P1 before acceptance.

Q18 subsequently answered and P1 accepted by owner's explicit request for both records.
No repeated broad research needed: this is a local
interface consistency correction. External official guidance and the prior local maps suffice.

### History evidence

Cache explorer traced properties to `3378eda` (initial record/store implementation), agreed
method conversion to `e7ef7ad` (record spec), and explicit deferrals to `10b095d` (separate
reviewed record change) and `e4ae9d5` (data-model plan excludes UUID/property migration).
Evidence supports a deferred integration task, not an unexplained accidental method removal.
Tests still explicitly require fingerprint in `model_dump()`; fix that observable contract
through review rather than retaining two contradictory surfaces.

## External evidence (facts, not adopted contracts)

- [LlamaIndex ingestion API/source](https://developers.llamaindex.ai/python/framework-api-reference/ingestion/): caches transformed nodes using content including metadata and transformation configuration; document-store deduplication/upsert remains a separate policy.
- [Haystack DocumentSplitter](https://docs.haystack.deepset.ai/docs/documentsplitter): output includes source bindings and copied metadata. [Document embedding](https://docs.haystack.deepset.ai/docs/openaidocumentembedder) can include selected metadata in effective text.
- [LangChain indexing API](https://reference.langchain.com/python/langchain-core/indexing/api/index): full cleanup assumes the loader supplies the full replacement set; partial iteration cannot silently imply deletion.
- Researcher's recommendation: detach reusable computational values from occurrence provenance and storage deduplication. Equal paragraphs may share computation but remain distinct evidence occurrences. No framework establishes an automatically safe universal Source fingerprint.

## Peer preparation

### Next frontier preparation (during P1, not a concurrent interview)

Owner asks next open design questions. Main assessment before new peer: prioritize Q12's
Source identity semantics, with full collection identity, exact origin and prepared text as
the candidate inputs; keep physical table layout Q13 separate unless evidence forces linkage.
Source A→B→A recovery is already settled, so do not ask it again. Alternative: add conversion
computation identity, distinguishing equal text produced differently but coupling records to
implementation history; recommendation excludes it unless provenance is itself a named identity
requirement. Exact constructors, supplied IDs/mutation policy and UUID packing remain subsequent
contract decisions. Q9/Q10 still govern computational equality and effective cache inputs:
deterministic IDs alone cannot make a key ignoring binding identity safe for bound outputs.

For inventory, list Q9/Q10, Q12, Q11, Q13/Q14 then Q17/Q16; Q15 ergonomics is lower priority
and Q7 benchmark evidence matching stays deferred. Revalidate dependencies; this is preparation,
not permission to implement identities. No ordinary question round before P1 completes.

Next-frontier peer: Claude Opus 5.5 (`claude-opus-5-5`), review
`aa313bda22954ce2a606bb20021b48c4`, complete JSON read. Recommends Q10 first, then
Source identity semantics; confirms Source ID semantics do not depend on shared/per-collection
table layout once full collection scope is an ID input. Recommends bound-output block keys
contain full binding IDs plus effective semantic values, leaving detached block reuse available.
Source candidate tuple: full collection UUID, exact origin, prepared text, with ID hashing
defined separately from record `fingerprint()`.

Attempted falsifications: table-layout dependency; A→B→A with ID+content keys; mutation under
unchanged IDs; equal text across origins/collections; present cache protocol acceptance;
cache versus record-table layout; full-record dataset projection. Impact: changed next-round
priority to Q10; removed artificial Q10→Q9 and Q12-Source→Q13 prerequisites; added a
version-versus-document identity discussion and duplicate-occurrence equivalence question.
Independent ingress explorer agrees on key/table-layout decoupling and separates collection
binding construction from identity inputs.

Dissent/limits:

- Peer calls Q14 categorically dependent on Q12. Rejected: ordered semantic data versus literal
  stored records is independently decidable; a content projection can work with current IDs.
- Random IDs do not violate empty-cache execution; they reduce reuse across reconstructed records.
- Peer would largely close Q11 under the owner's leaning. Not adopted: actual output binding,
  effective input contract and generated-ID semantics still need owner-approved declarations.
- History needs deliberate linkage, but no new stable-document key/type is approved by the
  review. Source ID can identify a content version without designing temporal fact records now.

P1 verification/review checkpoint: worker red contract failures then 44 focused tests passed;
main full suite 263 passed, 89% branch-inclusive coverage, timings recorded. Main ty/Ruff/format
and Cargo check/test passed. Docs agent ran four affected snippets with expected output and
strict MkDocs. Main fresh-context general/simplicity/pre-mortem/test-quality reviewer found no
production defect; requested traced admission/hit coverage. Worker added it: 58 relevant tests
passed, including traced tests, without tracing changes. New SQL test resources are explicitly
closed; existing lifecycle warnings remain separate. Final full run: 265 passed with 89%
branch-inclusive coverage; typing/Ruff/formatting and main strict MkDocs passed. Timings recorded;
existing SQL cleanup warnings remain. Fresh reviewer confirmed traced gap closed.

Diff peer: Claude Opus 5.5 (`claude-opus-5-5`), review
`4924db3d8a2041bf962fcb483a8dbe4a`, complete JSON read, supports production change.
Attempted attacks: missed property consumers; dumped fingerprint consumers; SQL reads;
old cache payloads; missing binding identity; nested delegation; existing cached record
consumers; actual traced reuse after reopening. Impact: found unique docs duplication and
published changelog prose; docs agent consolidated to authoritative record spec/guide and
strict build passed. Added plain wrong-parent example to guide; known binding hazard remains
outside method correction. Removed overlapping JSON/legacy decode checks, duplicate store
reopen and incidental cache pending-byte settings. Rejected test helper nit: two direct
construction blocks are locally readable; an abstraction is unnecessary. Scope unchanged.
Worker's trimmed tests passed (24 focused), typing/Ruff/format passed. No existing cached
Source/Chunk consumer found; peers did not run full tests themselves.

Round 1 neutral brief: `/tmp/triplum-ingress-round1.txt` (ephemeral); main session invoked host `peer-review --from gpt --mode design`, default Claude Opus target. Brief includes settled decisions, actual interfaces and external facts; excludes session recommendations. It asks whether Q11 can precede Q9 and Q12/Q13, and what happens to the existing Chunker contract.

Verification: strict MkDocs build passed after excluding `/brainstorms/` from publication; no production Python changed. No commit, push or CI run in this preparation slice.

## Lasting documentation targets

Contracts: relevant `docs/specs/` pages. Owner Q&A: `docs/plans/open-questions.md`. Handoff: `docs/plans/session-state.md`. Implemented behavior: concept guides and `docs/flow.md`. This capture stores interview/dependency history, not a replacement contract.

## Delivery checkpoint

P1 final state: 265 tests passed with 89% branch-inclusive coverage; durations measured.
Typing, Ruff, formatting, Cargo check/test and main strict MkDocs passed. Four affected teaching
snippets ran with expected output. Fresh general/simplicity/pre-mortem/test-quality review and
Claude Opus diff review addressed; no unresolved production findings. SQL cleanup warnings in
existing tests remain. Local delivery commit subject: `Make Source and Chunk fingerprints callable`.
No push/remote CI requested. The workstream remains open: next frontier Q10, then scoped Q12
Source identity/construction; no identity implementation proposal is accepted.
