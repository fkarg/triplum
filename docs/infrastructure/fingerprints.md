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
[`FixedSize`][triplum.steps.chunking.FixedSize]. It combines the qualified class name, loaded application method definitions,
immutable class constants, explicit configuration and declared dependencies. It does not scan instance attributes.

```python
from triplum.utils.fingerprint import Fingerprinted


class Prefix(Fingerprinted):
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.calls = 0

    def fingerprint_config(self) -> dict[str, object]:
        return {"prefix": self.prefix}

    def __call__(self, text: str) -> str:
        self.calls += 1
        return self.prefix + text


first = Prefix("note: ")
first("hello")
print(first.fingerprint() == Prefix("note: ").fingerprint())
print(first.fingerprint() == Prefix("warning: ").fingerprint())
```

Output:

```text
True
False
```

The counter does not change the result, so the configuration hook omits it. A stateless
implementation returns `{}`. Adding a resource attribute does not change identity. A changed
application method or selected setting does; inherited application methods are included too.
Pure Python definitions do not need source files. The digest describes loaded code rather than
rereading source files after import. Moving the
class to another module changes its qualified name and therefore its identity.

The [computation guide](cache/computations.md#select-settings-and-dependencies) explains dependency
selection, `definition_hash`, supported class constants and the limits of automatic inference.

The cache decorator has its own automatic **function** identity, covering source, qualified name,
evaluated defaults and captured configuration at decoration. It does not gain the mixin's hooks.
See [automatic function identity](cache/computations.md#use-automatic-function-identity-where-it-fits)
for its boundaries and explicit `process_id` override.

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
