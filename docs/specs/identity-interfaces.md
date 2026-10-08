# Identity interfaces: first review

Status: the owner authorized automatic configured-computation identity and documentation cleanup.
The bounded definition/configuration rules below are implemented and independently reviewed.
The follow-up [data-model convenience contract](data-model-fingerprints.md) supplies default field
projections without handwritten fingerprint methods. Record identities, dataset identities and
schema equivalence remain separate review items.

## Direction from the owner

Avoid manually maintained version numbers in fingerprints. Data or relevant structural changes
should change data identity naturally; relevant computation changes should change computation
identity naturally. Explicit semantic field selection remains required so bookkeeping timestamps,
cache resources, counters and execution policy do not define a reusable value.

A type/kind discriminator is not a version counter: it distinguishes different meanings of
otherwise equal fields. Do not substitute a manually bumped label for hashing relevant content
and definitions. The previous recommendation of manual implementation revisions is withdrawn
under this clarified requirement.

Settled decisions remain:

- Cache inputs and outputs implement `fingerprint()`, returning full SHA-256 hex. Pydantic is the
  default serialization surface, not an implicit definition of semantic equality.
- A→B→A restores value identity; equal outputs from different upstream computations can reuse
  downstream results. Producer history does not define the next step's input identity.
- Cache keys contain computation and input digests, with no codec format key or migration layer.
- Bare `@cached`, explicitly owned caches and `CachedStep` remain supported conveniences.
- Record property→method migration is already agreed in [Record types](record-types.md#decisions),
  but semantic inputs and deterministic UUID construction still require their own review. Source's
  at-least-24-bit collection tag preference, A→B→A requirement and the agreed Chunk allocation stand.
- Record UUIDs must not change merely because processing code changed. Code belongs in computation
  identity; scoped semantic record data belongs in record identity.

## Identity requirements and audit findings

| Change | Necessary identity behavior | Current limitation |
| --- | --- | --- |
| A consumed input field/value changes | Input fingerprint changes | Explicit methods only see selected fields |
| An unrelated bookkeeping field changes | Input fingerprint stays equal | Whole-object/model dumping includes it |
| Schema annotation or validator changes, serialized values stay equal | Depends on whether semantic meaning changed | A hash of field names/values alone does not see declarations or validation code |
| lower() changes to casefold(), input unchanged | Computation fingerprint changes | Explicit fixed process digests do not see code edits |
| Output contract changes without function source changing | Prevent incompatible reuse | Current function inference does not inspect the output model definition |
| Cache implementation, queue policy or counters change | Semantic identities stay equal | Current class/MRO hashing can include plumbing |

Adding a schema field does not necessarily change an explicit projection. Conversely, hashing an
entire Pydantic JSON schema would also track descriptions and unrelated bookkeeping declarations.
The problem to solve is selecting relevant definitions, not adding a schema-version field.
Serialization format remains independent; this is not approval to reintroduce a codec namespace.

## Audit inventory before this change

| Surface | Current identity | Consumer / mismatch |
| --- | --- | --- |
| `content_key(kind, payload)` | Namespace plus sorted JSON | Shared helper; does not define arbitrary-Python equivalence |
| Source/Chunk fingerprint properties | Origin/text, plus chunk offset | SQL columns; omit storage IDs and Chunk parent reference |
| Historical `Fingerprinted.fingerprint()` | Qualified class, class/base source and every attribute | Four reference steps; includes resources, collapses some type distinctions |
| `function_fingerprint()` | Function source/name/defaults/nonlocal captures | Frozen by the decorator; globals/helpers/model definitions not discovered |
| `Fingerprintable.fingerprint()` | Author-declared semantic value | Cache input/output boundary |
| `CachedStep.fingerprint()` | Author-declared computation | Re-evaluated per call; resources must stay out |
| Dataset/stream `fingerprint()` | Concrete source's chosen logical data or recipe | Full record dumps, bytes or source+selection composition differ |
| Record `id` | Current UUIDv7 identity | Store references; UUIDv8 layouts remain under separate review |

The pre-change audit reproduced these findings:

- Configured-object hashing equates list/tuple and integer/string dictionary keys even when a
  computation distinguishes them. The JSON helper can make the same conflations, so replacing
  the mixin does not by itself fix arbitrary handwritten encodings. Function inference already
  distinguishes lists/tuples and preserves dictionary iteration order.
- Two MarkdownFolder roots with identical names/bytes have equal dataset fingerprints but emit
  different absolute origins. RecordDataset instead includes full dumps and generated IDs.
- Changing record properties into methods would remove the shape mismatch but not the provenance
  problem: FixedSize copies Source.id into output Chunk.source_id, which current fingerprints omit.
- The current generic mixin cannot supply CachedStep identity unchanged: abstract-method/base order
  can prevent instantiation, and its all-attribute traversal encounters the mixin's locks/resources.

The inventory's focused existing suite passed 41 tests despite these gaps. Temporary probes
reproduced the cases; these are missing invariants, not proof of safe interchangeability.

## Proposed foundation, unchanged method shape

```python
from abc import abstractmethod
from typing import Protocol


class Fingerprintable(Protocol):
    @abstractmethod
    def fingerprint(self) -> str:
        """Return the full SHA-256 hex digest of the declared semantic value."""
        ...
```

Purpose: identify the data the operation actually consumes. Input: current selected semantic
state. Output: the digest. Equal identities promise interchangeable semantic values under the
declared type contract, subject to ordinary digest-collision assumptions. Do not retain a digest
across semantic mutation without an explicit invalidation/immutability rule.

For today's explicit projection, no manually bumped version is necessary:

```python
from pydantic import BaseModel
from triplum.utils.cache import content_key


class TextValue(BaseModel):
    text: str
    observed_at: int

    def fingerprint(self) -> str:
        return content_key("example.TextValue", {"text": self.text})


assert (
    TextValue(text="A", observed_at=1).fingerprint()
    == TextValue(text="A", observed_at=2).fingerprint()
)
```

This example does not claim automatic schema-change detection: that is precisely the current
limitation under review. Consumers using observed_at in the semantic answer need a different
projection. Serialization may retain old bookkeeping; attach current-event data after reuse.

## Configured computations: approved direction and bounded implementation

```python
class FingerprintedComputationMixin:
    def fingerprint_config(self) -> dict[str, object]:
        """Select effective settings; required when using the default fingerprint."""
        raise NotImplementedError

    def fingerprint_dependencies(self) -> tuple[object, ...]:
        """Declare additional Python definitions or fingerprintable dependencies."""
        return ()

    def fingerprint(self) -> str:
        """Hash loaded definitions, explicit configuration and declared dependencies."""
        ...
```

`CachedStep` inherits this implementation. Existing overrides of `fingerprint()` retain complete
control and need not implement the configuration hook. Stateless implementations return `{}`.
This requirement is checked when using default fingerprinting rather than making old explicit
fingerprint overrides abstract. Configuration is re-evaluated per call, so A→B→A restores identity.
Resources, locks, counters, policy and timing attributes are never traversed implicitly.

The automatic code boundary is loaded Python method definitions in the concrete class and its
ordinary bases. It covers functions, static/class methods and property accessors, including
inherited definitions and nested code. Exact framework bases (`FingerprintedComputationMixin`, `CachedStep`,
`object`, `ABC`, `Protocol`, `Generic`) and typing-generated Protocol helpers are excluded.
Domain Protocol method bodies remain included because explicit subclasses inherit concrete defaults. It is deliberately
conservative: unused or overridden application methods can invalidate a result. There is no
heuristic classifying arbitrary third-party packages as computation or infrastructure.

Definition hashing uses loaded code rather than reading a possibly edited source file: bytecode,
exception tables, argument counts, runtime flags, names and recursively typed constants, plus
evaluated defaults and captured nonlocals. Source locations and filenames are excluded. Non-executable docstring
text changes are ignored; a docstring literal referenced by executable bytecode remains semantic; adding/removing a docstring can conservatively change the digest because
Python can change constant indexes and bytecode. Cross-interpreter/compiler stability is not
promised. Definitions must not be monkeypatched after their first fingerprint: definition digests
are retained for fast repeated lookups. Configuration/dependencies must not mutate during a call.

Immutable own-class scalar/tuple/frozenset constants are included automatically, including prompts and
templates. Other class attributes (including regexes, Enum members and nested classes), metaclass/descriptor state, global helpers, model weights, files
and environment are not inferred: select their effective values and declare actual dependencies.
An explicitly declared Python definition hashes its bounded loaded implementation; a fingerprintable
object supplies its own semantic digest. A Path identifies its pathname only, not file bytes.
The implicit `__class__` closure used by `super()` and Python 3.14
`__classdict__` annotation namespace are covered by selected class ancestry rather than recursively
fingerprinting the class object/namespace. Python function captures (including wrapped methods) are
recursively identified; recursive capture cycles require an explicit fingerprint. Python 3.14 annotation
definitions are hashed as loaded code. CachedStep additionally includes an explicit output_type name;
this tracks type selection without claiming automatic schema equivalence.

`definition_hash(function_or_class)` exposes the same loaded-definition digest for composing an
explicit process_id. `source_hash` remains the AST/source utility: it reads the current source file
on first use, so it does not guarantee identity of previously loaded code after that file changes. Bare `@cached` retains its existing
source/default/nonlocal-capture inference at decoration time; this change does not turn it into
transitive dependency discovery. Explicit `process_id` can compose actual definition/content hashes
when that convenience boundary is insufficient. Neither API requires manually bumped version labels.

No automatic Pydantic schema or validator equivalence is claimed. An author whose computation depends
on an output definition must select its relevant contract or dependency. Equal projected values remain
interchangeable where the declared semantics permit that, regardless of creation or producer history.

## Configuration encoding is a local boundary

Selected configuration accepts exact finite scalar values, string-keyed mappings, lists/tuples,
Paths and nested values with `fingerprint()`. Nested fingerprint methods take priority; Pydantic
serialization is never a fallback definition of semantic equality. Unsupported resources and
non-finite floats fail clearly. Lists and tuples retain their distinction. Config dictionaries are
mappings, so insertion order is irrelevant; a computation observing iteration order must project
ordered pairs explicitly. Bare decorator captures retain their existing ordered-dictionary behavior.

The generic `content_key` helper is unchanged: its callers include records/datasets with contracts
still under review. Strictness at the new configuration boundary does not redefine their identities.

## Documentation and verification

The cache parent has subpages for value fingerprints, computation fingerprints, serialization,
storage, ownership/policy and administration. They lead with bare decorator use; configured step,
codec and backend extension examples follow only when those concerns are needed. Record and dataset
identity remain linked separate topics. One Protocol is not automatically a separate concept.

Implementation acceptance covers A→B→A, bookkeeping-only changes, automatic relevant-code
changes, explicit external-content changes, two upstream processes producing equal outputs,
mutation timing, and provenance-safe binding. Test FixedSize's two-parent counterexample before
making records cacheable. A Protocol cannot detect omitted semantic fields by itself.

## Independent evidence and review

[Bazel](https://bazel.build/remote/caching) separates action identity from output content and
identifies untracked dependencies as a source of false hits. [Dask custom tokenization](https://docs.dask.org/en/stable/custom-collections.html)
and [deterministic mode](https://docs.dask.org/en/latest/generated/dask.tokenize.tokenize.html)
support explicit extension contracts with bounded inference. [Joblib](https://joblib.readthedocs.io/en/latest/user_guide/memory.html)
documents irrelevant instance-state invalidation. [Hugging Face](https://huggingface.co/docs/datasets/en/about_cache)
uses transform lineage, which would prevent this project's cross-process equal-value reuse.
[Pydantic serialization](https://docs.pydantic.dev/latest/concepts/serialization/) is a projection
mechanism, not a definition of semantic equality. [FastAPI's tutorial](https://fastapi.tiangolo.com/tutorial/)
supports gradual, separately addressable concepts.

Claude Opus 5.5 (`claude-opus-5-5`), review `d028fb53a1354901b357aa6253ba7666`, examined the earlier
explicit-manual-revision versus code/config hook proposal. It supported manual methods under
those assumptions. **Superseded recommendation:** the owner then clarified that manual versions
should be avoided; this is a new constraint, not peer agreement with the revised hook proposal.
**Retained findings:** JSON coercion is orthogonal, namespace responsibility matters, full-MRO
hashing includes unrelated plumbing, and frozen decorator captures differ from live CachedStep
configuration. Tests attempted JSON collisions/NaN, mixin composition, MRO inclusion, mutation,
existing consumers and provenance. No performance measurements were made.

Local audits and the owner-requested persona trials are recorded in
[Cache interface trials](../personae/runs/cache-interfaces.md). The bounded computation implementation is authorized; structural-data rules and record migration
remain separate owner-review work.


### Automatic-definition design review

Claude Opus 5.5 (`claude-opus-5-5`), review `abca1b25fce349968e59215b7754fbb4`, challenged the
bounded proposal. **Changed decision / added verification:** track Python 3.14 annotation definitions
and explicit output type selection; recurse into captured wrapped Python functions with a cycle guard;
exclude Protocols only when `_is_protocol is True`; include immutable own-class constants; expose
`definition_hash` as the safe loaded-code building block. Tests cover these paths and loaded source drift.
**Rejected reasoning with counterexample:** the peer considered docstring-constant deduplication only a
false-miss risk. Two functions with docstring/returned literal respectively `a` and `b` have identical
bytecode and use constant zero; stripping that slot would create a false hit. The implementation retains
any executable reference to the slot, with a regression test.
**Added verification:** a concrete Protocol can acquire `object.__init__` in its own namespace
after instantiation. That exact framework initializer is excluded, preserving automatic identity
for stateless Protocol implementations.

Peer attacks inspected annotation-only changes, wrapper captures, Protocol flags, docstring slots,
existing explicit overrides and in-repository Protocol bodies. The documented class hierarchy rule
can conservatively include third-party ordinary base methods; no arbitrary dependency graph is inferred.
External research confirmed explicit tokenization contracts in Dask, incidental-self-state pitfalls in
Joblib, and untracked-input risks in Bazel. Joblib's development implementation also informed checking
exception tables and recursive code constants, without treating it as a stable public API contract.


### Implementation review

Claude Opus 5.5 (`claude-opus-5-5`), review `5066d2216f9a4772969f35bb51698784`, found one inherited
behavior defect: skipping complete domain Protocols omitted their concrete default methods.
**Unique defect / changed decision:** include domain Protocol definitions while excluding exact
typing-generated helpers; a real default-method edit regression failed before the fix.
**Changed decision / added verification:** include frozenset class constants using the existing
canonical constant encoder. Both new false-hit regressions now pass.

**Retained dissent, rejected broader recommendation:** the peer proposed rejecting every class
attribute that cannot be automatically encoded. The owner retained the bounded rule and explicit
configuration boundary: class-held clients/resources must remain usable without overriding the entire
fingerprint when selected configuration already declares their semantics. Regexes, Enum members,
mutable containers and nested classes require explicit projections/dependencies; silently claiming all
immutable objects are covered would be wrong. A compiled-regex projection regression verifies that path.

**Already addressed by independent reader / added documentation:** Pydantic model classes are not
automatically hashable schemas. The fresh reader hit `Text.__signature__`, and a focused retry verified
the explicit limitation and plain-function/helper composition after the documentation repair.
**No decision impact:** retain the small exact framework exclusion set and fixed-capture requirement,
rather than a new marker convention or prohibition on all captured mutable containers.
**Simplification:** removed the uninformative digest-length print and duplicate implementation prose;
clarified the error for captured classes.

The peer tried annotation changes (including postponed annotations), adaptive bytecode specialization,
docstring presence/content, abstract base bodies, unsupported descriptors and output-type selection.
It did not run the full suite/build or measure hot-path performance; maintainer checks are separate.
