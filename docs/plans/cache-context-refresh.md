# P3 — refresh effective computation context

Status: owner-approved option A implemented and verified.
Owner: "A is sufficient"; document mixed-context execution limits, without post-miss revalidation.
Contract: [context refresh](../specs/cache-context-refresh.md).
Owner requested proceeding with P3. Requirement is settled; do not re-ask whether changing
effective globals should invalidate computation identity.

Goal: default automatic computation identity reflects represented context at each lookup,
with stable A→B→A reuse and unchanged inference boundaries.
Architecture: remove full-definition memoization; calculate decorator identity locally per call;
retain immutable-code/disassembly caching and the current non-strict static projection.
Use the existing checkout/branch; preserve concurrent benchmark brainstorming/questions.

## Ownership and change budget

One scoped implementation worker owns `src/triplum/utils/fingerprint.py`,
`src/triplum/cache/identity.py`, `src/triplum/cache/steps.py` and focused identity/cache tests.
Main owns the contract, plan, capture, open questions and handoff. Delegate published docs sync
after implementation; main inspects it and runs strict build/examples.

No cache backend/schema, codec, argument protocol, data projections, tracing-policy changes,
manual dependency declarations, version numbers or compiled reader machinery. If required
correctness expands those boundaries, pause the affected work and report the evidence.

## Steps

- [x] Add red/green real SQLite workflow coverage for the same function and same explicit input
  under description A→B→A. Count actual executions; reopening the owner must reuse retained A/B.
  Cover both decorator forms with automatic identity, not a fixed process_id masking the issue.
- [x] Cover current direct definition/mixin identity after represented dictionary mutation and
  replacement, closure rebinding, defaults/keyword defaults, helper settings and helper rebinding
  through module attributes, plus supported class constants. Existing mapping-order projection
  must remain unchanged. Prefer parameterized focused cases over redundant pipeline fixtures.
- [x] Remove only `definition_hash`'s complete-definition `@functools.cache`; keep
  `content_key("python-definition", _definition(definition, _Definitions(definition)))`
  and bounded immutable caches intact. Update the public docstrings.
- [x] Static decorator computes `effective_identity = process` or a fresh automatic fingerprint
  into a call-local variable under `suspend_tracing()` before lookup. Remove the nonlocal digest
  memo; retain lazy codec initialization lock. Preserve explicit overrides and traced dispatch.
- [x] Verify a configured CachedStep sees changed helper globals with unchanged selected config;
  custom fingerprint overrides retain full control. Cover cache=None, fixed process_id,
  bookkeeping counter/log exclusions, existing semantic-mutation rejection and unchanged digest
  compatibility. Verify retained immutable-code cache use without timing assertions.
- [x] Run focused tests/typing/lint. Record a representative same-machine static hit measurement
  before/after and real execution counts; assess cost without an invented performance threshold.
  If results justify extra dependency machinery, return that new tradeoff to the owner.
- [x] Delegate computation guide/spec/flow sync, with a runnable A→B→A example. Replace first-use
  freeze descriptions with per-lookup freshness and stable-during-call bounds. Inspect examples;
  update identity/cache specs, handoff, capture and Q20 status.
- [x] Fresh spec/general/consistency/performance review and host Opus diff review. Read complete
  peer response, preserve dissent, fix defects and rerun affected verification. Full checks:
  pytest branch coverage/durations, ty, Ruff/format, Cargo check/test and strict MkDocs.
- [x] Commit the coherent scoped change locally with staged-snapshot hooks. Preserve concurrent
  files. No push, PR, merge or remote CI requested; report verified state and next design frontier.

Owner approval covers this option A scope and its local verification/commit stopping point.

Verification: 312 tests, 90% branch-inclusive coverage; ty, Ruff/format, Cargo check/test,
strict MkDocs and 12 affected published-guide Python blocks passed. Fresh reviews are clear.
Opus diff review added suspended static-step fingerprint preparation; its mutation-detection
expansion was rejected under the owner-selected stable-context boundary. Details in the contract.
