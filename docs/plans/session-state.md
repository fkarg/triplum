# Rebuild handoff

Continue on `main` in the existing checkout. Preserve concurrent work. Contributor/review rules
live in [AGENTS.md](../../AGENTS.md); this page records where to resume, not a second contract.

## Current work

The owner authorized the optional computation cache and a small reuse example for review.
`triplum.cache` and `examples/cached_pipeline.py` are the first implementation. Read:

- [Cache interfaces](../specs/cache-interfaces.md) for declarations, guarantees and peer reviews.
- [Implementation plan](cache-implementation.md#progress-and-rulings) for progress and verification.
- [Earlier identity/cache analysis](../specs/cached-pipeline.md) for research and tradeoffs.

The owner requested convenience defaults (`@cached`, `@cache.cached`) as the next refinement.
See the implementation plan for progress and the [cache guide](../infrastructure/cache.md)
for the current usage contract.

Source/Chunk identity changes remain unimplemented. Both still generate UUIDv7 IDs and expose
computed fingerprint properties; there is no chunk ordinal or UUIDv8 generation. The agreed
allocation, Source A→B→A requirement, proposals and unresolved decisions are authoritative in
[Record types](../specs/record-types.md#decisions). Resume those decisions after the cache review.

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
