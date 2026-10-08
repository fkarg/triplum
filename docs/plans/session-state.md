# Rebuild handoff

Continue on `main` in the existing checkout. Preserve concurrent work. Contributor/review rules
live in [AGENTS.md](../../AGENTS.md); this page records where to resume, not a second contract.

## Current work

The current task is an interface/concept audit, starting with identity and fingerprinting.
The owner authorized automatic configured-computation identity from code, selected configuration
and declared dependencies, without manually bumped version labels.
[Identity interfaces](../specs/identity-interfaces.md) records that contract and its review.
`Fingerprinted` and `CachedStep` now use explicit configuration hooks; value projections remain
independent of creation history and computation definitions. The owner also authorized the
[data-model base](../specs/data-model-fingerprints.md): `FingerprintedModel` supplies field-value
identity for use with bare decorators, with explicit exclusions and custom projections.
Record identity migration and further interfaces remain outside this approval.

The dirty-serving API-link regression is fixed in `18c29ca`: the hook restores skipped module
object references from the previous inventory while retaining changed-module-only rendering.

The owner authorized the optional computation cache and a small reuse example for review.
`triplum.cache` and `examples/cached_pipeline.py` are the first implementation. Read:

- [Cache interfaces](../specs/cache-interfaces.md) for declarations, guarantees and peer reviews.
- [Automatic identity implementation](automatic-computation-identity.md) for the current slice.
- [Initial implementation plan](cache-implementation.md#progress-and-rulings) for progress and verification.
- [Earlier identity/cache analysis](../specs/cached-pipeline.md) for research and tradeoffs.

Convenience defaults (`@cached`, `@cache.cached`) are implemented; see the
[cache guide](../infrastructure/cache.md) for usage and the implementation plan for review status.

The owner selected per-computation SQLite tables with input-only row keys and removed codec
format identity/migrations. Incompatible output contracts require representing their changed
definition in process identity or clearing; there is no manually maintained version counter.
`triplum cache stats` and `cache clear` are implemented; stats scans counts only with `--details`.
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
