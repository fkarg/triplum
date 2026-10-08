# Fingerprints for Pydantic data values

The owner approved a data-model convenience base alongside computation decorators. The normal
example is a `Text(FingerprintedModel)` declaration and a bare `@cached` function. Existing
Source/Chunk records and dataset identities are not migrated by this change.

## Contract

```python
class FingerprintedModel(BaseModel):
    fingerprint_exclude: ClassVar[frozenset[str]] = frozenset()

    def fingerprint_data(self) -> dict[str, object]: ...

    def fingerprint(self) -> str: ...
```

Import from `triplum.datatype`. Default identity consists of the qualified model kind and actual
field values. The default projection keeps declared `fields` and allowed `extras` in separate
namespaces so an alias/extra collision cannot hide either value. Explicit exclusions remove bookkeeping from identity
without removing it from serialization. Exclusions name declared fields; unknown names fail at class
definition rather than silently accepting a typo. Extras can be excluded through a custom projection.
An override of `fingerprint_data()` selects another semantic projection; a complete `fingerprint()`
override remains available for custom identity contracts.

Equivalent selected values have equal full SHA-256 fingerprints, regardless of construction order,
explicit versus implicit defaults, declaration order or producer history. Fingerprints are recomputed
so semantic mutation A→B→A returns to the original identity. Implementation code, schema declarations,
validators, computed fields and private attributes are not automatically included. No timestamp
heuristics or manually maintained version strings are required.

## Value boundary

Use actual field values rather than serialization output. Pydantic serialization can hide nested
subclass fields or explicitly excluded fields; those values still affect identity by default.
Nested values must supply their own `fingerprint()` semantic projection (usually by inheriting
`FingerprintedModel`) or be projected explicitly. There is no fallback that silently serializes plain
nested models. Nested subclass identity makes serialization loss visible to the existing cache codec's
fingerprint round-trip check.

The default encoder supports typed scalars, finite floats, lists, tuples, string-keyed mappings,
paths, bytes, UUIDs and nested fingerprintable values. Mapping order does not affect identity;
sequence order and list/tuple distinctions do. Paths identify spelling, not file contents.
Unsupported semantic values need an explicit projection or a nested `fingerprint()` implementation.
There is no arbitrary-object serialization fallback or claim of universal Pydantic-type support.

Changing excluded metadata may reuse an earlier serialized result carrying earlier metadata.
Consumers that need current-event metadata must attach it after reuse. Excluding any field promises
that consumers do not depend on that field. Shared content does not grant shared provenance or ACLs.

## Verification and evidence

Exercise bare decoration with a real SQLite cache, nested projections, defaults, mutation, allowed
extras, field serialization exclusions, lossy nested subclass round trips and unsupported values.
The source for serialization pitfalls is [Pydantic's serialization documentation](https://docs.pydantic.dev/latest/concepts/serialization/).
Local probes reproduced subclass truncation, serialization-only exclusions, computed-field inclusion
and construction-dependent `exclude_unset` output. Independent review is recorded below.

## Independent review

Claude Opus 5.5 (`claude-opus-5-5`), review `707b9ec7b0f2468d9c315a1178f8a506`, supported
the contract after testing shadowed ClassVars/methods, excluded-output metadata, tuple round trips,
subclass truncation, scalar collisions and class naming. Changes: validate reserved field names and
exclusions at class definition; require nested fingerprints/projections instead of duplicating plain
model recursion. Added verification: serialized bookkeeping itself is checked, and ambiguous sequence
annotations that lose tuple identity are refused. Keep the small data encoder separate from computation
encoders: it rejects definitions and does not infer code identity. Surrogate-string handling remains
the existing content_key UTF-8 boundary; this change does not broaden the generic encoder.

Claude Opus 5.5 (`claude-opus-5-5`), diff review `4cc8cd2d1d3b4cfa9a974651fc5d0cef`,
found an alias/extra collision that could hide a declared field and cause a false cache hit.
A real SQLite regression reproduced it; separate `fields` and `extras` projection namespaces fix it.
A second regression rejects string-valued exclusion settings instead of treating them as characters.
Custom projections remain inherited ordinary methods: document responsibility for newly added
subclass semantic fields rather than forbid intentional narrow projections. Other attacks covered
container round trips, extra/reserved names, private fields, scalar distinctions, generic kinds and
nested digest collisions. The peer's assertion that byte serialization errors are skipped background
writes was rejected: serialization happens in the caller and errors propagate there.
