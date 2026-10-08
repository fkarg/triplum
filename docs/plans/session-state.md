# Rebuild handoff

Continue on `main` in the existing checkout. Preserve concurrent work. Contributor/review rules
live in [AGENTS.md](../../AGENTS.md); this page records where to resume, not a second contract.

## Current work

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
Automatic helper discovery uses the shared loaded-definition engine; decorators freeze identity on
first use, permitting helpers defined later in a module. Optional `dependency_mode="traced"`
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

Static mode remains the default and freezes inferred function identity on first use. Traced mode
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

Source/Chunk identity changes remain unimplemented. Both still generate UUIDv7 IDs and expose
computed fingerprint properties; there is no chunk ordinal or UUIDv8 generation. The agreed
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
