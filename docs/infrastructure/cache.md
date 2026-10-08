# Reuse computed results

Cache a step when reusing its result is cheaper than computing it again. A cache hit requires
both the same computation and the same immediate input content. Different pipelines can therefore
reuse an intermediate result without sharing their whole processing history.

## Add the decorator

Use `@cached` on a function with fingerprintable inputs and outputs. The decorator identifies the
computation, chooses serialization from the return annotation and opens a shared SQLite cache
when first called. No cache configuration or manual computation ID is needed.

Save this complete example as `cache_example.py` and run `uv run python cache_example.py`.
The small `Text` model declares what counts as the same data; if your application already has a
fingerprintable Pydantic value, use that type directly.

```python
from pydantic import BaseModel

from triplum.cache import cached
from triplum.utils.cache import content_key


class Text(BaseModel):
    text: str

    def fingerprint(self) -> str:
        return content_key("example.Text", {"text": self.text})


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
`Text.fingerprint()` identifies its content. [Value fingerprints](cache/fingerprints.md) explains
that separate data contract.

The default database is `$XDG_CACHE_HOME/triplum/cache.sqlite`, falling back to
`~/.cache/triplum/cache.sqlite`. Importing and decorating do not open it. Accepted writes run in
the background and remain readable immediately; normal process exit drains them. For explicit
lifetime control, use [`close_default_cache()`][triplum.cache.close_default_cache] or an owned
cache as described in [ownership and write policy](cache/policies.md).

Function identity covers source, defaults and captures. Run the example from a file so the source
is available. External helpers and model dependencies need explicit treatment; see
[computation fingerprints](cache/computations.md) when the default is insufficient.

## Specialize only the part you need

Ordinary functions remain uncached, and several cached functions share the same default cache.
Each computation has its own namespace. Use `@cache.cached` with an explicitly owned `Cache`
when choosing storage or lifetime; use `CachedStep` when an operation already needs a configured
class. Neither is required for the decorator above.

| Part | Responsibility | Default |
| --- | --- | --- |
| Decorator or `CachedStep` | Identify a call and serialize its result | Pydantic output model from the return annotation |
| `Cache` and storage backend | Look up results and persist accepted writes | SQLite, with a background writer |
| Admission policy | Decide what happens when pending writes fill the budget | Skip the new write and count it |

## Choose the next concept

Each page explains one boundary, with a small runnable example and the rules for supplying your
own implementation. You can use each extension without adopting the others.

| What you want to do | Read | Interface |
| --- | --- | --- |
| Define which input/output fields mean the same thing | [Value fingerprints](cache/fingerprints.md) | `Fingerprintable` |
| Identify an operation or write a configured cached step | [Computation fingerprints](cache/computations.md) | `cached`, `CachedStep` |
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
explain the boundary; current Source/Chunk fingerprint properties cannot be used directly as cache
values.

The former `triplum.utils.cache.Cache` file utility has been removed. Use `triplum.cache.Cache`;
`triplum.utils.cache` contains only the `canonical_json` and `content_key` identity helpers.
