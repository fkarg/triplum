# Reuse computed results

Cache a step when reusing its result is cheaper than computing it again. A cache hit requires
both the same computation and the same effective argument values. Different pipelines can therefore
reuse an intermediate result without sharing their whole processing history.

## Add the decorator

Use `@cached` on a function returning a fingerprintable output. Arguments may be supported
plain values or fingerprintable objects. The decorator identifies the computation, chooses
serialization from the return annotation and opens a shared SQLite cache
when first called. No cache configuration or manual computation ID is needed.

Save this complete example as `cache_example.py` and run `uv run python cache_example.py`.
`FingerprintedDataModel` supplies data fingerprinting and Pydantic serialization; the decorator
supplies computation identity and caching.

```python
from triplum.cache import cached
from triplum.datatype import FingerprintedDataModel


class Text(FingerprintedDataModel):
    text: str


@cached
def lowercase(value: Text) -> Text:
    print("Computing")
    return Text(text=value.text.lower())


for text in ("Hello", "Hello", "WORLD", "Hello"):
    print(lowercase(Text(text=text)).text)
```

With an empty cache:

```text
Computing
hello
hello
Computing
world
hello
```

The second call reuses the result. Changing the input to `WORLD` computes another result;
returning to `Hello` reuses its earlier result. Results persist between runs, so subsequent runs
may print no `Computing` lines. The `-> Text` annotation selects Pydantic serialization, while
the inherited `Text.fingerprint()` identifies its field values.
[Value fingerprints](cache/fingerprints.md) explains that separate data contract.

The cache opens on the first call and is shared by decorated functions. For its location, explicit
cleanup, or write policy, see [ownership and write policy](cache/policies.md).

Function identity rereads loaded code, defaults, captures, supported globals and statically resolved
application helpers before each lookup. Keep
[inputs and context stable during each call](cache/computations.md#keep-inputs-and-context-stable-during-a-call).
External resources have their own identity boundaries; see
[computation fingerprints](cache/computations.md).

## Pass text and context directly

The decorator accepts the function's usual positional and keyword arguments. You do not need to
wrap plain strings or containers in a data model. This complete example uses an explicitly owned
temporary cache so each run starts empty:

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from triplum.cache import Cache, SQLiteBackend
from triplum.datatype import FingerprintedDataModel


class Rendered(FingerprintedDataModel):
    text: str


with TemporaryDirectory() as directory:
    with Cache(SQLiteBackend(Path(directory) / "cache.sqlite")) as cache:

        @cache.cached
        def render(text: str, context: str, *, separator: str = "\n") -> Rendered:
            print("Computing")
            return Rendered(text=context + separator + text)

        first = render("Evidence", "Collection")
        second = render(context="Collection", text="Evidence", separator="\n")
        print(first.text == second.text)
```

This prints `Computing` once, then `True`. Calls bind to parameter names and include defaults:
positional versus keyword spelling, omitted versus explicit defaults, and the order of declared
named keywords select the same input. Swapping text and context selects a different input.

Supported argument values are finite primitives, bytes, UUIDs, paths, lists, tuples, string-keyed
mappings and objects implementing `fingerprint()`. See [value fingerprints](cache/fingerprints.md)
for their data semantics and record projection limits. Unsupported values and invalid calls fail
before lookup. Ordered `*args` retain order and multiplicity; residual `**kwargs` retain keyword
order because the function can observe it. Ordinary dictionaries used as values remain
order-independent. The function's parameter and return types are preserved.

## Specialize only the part you need

Ordinary functions remain uncached, and several cached functions share the same default cache.
Each computation has its own namespace. Use `@cache.cached` with an explicitly owned `Cache`
when choosing storage or lifetime. A [function factory](cache/computations.md) can capture settings;
`CachedStep` is available for operations already implemented as classes.

## Choose the next concept

Each page explains one boundary, with a small runnable example and the rules for supplying your
own implementation. You can use each extension without adopting the others.

| What you want to do | Read | Interface |
| --- | --- | --- |
| Define which input/output fields mean the same thing | [Value fingerprints](cache/fingerprints.md) | `FingerprintedDataModel`, `Fingerprintable` |
| Identify an operation or write a configured cached step | [Computation fingerprints](cache/computations.md) | `cached`, `CachedStep` |
| Follow application methods used at runtime | [Runtime dependency tracing](cache/tracing.md) | `dependency_mode="traced"` |
| Use Pydantic output or supply another encoding | [Serialization](cache/serialization.md) | `Codec`, `PydanticCodec` |
| Supply storage or use keys/bytes directly | [Storage backends](cache/storage.md) | `CacheBackend`, `SQLiteBackend`, `CacheKey` |
| Choose skipping/blocking and manage lifetime | [Ownership and write policy](cache/policies.md) | `Cache`, `CachePolicy`, shared-default helpers |
| Inspect or clear persisted results | [Administration](cache/administration.md) | CLI, `cache_stats`, `clear_cache` |

For a two-step composition demonstrating reuse across upstream computations and after reopening,
run `uv run python examples/cached_pipeline.py`. Ordinary functions can sit between cached steps;
there is no requirement to cache every operation or use a pipeline executor.

## Cache versus record storage

The cache holds recomputable results. A [record store](store.md) holds selected records and their
references. Equal text may reuse a vector computation without merging source identity or copying
another source's provenance. [Value fingerprints](cache/fingerprints.md#share-content-without-sharing-provenance)
explain the boundary. The [record fingerprint guide](fingerprints.md#existing-record-fingerprints)
describes the fields Source/Chunk fingerprints and IDs cover. Include every field the computation
uses in its effective input identity.
