# Multiargument cache decorators — P2 proposal

Status: completed and verified. Owner: "P2 sounds good, proceed."
Contract: [call arguments](../specs/cache-call-arguments.md).
Existing checkout/branch per AGENTS.md; preserve concurrent files.

Goal: multiple named/positional arguments become one deterministic input digest, with preserved
call typing, existing single-input entries, and static/traced correctness.

## Ownership and budget

One scoped implementation worker owns `cache/steps.py`, `cache/runtime.py`, `cache/tracing.py`
and focused cache tests. Reuse the existing typed encoder without public helper/module changes.
Docs worker owns cache concept/tracing guides and authoritative cache interface spec; main owns
the interview capture, open questions and handoff. Review and inspect docs before building on them.

Expected changed areas: decorator overloads/binding, prepared-digest lookup, named traced
receivers and regressions. Existing value projections, codec/backend/schema, CachedStep's
one-item public contract and computation discovery policies retain their current contracts.
No cache-key override API, argument wrapper for users, record ID migration or benchmarking work.
Default static-global refresh remains a separate follow-up, not a delivered claim for P2.

## Steps

- [x] Add real SQLite red tests for both decorator forms. Use a deterministic fingerprintable
  result and count actual computations. Example calls for one wrapped `render` function:

  ```python
  first = render("Evidence", "Collection")
  assert render(context="Collection", text="Evidence", separator="\n") == first
  assert computations == 1
  assert render("Different", "Collection") != first
  assert render("Evidence", "Other collection") != first
  assert render("Collection", "Evidence") != first
  ```

  Include three arguments, defaults, zero args, ordered varargs/residual kwargs, supported
  primitive plus fingerprintable inputs, unsupported values/malformed top-level fingerprints,
  invalid Python calls before backend access and cache=None bypass. Keep the existing
  decorator/CachedStep entry-sharing test unchanged. Verify reopen reuse and A→B→A mutation.

- [x] Implement binding and combined identity in steps.py as declared. Retain sole-input raw
  keys; name every other bound parameter in the canonical hash. Generalize static `_call` to
  receive digest/invocation while keeping CachedStep's input method. Apply ParamSpec overloads
  and forwarding in runtime.py. Preserve functools.wraps and lazy default cache behavior.

- [x] Adapt tracing with original computation and named actual receivers. Test a mixed string
  plus model call using string methods; independent changes to methods on both object args;
  two known objects sharing one method implementation; same object under two parameter names
  followed by distinct equal-value objects; receiver labels named input/owner; and child-hit
  manifest propagation. Fingerprint work must be suspended and static child hits must keep
  their existing conservative parent-admission behavior. Pause/report if correct support would
  require unrelated inference expansion rather than these explicit receiver bindings.

- [x] Add signature/type probes with `assert_type`: named positional, keyword-only and default
  arguments retain their original types under both decorator forms. Use ty and narrow internal
  call-binding boundaries rather than broad Any or ignores. Run focused static/traced tests
  and checks; verify no approved old tests were weakened for new implementation behavior.

- [x] Delegate docs sync, including a runnable multiargument example and the input-value/variadic
  contracts. Main inspects changes and strict MkDocs. Run full CONTRIBUTING checks: pytest with
  branch coverage/durations, ty, Ruff/format, Cargo check/test and strict docs. Exercise affected
  teaching examples; independent fresh-context and Claude Opus diff review; address defects,
  preserve dissent and rerun affected checks. Commit coherent verified changes locally and run
  staged-snapshot hooks. No push/PR requested; report local verification and no remote CI.

Acceptance means this named scope only. Any new public API or discovered identity-policy
tradeoff returns to the owner; routine internal implementation choices stay with the worker.
