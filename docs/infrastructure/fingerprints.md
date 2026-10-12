# Fingerprints

A fingerprint identifies the content you chose to treat as equivalent. For caching, two questions
matter: **is this the same input data?** and **is this the same computation?** The cache matches both.
A record's storage ID answers a third question: which persisted record does this refer to?

```python
from triplum.datatype import Source
from triplum.steps.chunking import FixedSize

first = Source(origin="notes/returns.md", text="Returns within 30 days.")
second = Source(origin="notes/returns.md", text="Returns within 30 days.")

print(first.id == second.id, first.fingerprint() == second.fingerprint())
print(FixedSize(20).fingerprint() == FixedSize(20).fingerprint())
print(FixedSize(20).fingerprint() == FixedSize(30).fingerprint())
```

Output:

```text
False True
True
False
```

The sources contain equivalent data but have distinct UUIDv7 storage IDs. The chunkers identify
configured computations: changing the chunk size changes their identity.

## Choose the identity question

For Pydantic data, inherit [`FingerprintedDataModel`][triplum.datatype.FingerprintedDataModel] to get a
`fingerprint()` method based on actual field values and qualified type name. Use `@cached` on the
computation. Start with [Value fingerprints](cache/fingerprints.md) for the smallest example,
bookkeeping exclusions and custom projections. External value types can implement the method
themselves. [Computation fingerprints](cache/computations.md) explains configured
steps and automatic function inference. Those pages include complete extension examples.

This page describes existing record, object and dataset identities. They use related digest
helpers but have different equality promises; the common name does not make them interchangeable.

## Existing record fingerprints

[`Source`][triplum.datatype.source.Source] and [`Chunk`][triplum.datatype.chunk.Chunk] expose
`fingerprint()` methods, recomputed on each call:

| Record | Included fields | Excluded identifiers |
| --- | --- | --- |
| Source | `origin`, `text` | `id` |
| Chunk | `origin`, `start`, `text` | `id`, `source_id` |

Equal record fingerprints therefore do not mean equal storage identity or provenance. Two chunks
can have equal fingerprints while referring to different source records. The digest is absent
from model dumps and JSON; SQL storage fills its indexed fingerprint column explicitly.

These methods satisfy the cache's `fingerprint()` requirement and support nested value
fingerprints. That does not make every record consumer safe to cache: computations that use
excluded IDs or parent references need those values in their effective input identity. Cached
records restore their stored IDs and references unchanged. For example, a cached `Source -> Chunk`
function that copies `source.id` into `chunk.source_id` returns the first source's parent reference
when called with an equal-fingerprint Source that has a different ID. Include binding references
in the effective input identity, or attach them after reusing an unbound result.
Define an explicit [value model](cache/fingerprints.md) when the computation needs another projection.

## Configured-object identity

[`FingerprintedComputationMixin`][triplum.utils.fingerprint.FingerprintedComputationMixin] in `triplum.utils.fingerprint` supplies
a `fingerprint()` implementation used by steps such as
[`FixedSize`][triplum.steps.chunking.FixedSize]. It combines the qualified class name, loaded application method definitions,
immutable class constants, selected configuration and statically resolved application helpers. It does not scan instance attributes.

The initial `FixedSize` example uses this implementation: equal sizes identify equivalent
chunkers, while different sizes identify different computations. Settings are selected explicitly;
runtime counters and clients stay out. For cached functions with settings, start with a
[function factory](cache/computations.md). The same guide shows `CachedStep` for existing classes.

The [computation guide](cache/computations.md#select-settings-for-a-computation-class) explains
configuration selection and supported class constants. Decorators and computation classes share
loaded-definition hashing and bounded helper discovery. See the
[automatic boundary](cache/computations.md#know-the-automatic-boundary) for external resources,
dynamic dispatch and complete `process_id` overrides.

## Dataset identity

[`Dataset`][triplum.utils.data.dataset.Dataset] and
[`IterableDataset`][triplum.utils.data.dataset.IterableDataset] require `fingerprint()` methods.
Their contract describes logical output: equal identities promise the same ordered logical data,
including source revision and transformations. Computing identity must not consume iteration
state. Physical loader batch size is not content, and identifying a one-shot stream does not
make it replayable.

Concrete implementations choose their own projection:

- [`RecordDataset`][triplum.utils.data.dataset.RecordDataset] hashes the ordered, complete
  `model_dump(mode="json")` of every record, recomputing on each call. It does **not** delegate to
  each record's `fingerprint()` method. Freshly created Source records with matching
  content but different IDs therefore produce different RecordDataset identities.
- [`MarkdownFolder`][triplum.datasets.markdownfolder.MarkdownFolder] hashes its fixed, sorted file
  list by absolute path and bytes, matching the emitted `Source.origin` and `text`. Reading an
  unchanged folder again gives the same dataset identity, although accessed Source records receive
  fresh IDs. A copy of the folder elsewhere has a different identity, because its origins differ.

For example, record content equivalence and full-record dataset equivalence differ:

```python
from triplum.datatype import Source
from triplum.utils.data import RecordDataset

first = Source(origin="notes.md", text="Hello")
second = Source(origin="notes.md", text="Hello")
print(first.fingerprint() == second.fingerprint())
print(RecordDataset([first]).fingerprint() == RecordDataset([second]).fingerprint())
```

Output:

```text
True
False
```

Choose the dataset's identity according to its concrete contract; a method named `fingerprint`
alone does not establish that it excludes storage IDs or bookkeeping.

Next: [Cache](cache.md).
