# Rebuild handoff

Continue on `main` in the existing checkout. Preserve concurrent work. Contributor/review rules
live in [AGENTS.md](../../AGENTS.md); this page records where to resume, not a second contract.

## Resume here

Active grill-me workstream: [ingress and caching](../brainstorms/2026-10-12-ingress-caching.md).
Sequential owner interview, interfaces first. Owner accepted P1: both Source and Chunk adopt
plain fingerprint methods, preserving existing digest inputs and dropping computed-field JSON
output. Implementation/docs are present; 265 tests passed with 89% branch-inclusive coverage,
typing/Ruff/formatting/Cargo/strict MkDocs passed, and four affected guide snippets ran.
Fresh-context review found no unresolved defects; Claude Opus 5.5 diff review supports the
correction. Its docs consolidation and redundant-test findings were addressed; peer dispositions
are in the capture. Existing SQL connection-cleanup warnings remain. No push or remote CI requested.
Deterministic IDs and digest-field changes remain open. Owner favors practical collection-dependent
later-block caching, with cheap chunking uncached. The owner has answered Q10/Q11: ordinary
multiargument decorators with deterministic named inputs;
practical reuse without optimizing rare cross-source hits, with contextual reconstruction allowed.
Do not re-ask those directions. Owner accepted P2; [multiargument decorators](cache-call-arguments.md)
are committed in `472b3a4` and verified: 288 tests passed with 90% branch-inclusive coverage; typing, Ruff,
formatting, Cargo and strict MkDocs passed. Eight affected teaching snippets ran. Opus 5.5 found
annotation evaluation and stale-default execution defects; both and the resulting key mismatch
were fixed with regressions. Fresh reviews have no remaining findings. No remote CI requested.
Owner approved P3 option A; [effective-context refresh](../specs/cache-context-refresh.md)
is implemented and verified: 312 tests passed with 90% branch-inclusive coverage; typing,
Ruff/format, Cargo and strict MkDocs passed. All 12 affected guide Python blocks ran. Automatic static identity now rereads its existing
bounded projection each lookup; immutable code/disassembly caches remain. Inputs/context must
stay stable during identity calculation and execution; mixed-context execution is outside the
guarantee, with no post-miss validation. The [plan](cache-context-refresh.md) owns verification.
Q20/Q21 are answered; fresh and Opus reviews have no unresolved findings. No push/remote CI
requested. Source identity
is independent of physical Q13 table layout. See the capture for peer dispositions.

Earlier work resolved Q4 with a bounded referenced-class identity improvement. The wider
library audit against the owner-maintained [goals](../goals.md) remains the context for the
remaining decisions.

- Working agreement: slow, step by step, with owner review. Do what follows directly from the goals
  and instructions; put everything else to the owner as questions.
- Next: resume remaining
  record/interface questions in [open questions](open-questions.md), one decision at a time. The owner
  deferred Q7's exact span counting/partial-credit choices until benchmark design. Earlier peer
  summaries for Q7 and Q9–Q12 are recorded there (review `4e752214c2144f13b6021c9dcbb48679`);
  its saved full response is unavailable on this machine.
- Q4: the owner accepts bounded inference for quick experimentation. Static discovery now tries
  existing loaded-definition hashing for referenced application classes, falling back to their
  qualified names when unsupported. Traced references, external classes and Pydantic model
  contracts retain their limits. No Python hash or class fingerprint hook is invoked.
  [Implementation and review](referenced-class-identity.md) record the slice. Verification:
  257 tests passed with 89% branch-inclusive coverage; typing, Ruff, Cargo checks/tests and strict
  MkDocs passed. The new class-helper guide example and existing cache reuse example ran.
  Existing SQL connection-cleanup warnings remain. No push or remote CI run was requested.
- Earlier audit fixes: `Chunk.origin` is a plain string; `MarkdownFolder` fingerprints cover
  absolute paths; the CLI reports inexact selector matches and handles `--name` on an empty
  cache; static identity rejects globals that are both assigned and read, and function-local
  imports of application code. Cache docs now have an Advanced section.
- Known: unsupported class definitions and output-model contracts can still require clearing
  affected cache entries. Source/Chunk methods satisfy the cache protocol, but their fingerprints
  omit IDs/bindings; arbitrary bound-record caching still needs complete effective inputs (Q9–Q11).
- Command-line scope is recorded in [the CLI contract](../specs/cli-selection.md).

## Background: identity and fingerprinting audit

The current task is an interface/concept audit, starting with identity and fingerprinting.
The owner authorized automatic configured-computation identity from code, selected configuration
and statically resolved application helpers, without manual dependency declarations or version labels.
[Identity interfaces](../specs/identity-interfaces.md) records that contract and its review.
`FingerprintedComputationMixin` and `CachedStep` now use explicit configuration hooks; value projections remain
independent of creation history and computation definitions. The owner also authorized the
[data-model base](../specs/data-model-fingerprints.md): `FingerprintedDataModel` supplies field-value
identity for use with bare decorators, with explicit exclusions and custom projections.
`FingerprintedDataModelMixin` supplies the same data identity to existing Pydantic bases;
`FingerprintedComputationMixin` names the separate computation helper.
Automatic helper discovery uses the shared loaded-definition engine; decorators refresh its bounded
projection before each lookup, permitting helpers defined later in a module. Optional `dependency_mode="traced"`
refreshes root identity and validates manifests before reuse; tracing records supported application
calls on misses. Unknown dependencies decline admission rather than forcing cached children to
rerun. See [computation dependencies](../specs/automatic-helper-identity.md) for its approved
design and the bounded static inference guarantees.
Record identity migration and further interfaces remain outside this approval.

## Completed identity and tracing slice

Implementation and documentation are committed; no tracing implementation task remains pending.
Resume with the owner's next interface question rather than expanding dependency inference or
migrating record identities automatically.

- `64da08d`: completed computation naming and the separate data mixin/Pydantic model base.
- `213d800`: automatic bounded static helper discovery, without manual dependency lists.
- `d29105c`: optional runtime tracing for `@cached`, `@cache.cached` and `CachedStep`.
- `1ba69ce`: production cache benchmark, raw measurements and performance report.
- Concurrent session's `4b53547`: function-name/source metadata and name-based cache clearing;
  this work is integrated and preserved.

Static mode remains the default; P3 refreshes its bounded inferred function identity each lookup. Traced mode
refreshes root identity, records application calls on misses and validates dependency manifests
on hits. A small input-addressed manifest index selects separately stored result blobs, preserving
A→B→A reuse. Index and result tables carry the same function metadata for name-based clearing.
Unsupported inference computes without admission; a static child cache hit is retained and
prevents parent admission rather than being rerun. Unknown receivers, ambiguous aliases,
semantic mutation, external memoization and nested configured computations have conservative
limits. Other-thread activity can prevent admission. Native code, files and external services
are not automatically covered. See the [tracing guide](../infrastructure/cache/tracing.md).

Claude Opus 5.5 review `f13e7f0d5d1342fa91f2517db0db1601` found unique stale-hit defects involving
receiver class constants, semantic mutation and equal code objects with different globals;
these changed the implementation and have regressions. Follow-up probes added closure-binding
identity, cross-helper mutation checks and empty-closure-cell coverage. Full review dispositions
remain in the [dependency spec](../specs/automatic-helper-identity.md#independent-reviews).

Verification at completion: 238 tests passed with 89% branch-inclusive coverage; typing, Ruff,
formatting, strict MkDocs and staged pre-commit checks passed. All 19 teaching examples ran
successfully with empty and populated caches. Rust checks/tests passed during this slice; Rust
was unchanged. Existing SQL connection-cleanup warnings remain. The hook's newer `uvx ty`
required `Generator[None]` return annotations for context managers; that correction is committed.
No push or remote CI run was requested.

[Measurements](tracing-performance.md): traced hits cost 0.66–1.23 ms, versus 39–72 µs for static
hits in the measured workloads. The larger computation improved from 4.085 ms uncached to
0.659 ms traced; tiny operations remain faster to recompute. Raw samples include source hashes
and environment details; they precede only the annotation correction above. These are local
microbenchmarks, not evidence of tens/hundreds-of-GB backend scaling. Further optimization and
competing-backend comparisons remain future work.

## Existing cache and record checkpoint

The dirty-serving API-link regression is fixed in `18c29ca`: the hook restores skipped module
object references from the previous inventory while retaining changed-module-only rendering.

The owner authorized the optional computation cache and a small reuse example for review.
`triplum.cache` and `examples/cached_pipeline.py` are the first implementation. Read:

- [Cache interfaces](../specs/cache-interfaces.md) for declarations, guarantees and peer reviews.
- [Automatic helper implementation](automatic-helper-identity.md) for the current slice.
- [Initial implementation plan](cache-implementation.md#progress-and-rulings) for progress and verification.
- [Earlier identity/cache analysis](../specs/cached-pipeline.md) for research and tradeoffs.

Convenience defaults (`@cached`, `@cache.cached`) are implemented; see the
[cache guide](../infrastructure/cache.md) for usage and the implementation plan for review status.

The owner selected per-computation SQLite tables with input-only row keys and removed codec
format identity/migrations. Incompatible output contracts require representing their changed
definition in process identity or clearing; there is no manually maintained version counter.
`triplum cache stats` and `cache clear` are implemented; stats scans counts only with `--details`.
Both support `--name` to select recorded function names across computation fingerprints.
The cache guide and interface spec record lifecycle guarantees and peer dissent.

Source/Chunk deterministic identity changes remain unimplemented. Both still generate UUIDv7 IDs
and now expose plain fingerprint methods; there is no chunk ordinal or UUIDv8 generation. The agreed
allocation, Source A→B→A requirement, proposals and unresolved decisions are authoritative in
[Record types](../specs/record-types.md#decisions). Review the shared fingerprint contract first;
Source/Chunk identity inputs and migration still require their own owner approval.

## Other implementation boundaries

The [overview](../flow.md#implemented-foundations) and linked guides describe the current modules.
Collection's baseline was added in `7a2858f`; membership/store operations remain deferred.
`steps/indexing.py`, `steps/ingestion.py`, `examples/naive.py` and their tests are owner prototypes
under review. Generated API presence does not establish approval.

## Known issues and deferred work

- Reconstructed records get fresh IDs; rerun insertion semantics remain open.
- `RecordDataset.fingerprint()` includes record IDs. Dataset semantics and the owner's interest
  in lazy fingerprints available after consumption need review.
- Replacing a source retains its old chunks and can break their text correspondence. Replace-by-ID
  and reads without a Viewer do not satisfy history/access requirements.
- `utils.data.Source` is a dataset type alias that clashes with `datatype.Source`.
- Revisit the proposed `(source_id, start)` index after ordinal and result-membership decisions.
- `SQLAlchemyStore.sources()` loads everything; row-by-row merging is slow.
- Manual documentation examples are not automatically tested. The Collection guide needs a
  later improvement pass, deferred by the owner.
- SQL store tests have emitted connection-cleanup warnings. Use current check output, not old
  handoff test counts, to establish verification status.

Remaining record reviews cover representations/vector configuration, mentions/entities/relations,
groups/summaries and processing results. Benchmark cache methodology is deferred; do not add
bookkeeping timestamps to fingerprints to force recomputation.
