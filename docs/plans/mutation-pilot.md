# P10 mutation-testing pilot

Pilot of the owner's TQ1 decision ([testing questions](questions/testing.md)): on-disk cosmic-ray
mutants with per-mutant test selection, run locally on an isolated copy. Tool:
`scripts/mutation.py` with the coverage plugin `scripts/mutation_context.py`; usage is in
CONTRIBUTING. Scratch results lived under `/tmp/p10` on jolly and do not travel; the figures
below are the record.

## Setup (observed)

- Machine "jolly": AMD Ryzen 9 9950X3D, 16 cores / 32 threads, 91 GB, power profile `balanced`.
  Python 3.14.8, cosmic-ray 8.8.0, parso 0.8.7, coverage 7.16.1, pytest 9.1.1. Base `f796b23`.
- Suite: 542 tests, 10.6 s wall. Each Python process spun up numpy/OpenBLAS threads at import:
  42 s user CPU per suite run, 8 s with `OPENBLAS_NUM_THREADS=1` (import: 2.2 s → 0.35 s). The
  runner pins BLAS to one thread. The earlier research ran on margo (Core Ultra 5 125H laptop,
  ~35 s per suite); its CPU-hour estimates do not transfer.
- The copy imports its own `src` through `PYTHONPATH` ahead of the editable install; observed
  via `triplum.__file__`. Subprocess tests inherit it. A child started with `python -I`/`-E`
  would escape; none exists today.

## Coverage map (observed)

- Per-test contexts need the `ctrace` core (Python 3.14's `sysmon` records only the first test
  per line, TQ5 research).
- `patch = subprocess` alone serialises the parent's already-expanded configuration into the
  child, so every subprocess line was credited to no test. The plugin instead points children
  at the rc file through `COVERAGE_PROCESS_START`; its `context = ${TRIPLUM_MUTATION_CONTEXT}`
  then expands to the calling test. Result: 518 contexts (some tests cover no package line);
  CLI, example and fresh-interpreter tests are attributed.
- 3,071 measured lines; 52 run only at import time. Tests per line: median 17, mean 32, max 345.
  The coverage pass takes 15.7 s against 11 s plain.

## Full pass (observed)

6,249 mutants from cosmic-ray's default operators; 990 s elapsed on 30 workers; 19,733 s child
CPU (5.5 CPU-hours).

| Status | Count | Meaning |
| --- | ---: | --- |
| arid | 1,287 | inside an annotation; skipped (mostly `X \| None` under 11 binary-operator swaps) |
| invalid | 1,150 | does not compile; discarded (cosmic-ray treats `*`, `/`, `**` in parameter lists and unpacking as operators) |
| uncovered | 76 | on statements no test executes; not run |
| killed | 3,030 | |
| timeout | 37 | counted as killed (cosmic-ray convention); 26 in `cache/runtime.py` |
| survived | 669 | on 341 distinct lines; 202 in `utils/fingerprint.py`, 73 in `cache/tracing.py`, 64 in `cache/runtime.py` |

Worker time by path:

| Path | Mutants | Median | Share |
| --- | ---: | ---: | ---: |
| selected tests, then full suite (survivor confirmation) | 519 | 22.5 s | 43% |
| full suite only (import-time line, 403 in `datatype/ids.py`) | 730 | 15.5 s | 35% |
| selected tests only (killed) | 2,450 | 1.0 s | 11% |
| timeouts (75 s limit) | 37 | 75 s | 10% |

Selected runs used a median of 29 tests. Selection saved less than TQ5 estimated (inferred:
roughly 1.5× CPU against a full suite per mutant), because confirmation and import-time code
dominate. Full runs take ~20 s each under 30-way load against 10.6 s alone.

**Selection misses:** 32 of 519 confirmations were killed only by the full suite, 26 of them
`==` → `is`. Reproduced one: `action is "list"` makes the compiler emit a `SyntaxWarning`,
which a CLI test catches by asserting empty stderr. A test that never runs the line can kill a
mutant at compile time; coverage cannot see that, the confirmation does. The same blind spot
applies to the 76 uncovered mutants, which are not run.

## Independent review of the runner

Peer gpt-6.1-sol, review `5eb9148b967446879eb9257b6c702776`, 15 findings. Attempted
falsifications (several executed): a mocked baseline timeout, relative-path evaluation, a
parse-count spy, a multi-line assignment under `--diff`, a non-ASCII identifier before an
annotation, all selected/full exit-code combinations, a `KeyboardInterrupt` through cosmic-ray's
restore, a child exiting through `os._exit`. Dispositions:

- Unique defects, fixed: a timed-out baseline was accepted; a relative `--out` sent workers'
  `PYTHONPATH` to a missing directory (fallback to the editable install); an `--out` inside the
  repository copied earlier copies (now rejected; other workers copy the first snapshot);
  `--diff` used selection anchors for eligibility (now the mutated span only); the module cache
  re-parsed per mutant; timeouts were stored as ordinary kills in `session.sqlite` (now output
  `timeout`, as cosmic-ray does); a descendant could outlive its run into the next mutant (the
  process group is now always killed); AST byte columns compared with character columns.
- Added verification: `patch = _exit` for children leaving through `os._exit`; the worker cache
  directory is cleared before each run. Neither problem was observed (no `os._exit` in tests or
  source; no worker wrote to its `XDG_CACHE_HOME`).
- Rejected: "exit 3 or a signal is not a kill". A crash caused by the mutant is a detection;
  cosmic-ray counts any nonzero exit the same way. Output is now kept for exits other than
  0/1/timeout, so such kills can be audited.
- Boundary stated, not fixed: `-I`/`-E` children (none today).
- Nits applied: direct optional annotation, set comprehension, `enumerate` for progress.

The full pass above ran before these fixes, invoked so none of the defects applied (absolute
`--out` outside the repository, passing baseline, no `--diff`).

## Selection soundness sample (observed)

300 random runnable mutants with `--verify-selection` (seed 1; 188 s, 2,598 CPU-s): of 182
pairs with both a selected and a full run, 146 were killed by both, 34 survived both and 2
survived selection but were killed by the full suite (caught by the confirmation). **No
selected kill was contradicted by the full suite**, so test-order dependence did not create
false kills in this sample.

## Diff-scoped run (observed)

`--diff HEAD~3` (P13/P14 source changes: 7 files, 37 changed lines): 74 mutants, 52 invalid,
16 killed, 6 survived; 35 s elapsed, 120 CPU-s on 30 workers, including the 15 s coverage
pass. The survivors, each a one-line review:

- `RetrievalHit` `frozen=True` → `False`: no test pins that hits are immutable.
- `MemoryStore.sources()` `s.collection_id == collection_id` → `is`: tests pass the identical
  UUID object; an equal UUID built from a string would kill it.
- `sources(self, *, collection_id, …)` → `(self, /, collection_id, …)` in the Protocol, memory
  and SQL stores: keyword-only calling is not pinned.
- `@abstractmethod` removed from the Protocol's `sources()`: an explicit subclass lacking
  `sources()` is not detected.

## Survivor review (30 random survivors of the full pass, seed 7)

Test-quality reviewer subagent; six classifications checked by running mutants (observed),
one by arithmetic against the fixture, the rest by reading (inferred). About 5 minutes of
agent time; 11 survivors were decidable from the diff alone. Session spot-checked S2 and S25.

| Class | All (30) | Caching/fingerprint modules (10) | Rest (20) |
| --- | ---: | ---: | ---: |
| Gap that could hide a user-visible bug | 5 | 1 | 4 |
| Minor gap | 9 | 2 | 7 |
| Equivalent | 10 | 4 | 6 |
| Defensive (guard, budget or performance only) | 6 | 3 | 3 |

The caching and fingerprint modules hold half of all survivors but no more equivalent noise
than the rest, and the top-ranked gap is there: excluding them would hide real gaps.

Top gaps:

1. `utils/fingerprint.py:510` `index + 1` → `index << 1`: global-mutation detection depends on
   bytecode position; a late `SETTINGS.update(...)` is accepted silently (stale hits), a late
   `LOG.append(...)` makes the list part of identity (observed).
2. `datasets/hotpotqa.py:110` `+` → `^`: passage-level gold end offsets are wrong for most title
   lengths; the fixture's one-letter titles make `2 ^ n == 2 + n`.
3. `datatype/ids.py:42` `0xFFF` → `4094`: `_unpack` drops payload bit 62, re-keying chunk ids
   whose source has that bit set; the layout test's only origin has it clear (observed).
4. `cache/defaults.py:60`: `close_default_cache()` becomes a no-op, losing pending writes at
   exit; close/reopen is not pinned (observed).
5. `store/sql/generic.py:24` `==` → `<=`: non-SQLite URLs get SQLite pool settings; only
   `sqlite://` URLs are tested (inferred).

## What the survivors say about the suite

The owner's purpose for mutation testing is to show how to improve the suite. The diff run and
the sample point at a few recurring weaknesses, each fixable with one or a few tests rather than
one test per mutant:

- **Degenerate fixture values.** One example whose values make wrong arithmetic agree (S2, S25),
  or a pattern tested at one bytecode position (S19, S26). Fix: a second, deliberately
  different example; parametrize positions and values.
- **Identity instead of equality.** Tests pass the same UUID object they compare against (diff
  run, `==` → `is`). Fix: reconstruct inputs (`UUID(str(x))`) as real callers do.
- **Record invariants unpinned.** `frozen=True` on `RetrievalHit`, `RecallSummary`,
  `DocumentEvidence`, `ResolvedSpan`, `Viewer` survives. Fix: one parametrized test over the
  record models (assignment raises, `hash()` works).
- **Lifecycle and configuration branches.** Close/reopen of the default cache, non-SQLite URLs,
  default `chunk_size`, budget edges. Tests check that a computation ran, not the state after.
- **Call-shape contracts.** Keyword-only parameters and `@abstractmethod` on Protocols survive;
  minor, cheap to pin where the contract is approved.

Noise to discount when reviewing: `type(x) is T` versus `==`, single-column `[0]`/`[-1]`,
unreachable bytecode-end guards, `Literal`-domain comparisons.

## Assessment

- The tool works: full pass 16.5 min on jolly, diff-scoped run under a minute with survivors
  that review in minutes and name concrete tests. Selection is sound in the sample; misses come
  from compile-time effects and are caught by confirmation.
- Selection is not where the time goes: survivor confirmation and import-time code are. Neither
  needs changing for diff-scoped use. Possible later optimisations, only if runs get slow: a
  per-mutant timeout from measured test durations (timeouts cost 10%), and finding out why
  `datatype/ids.py` lines count as import-time.

## Follow-up tests (observed)

Each new test fails against its mutant in a scratch copy and passes on the real code:

- Gap 1: the mutated-global rejection test is parametrized with a body that puts `queue.pop()`
  past the bytecode midpoint (`tests/test_computation_identity.py`).
- Gap 2: the HotpotQA fixture title `B` became `Bb` (offset 3), and each gold span is checked
  against the text it selects (`tests/test_dataset_files.py`).
- Gap 3: the id layout test runs over `notes.md` and `other.md`, whose payload bit 62 differ
  (`tests/test_ids.py`).
- Gap 4: after `close_default_cache()`, `default_cache()` must return a new owner
  (`tests/test_cache_defaults.py`).

Remaining queue: gap 5 and the call-shape survivors touch the store, which the concurrent storage
topic is redesigning; the `frozen=` record test touches records (Viewer is deferred) and waits
for the same reason. The other minor gaps in the sample (admin `reusable_bytes`, default
`chunk_size`, `ResolvedSpan` ordering, budget edges, S19 counter position) are open.
