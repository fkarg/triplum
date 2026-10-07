# Fingerprints

A fingerprint identifies the content you chose to treat as equivalent. For caching, two questions
matter: **is this the same input data?** and **is this the same computation?** The cache matches both.
A record's storage ID answers a third question: which persisted record does this refer to?

```python
from triplum.datatype import Source
from triplum.steps.chunking import FixedSize

first = Source(origin="notes/returns.md", text="Returns within 30 days.")
second = Source(origin="notes/returns.md", text="Returns within 30 days.")

print(first.id == second.id, first.fingerprint == second.fingerprint)
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

Cacheable values implement an explicit `fingerprint()` method. Start with
[Value fingerprints](cache/fingerprints.md) to select fields, exclude bookkeeping and define your
own Pydantic or custom value. [Computation fingerprints](cache/computations.md) explains configured
steps and automatic function inference. Those pages include complete extension examples.

This page describes existing record, object and dataset identities. They use related digest
helpers but have different equality promises; the common name does not make them interchangeable.

## Existing record properties

[`Source`][triplum.datatype.source.Source] and [`Chunk`][triplum.datatype.chunk.Chunk] expose
`fingerprint` as a **property**, recomputed on access:

| Record | Included fields | Excluded identifiers |
| --- | --- | --- |
| Source | `origin`, `text` | `id` |
| Chunk | `origin`, `start`, `text` | `id`, `source_id` |

Equal record fingerprints therefore do not mean equal storage identity or provenance. Two chunks
can have equal fingerprints while referring to different source records. The computed property
is also included in `model_dump()`; SQL storage retains it in an indexed column.

These properties are **not compatible with the new cache's `fingerprint()` method requirement**.
Passing a Source or Chunk directly to a cached function does not make it a valid cache value.
Their identity migration remains under review. Define an explicit [value model](cache/fingerprints.md) for the data a
computation needs; do not assume an entire record is interchangeable merely because
its content property matches.

## Configured-object identity

[`Fingerprinted`][triplum.utils.fingerprint.Fingerprinted] in `triplum.utils.fingerprint` supplies
a `fingerprint()` implementation used by steps such as
[`FixedSize`][triplum.steps.chunking.FixedSize]. It hashes:

1. The qualified class name, including its module.
2. Source code for the class and its bases, excluding the mixin and typing scaffolding.
3. Every instance attribute in `vars(self)`.

Class source hashing ignores comments, formatting and docstrings. Other code edits, including
renaming a local variable, affect the digest. Moving a class from a script into an imported
module changes its qualified name and therefore its fingerprint. Compare identities in examples
rather than relying on a literal digest remaining stable after edits.

Run this example from a `.py` file: class source must be inspectable. Classes defined through
`exec` or a script piped to `python -` cannot be fingerprinted this way. Other interactive
execution environments are not tested.

```python
from triplum.utils.fingerprint import Fingerprinted


class Prefix(Fingerprinted):
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    def __call__(self, text: str) -> str:
        return self.prefix + text


print(Prefix("note: ").fingerprint() == Prefix("note: ").fingerprint())
print(Prefix("note: ").fingerprint() == Prefix("warning: ").fingerprint())
```

Output:

```text
True
False
```

Attribute handling is broader than the cache's explicit semantic contract:

- Plain strings, numbers, booleans, `None`, paths, lists, tuples and dictionaries are supported.
  The current normalizer collapses list/tuple distinctions, stringifies dictionary keys, and
  ignores dictionary iteration order. Use an explicit method if the computation distinguishes
  these cases; this helper is under review.
- Pydantic models use their entire `model_dump(mode="json")`, even if they also define a
  `fingerprint()` method. IDs and bookkeeping fields in that dump enter the object identity.
- Other objects can supply their own `fingerprint()` method.
- Unsupported values, such as a raw network client, raise `TypeError`.

Consequently, adding a bookkeeping attribute can change an object's fingerprint. For a step with
resources or operational state, implement an explicit fingerprint selecting its effective
configuration. Include revisions for external dependencies: this utility does not hash helper
functions, imported library code or model weights merely because the class uses them.

The cache decorator has a separate automatic **function** identity, covering source, qualified
name, evaluated defaults and captured configuration. It does not discover globals or external
dependencies either. See [computation identity](cache/computations.md) for when
to supply an explicit process digest; the configured-object mixin is not the decorator's algorithm.

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
  each record's fingerprint property or method. Freshly created Source records with matching
  content but different IDs therefore produce different RecordDataset identities.
- [`MarkdownFolder`][triplum.datasets.markdownfolder.MarkdownFolder] hashes its fixed, sorted file
  list by file name and bytes. Reading an unchanged folder again gives the same dataset identity,
  although accessed Source records receive fresh IDs. Its fingerprint omits the absolute folder
  path, while emitted `Source.origin` includes that path. Equal fingerprints across copied folders
  therefore do not promise equal origins; account for location separately if a computation uses it.

For example, record content equivalence and full-record dataset equivalence differ:

```python
from triplum.datatype import Source
from triplum.utils.data import RecordDataset

first = Source(origin="notes.md", text="Hello")
second = Source(origin="notes.md", text="Hello")
print(first.fingerprint == second.fingerprint)
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
