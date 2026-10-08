# Automatic computation identity implementation plan

> Execution: one production-code author, delegated documentation and independent peer review.
> Skills: executing-plans, test-driven-development, writing-tests, verification-before-completion.

**Goal:** configured computations automatically identify loaded definitions and explicitly selected
settings, without manual version counters or runtime resource state.

**Architecture:** `Fingerprinted` supplies code/config/dependency identity; `CachedStep` inherits this
default while preserving explicit overrides. Data fingerprints and cache storage remain separate.

**Spec:** [Identity interfaces](../specs/identity-interfaces.md).

## Constraints and review focus

- No Source/Chunk, dataset, UUID, cache table or generic content_key behavior changes.
- No required version labels; no arbitrary transitive import discovery or schema hashing.
- Preserve bare decorator capture ordering and decoration-time source capture regressions.
- Inherited computation changes, loaded source drift, nested code, runtime counters and selected
  configuration mutation must be distinguished by behavioral tests.
- Explicit custom fingerprints remain valid; missing configuration fails rather than hashing resources.

## Task 1: automatic configured-object definitions

Files: `src/triplum/utils/fingerprint.py`, the four reference step modules,
`tests/test_fingerprint.py`, `tests/test_computation_identity.py`.

- [x] Record exact code-selection declaration in spec and obtain host Opus design critique.
- [x] Add failing cases for required projection, counters/locks, inherited code and source drift.
- [x] Implement `fingerprint_config`, `fingerprint_dependencies`, bounded loaded-definition hashing.
- [x] Give reference steps explicit size/dimensions/empty configuration projections.
- [x] Run focused fingerprint tests, typing and lint; inspect missing branches and peer findings.

## Task 2: cached step and worked reuse example

Files: `src/triplum/cache/steps.py`, `src/triplum/cache/identity.py`,
`tests/test_cached_steps.py`, `tests/test_cache_defaults.py`, `examples/cached_pipeline.py`.

- [x] Add a real temporary SQLite default CachedStep reuse case, plus loaded inherited/helper edit regressions.
- [x] Inherit automatic configured fingerprint; retain explicit fingerprint and bypass behavior.
- [x] Remove version advice and internal example version strings; demonstrate code/config identity.
- [x] Run cache/default/reuse tests and execute the example.

## Task 3: documentation, review and verification

Files: cache concept subpages, fingerprints guide, interface spec, session state, AGENTS and flow.

- [x] Delegate docs sync, keeping declarations separate from data fingerprints and deferred UUID work.
- [x] Run examples and strict MkDocs; perform fresh docs-only reader trial.
- [x] Obtain host Opus diff critique and resolve concrete defects.
- [x] Run full pytest branch coverage/durations, ty, Ruff, Cargo checks/tests and strict MkDocs.
- [x] Commit coherent verified change; record peer model, attacks and dispositions.

## Verification result

159 tests passed with branch coverage and duration reporting; total coverage is 90% and the changed
fingerprint module is 92%. Ruff, formatting, ty, Cargo check/test and strict MkDocs passed. The ten
cache-page Python blocks and the pipeline example ran successfully; general fingerprint examples
were separately checked by the docs writer. Existing SQL-store ResourceWarnings remain unrelated.
Host Opus design and implementation reviews and both fresh reader trials are recorded in the
identity spec and persona report. No Source/Chunk or dataset migration was performed.
