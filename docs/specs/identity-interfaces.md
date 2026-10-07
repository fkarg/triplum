# Identity interfaces: first review

Status: owner-review draft, not implemented. The owner requested an interface/concept audit,
starting with identity, and cache subpages explaining how to implement each extension interface.
The documentation describes current behavior; proposed API changes remain separate.

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

## What a change can and cannot affect automatically

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

## Current interface inventory

| Surface | Current identity | Consumer / mismatch |
| --- | --- | --- |
| `content_key(kind, payload)` | Namespace plus sorted JSON | Shared helper; does not define arbitrary-Python equivalence |
| Source/Chunk fingerprint properties | Origin/text, plus chunk offset | SQL columns; omit storage IDs and Chunk parent reference |
| `Fingerprinted.fingerprint()` | Qualified class, class/base source and every attribute | Four reference steps; includes resources, collapses some type distinctions |
| `function_fingerprint()` | Function source/name/defaults/nonlocal captures | Frozen by the decorator; globals/helpers/model definitions not discovered |
| `Fingerprintable.fingerprint()` | Author-declared semantic value | Cache input/output boundary |
| `CachedStep.fingerprint()` | Author-declared computation | Re-evaluated per call; resources must stay out |
| Dataset/stream `fingerprint()` | Concrete source's chosen logical data or recipe | Full record dumps, bytes or source+selection composition differ |
| Record `id` | Current UUIDv7 identity | Store references; UUIDv8 layouts remain under separate review |

Reproduced findings:

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

## Revised recommendation for configured computations

Prefer relevant code plus explicitly selected effective configuration, instead of manual revision
labels or all-instance introspection. Keep the public `fingerprint()` method and bare decorator
convenience. A configuration hook is a reasonable implementation candidate:

```python
from abc import ABC, abstractmethod


type FingerprintData = (
    None | bool | int | float | str | list[FingerprintData] | dict[str, FingerprintData]
)


class Fingerprinted(ABC):
    @abstractmethod
    def fingerprint_config(self) -> dict[str, FingerprintData]:
        """Select effective settings and declared external dependency identities."""
        ...

    def fingerprint(self) -> str:
        """Hash relevant computation code and selected configuration."""
        ...
```

This is a candidate declaration, not an approved implementation. It still needs a precise rule
for relevant code. Do not retain the current full-MRO scan: domain Protocols, CachedStep plumbing
and ABC code would enter identity. Hashing only a method can instead miss helpers and inherited
behavior. External model/file dependencies must identify actual content or another stable
upstream identity, not an untracked mutable object. The owner should not maintain arbitrary
counters to compensate for missing dependencies.

Keep the choice proportional: explicit declarations of dependencies can be simpler and safer
than recursive discovery of every imported object. Unrestricted dependency tracing, a registry,
new object hierarchy and whole-schema hashing are not implied. A final declaration and extension
example require independent review before implementation.

## Encoding is a separate decision

Restricting a configuration hook to explicitly encoded finite JSON values avoids silent coercion
at that boundary. Ordered lists retain order; dictionaries treated as mappings do not encode
iteration order. A consumer that observes another distinction must represent it explicitly.

Do not silently tighten `content_key` in the same change: existing callers include tuples and
records whose equivalence remains under review. Rejecting unsupported values versus supplying
a typed canonical encoder needs a consumer audit. Likewise, dataset content identity versus
source/selection recipe identity needs its own review before collection seeding.

## Documentation and verification

The cache parent now has subpages for value fingerprints, computation fingerprints, serialization,
storage, ownership/policy and administration. Custom value, configured step, codec and backend
examples describe current APIs; they are not a publication of this proposal. Record and dataset
identity remain linked separate topics. One Protocol is not automatically a separate concept.

Implementation acceptance should cover A→B→A, bookkeeping-only changes, automatic relevant-code
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
[Cache interface trials](../personae/runs/cache-interfaces.md). The revised code-selection and
structural-data rules remain for the next owner review; no production behavior has changed.
