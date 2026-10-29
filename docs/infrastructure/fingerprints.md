# Fingerprints

A fingerprint identifies the content you chose to treat as equivalent. For caching, two questions
matter: **is this the same input data?** and **is this the same computation?** The cache matches both.
A record's ID answers a third question: which record does this refer to?

```python
from triplum.datatype import Collection, Source
from triplum.steps.chunking import FixedSize

collection = Collection(name="Research notes")
text = "Returns within 30 days."
first = Source(collection_id=collection.id, origin="notes/returns.md", text=text)
second = Source(collection_id=collection.id, origin="notes/returns.md", text=text)

print(first.id == second.id, first.fingerprint() == second.fingerprint())
print(FixedSize(20).fingerprint() == FixedSize(20).fingerprint())
print(FixedSize(20).fingerprint() == FixedSize(30).fingerprint())
```

Output:

```text
True True
True
False
```

The sources hold the same collection, origin and text, so they get the same derived ID and the
same fingerprint. The chunkers identify configured computations: changing the chunk size changes
their identity.

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
`fingerprint()` methods, recomputed on each call. Each covers the same fields as the record's
deterministic `id`:

| Record | Fingerprint and `id` fields | Not included |
| --- | --- | --- |
| Source | `collection_id`, `origin`, `text` | `id` |
| Chunk | `collection_id`, `source_id`, `ordinal`, `start`, `text` | `id`, `origin` |

Records with equal fingerprints therefore have equal IDs, collections and parent references.
`Chunk.origin` is left out because it is copied from the source that `source_id` already
identifies. The same document in two collections, or a chunk at a different position, has a
different fingerprint. The digest is absent from model dumps and JSON; SQL storage fills its
indexed fingerprint column explicitly.

These methods satisfy the cache's `fingerprint()` requirement and support nested value
fingerprints. A cached `Source -> Chunk` function that copies `source.id` into `chunk.source_id`
can be reused safely: an equal-fingerprint source has the same `id`. Define an explicit
[value model](cache/fingerprints.md) when a computation should treat records from different
collections, or chunks at different positions, as equivalent.

## Configured-object identity

[`FingerprintedComputationMixin`][triplum.utils.fingerprint.FingerprintedComputationMixin] in `triplum.utils.fingerprint` supplies
a `fingerprint()` implementation used by steps such as
[`FixedSize`][triplum.steps.chunking.FixedSize]. It combines the qualified class name, loaded application method definitions,
immutable class constants, selected configuration and statically resolved application helpers,
rereading this bounded projection on every request. It does not scan instance attributes. Keep
[inputs and context stable during each call](cache/computations.md#keep-inputs-and-context-stable-during-a-call).

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
  each record's `fingerprint()` method, so every dumped field counts, including `Chunk.origin`.
  Because Source and Chunk IDs are derived from their content, equal records give equal
  RecordDataset identities.
- [`MarkdownFolder`][triplum.datasets.markdownfolder.MarkdownFolder] hashes its collection and its
  fixed, sorted file list by absolute path and bytes, matching the emitted `Source.collection_id`,
  `origin` and `text`. Reading an unchanged folder again with the same collection `id` gives the
  same dataset identity and the same Source IDs. A copy of the folder elsewhere has a different identity, because its origins
  differ.

Choose the dataset's identity according to its concrete contract; a method named `fingerprint`
alone does not establish that it excludes storage IDs or bookkeeping.

Next: [Cache](cache.md).
