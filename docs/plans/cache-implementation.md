# Optional caching implementation plan

**Goal:** Implement the reviewed decorator/mixin/backend/policy boundary and a runnable shared-cache
pipeline example, with fingerprintable values and a Pydantic serialization option.

**Spec:** `docs/specs/cache-interfaces.md`. The owner explicitly requested implementation after
receiving the draft. Execute inline in the current checkout, with independent research/review and
a delegated documentation pass; no additional approval handoff is needed.

**Architecture:** `triplum.cache` owns the interface. One explicitly owned Cache can serve multiple
steps, keyed by full computation and immediate input digests. The subsequent table/CLI change
removed codec format keys; owner-requested cleanup removed the unused `utils.cache.Cache` class
while retaining its hashing helpers. A replaceable backend owns storage connections; Cache owns the
bounded queue, pending visibility and background writer. Start with SQLite, without claiming a
performance winner. A PydanticCodec provides JSON bytes and validation for fingerprintable models;
custom codecs remain possible. No record-ID migration, embedding contract rewrite or Bloom filter.

## Constraints and review focus

- Strict fingerprintable inputs/outputs; fingerprints explicitly select semantic fields.
- Skip-and-count by default, blocking override; oversized blocking entries raise ValueError as
  drafted. This keeps the byte budget strict and the alternative visible for owner review.
- Serialization occurs before admission; only persistence is background work.
- Same computation/configuration and input reuse across instances; changed computation or input
  misses; upstream history, policies and storage paths do not enter semantic fingerprints.
- Read-your-writes includes in-flight batches. Old batch completion cannot evict newer writes.
- Writer failure wakes waiting callers; close stops admission and drains accepted writes.
- Pydantic serialization is not universally lossless: codecs must round-trip semantic fields.
- No new dependencies, cross-process pending guarantees or duplicate-compute lock.

## Task 1: Backend and coordinator

Files: `src/triplum/cache/{__init__,protocols,sqlite,runtime}.py`,
`tests/test_computation_cache.py`, `tests/test_sqlite_cache.py`.

- [x] Write public-API tests using temporary SQLite databases and event-controlled backend fakes:
  persistence/reopen, all three key components, empty bytes, pending visibility, queue skip/block,
  oversized entries, duplicate keys during commit, failed writer wakeup, draining close.
- [x] Run tests and observe missing-feature failures.
- [x] Add validated CacheKey/CachePolicy and CacheBackend protocol; implement SQLite with binary
  indexed keys, separate reader/writer connections and WAL; implement one bounded writer queue.
- [x] Run relevant tests, ty and Ruff. Check the shared identity/lifecycle contract independently.

## Task 2: Typed frontends and serialization

Files: `src/triplum/cache/{codecs,steps}.py`, `tests/test_cached_steps.py`,
`examples/cached_pipeline.py`.

- [x] Test Pydantic roundtrips, unsupported fields, semantic timestamps, changed input/config,
  equivalent step instances sharing results, decorator/mixin equivalence and cache=None bypass.
- [x] Observe missing-feature failures, then implement Fingerprintable/Codec, PydanticCodec,
  cached and CachedStep.compute. Preserve generic input/output types and explicit process identity.
- [x] Add a small two-step pipeline using fingerprintable Pydantic values. Demonstrate downstream
  reuse when different upstream computation yields the same value, A→B→A reuse, and reopen reuse.
- [x] Run the example and targeted tests. Commit a verified coherent implementation with docs.

## Task 3: Documentation, review and verification

Files: README.md, AGENTS.md, docs/flow.md, 
`docs/infrastructure/cache.md`, docs/specs/cache-interfaces.md,
docs/plans/session-state.md, the current cache spec (historical design/API pages are absent and are not recreated).

- [x] Delegate documentation synchronization; preserve distinction between current implementation
  and unapproved record/embedding interfaces. Explain shared cache identity and per-step isolation.
- [x] Independent code/consistency review, plus required host Claude Opus review. Record findings,
  attempted falsifications and dispositions; fix concrete defects with regression coverage.
- [x] Run pytest with branch coverage, ty, Ruff checks/format, Cargo check/test and strict MkDocs.
- [x] Commit coherent changes. Report actual implementation, verification and performance limits.


## Progress and rulings

- Tasks 1–2 implemented and exercised by the cache/backend/frontend/example tests.
- Default external surface refined per owner: output_type selects Pydantic serialization;
  codec is optional. A parameter-light convenience layer is the latest requested refinement.
- Retain the explicit oversized-blocking error proposal; automatic oversize admission would
  weaken the hard pending budget. Owner may change that tradeoff during code review.
- Default codec checks roundtrip on writes; custom codecs uphold that same contract themselves.
  Per-hit hashing is not added. Custom serialization changes require format-version updates.
- Existing docs/API/design paths missing from this rebuild were not recreated. Documentation
  agent updated README, AGENTS, flow, the cache guide and session handoff instead.
- Full Python verification after initial implementation: 89 passed, 92% total branch-aware
  coverage; two existing SQL store cleanup warnings. Type checks passed.
- Consistency review found and tests reproduced both successful-batch and error-traceback payload
  retention; fixed. Both independent Opus code reviews returned; findings and dispositions are in the spec.

- Owner explicitly chose both bare @cached and @cache.cached convenience. Implemented inferred
  Pydantic return models, optional per-binding overrides, documented lazy default ownership/path,
  Cache/CachedStep defaults, and normalized source/default/capture identity for simple functions.
- Convenience review found order-sensitive dict captures and custom builtin subclasses collapsed
  in identity. Both reproduced with tests, then fixed. Dependency tracking remains explicit;
  captured configuration is fixed after first use.
- Core checkpoint committed as 0ed0bae; convenience APIs are a separate reviewed change.

- Opus core review d255e8907b2d492881b7eaa06d382112 added grouped cleanup errors/retry and
  text-only traceback logging. Both regressions reproduced before fixing.
- Opus convenience review c1e067b6e066427b965267e5d7e74425 caught edited-source key poisoning;
  automatic identity now binds at decoration. Added atexit no-reopen regression and documented
  stop/join-before-close ownership. Cache I/O and codec creation remain lazy.
- Concurrent documentation rewrites overlap README, AGENTS, flow and session handoff; preserve
  their worktree state. Cache guide, this plan and the interface spec are staged independently.
