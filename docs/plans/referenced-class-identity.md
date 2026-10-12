# Referenced application class identity

The owner approved using existing class-definition hashing for discovered application classes
and documenting the remaining limits. This is a refinement of dependency discovery, not a new
cache interface or a promise of complete invalidation. The computation/input/result key structure
does not change. Q7's evidence-counting decisions wait for benchmark design.

## Internal declaration and scope

```python
def _reference(value: object, active: _Definitions) -> object:
    """Encode a statically resolved dependency in the active definition graph."""
```

Inputs: a resolved loaded object and the current application boundary/cycle-tracking context.
Output: the existing canonical identity projection. In static mode, ordinary application classes
try the existing class encoder: loaded methods, ordinary bases and supported immutable constants.
Unsupported walks restore traversal state and retain qualified-name identity. Qualified names
remain the boundary for external classes, traced references and Pydantic model references. The latter are not an
automatic field/validator/serializer contract. Static identities remain frozen on first use.

Example: a cached function calling `Folder().run(value)` changes computation identity when a
freshly loaded `Folder.run` changes. Equivalent definitions retain identity and can reuse results.
Class state, native/external behavior, arbitrary dispatch and output-model contracts remain limited.
No class is instantiated, and no `fingerprint()` or `__hash__()` is invoked on a class object.
Instance `fingerprint()` projections retain their existing meaning.

## Implementation plan

- [x] Consume host Claude Opus design critique and record its serving model and disposition.
- [x] Add a real SQLite regression for fresh class method/inherited-method/constant edits and
  equivalent definitions returning to an earlier computation; run it red before implementation.
- [x] Extend `_reference` to route application classes through `_definition`, preserving cycle
  tracking. Keep external and Pydantic references bounded; avoid executing metaclass hooks.
- [x] Delegate concept/spec documentation synchronization and inspect the resulting diff.
- [x] Run Python tests with branch coverage/durations, typing, Ruff, Cargo and strict MkDocs;
  run affected examples, review the diff, and prepare the coherent verified change for commit.

Captured/configured classes and unsupported descriptors require peer scrutiny before changing
their existing rules. No public custom class-fingerprint hook or Python hash fallback is proposed.

## Review disposition

Host Claude Opus 5.5 (`claude-opus-5-5`), review `ff86122b6d0f4fb8a75d89e095cd4fba`,
found generated/native class and tracing regressions in a naive recursive walk. This changed the
implementation to static-only best-effort expansion with rollback. Tests verify the resulting
fallback and shared-helper behavior. The full attempted falsifications and disposition are recorded
in the [dependency spec](../specs/automatic-helper-identity.md#independent-reviews).

A fresh-context reviewer found a unique metaclass-hook defect: equality/hash-based framework
membership executed custom class hooks. Identity comparisons replace both checks, with regressions
for metaclass hash/equality and unused mutating class methods under tracing. This changed the
implementation; the hash regression failed before correction. The reviewer confirmed the
correction and reported no remaining actionable source/test findings. Final verification:
257 tests, 89% branch-inclusive coverage, typing/lint/format checks, Cargo checks/tests, strict
MkDocs and both affected cache examples passed. Existing SQL cleanup warnings remain.
