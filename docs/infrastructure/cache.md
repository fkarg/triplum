# Reuse computed results

Cache a step when reusing its result is cheaper than computing it again. A cache hit requires
both the same computation and the same immediate input content. Different pipelines can therefore
reuse an intermediate result without sharing their whole processing history.

Use [`triplum.cache`][triplum.cache] for this interface. Its three independent parts are:

| Part | Responsibility | Default |
| --- | --- | --- |
| Decorator or `CachedStep` | Identify a call and serialize its result | Pydantic output model from the return annotation |
| `Cache` and storage backend | Look up results and persist accepted writes | SQLite, with a background writer |
| Admission policy | Decide what happens when pending writes fill the budget | Skip the new write and count it |

Ordinary functions remain uncached. Several cached steps can share one cache; each computation
has its own namespace. Record [stores](store.md) retain selected records and provenance instead.
The `content_key` helper used below lives in `utils.cache`, but using it does not open a cache.

## See a miss, a hit, and a changed input

Cached inputs and outputs implement `fingerprint()`, returning a SHA-256 hex digest of their
semantic content. The default output serializer accepts Pydantic models. This example deliberately
selects the text field, rather than hashing every attribute a model might acquire later.

Save the complete example as `cache_example.py` and run `uv run python cache_example.py` from a
checkout. Automatic computation identity needs the function's source, so use a file rather than
pasting the function into a REPL. The temporary database gives the same demonstration on every run.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import BaseModel

from triplum.cache import Cache, SQLiteBackend
from triplum.utils.cache import content_key


class Text(BaseModel):
    text: str

    def fingerprint(self) -> str:
        return content_key("example.Text", {"text": self.text})


with TemporaryDirectory() as directory:
    with Cache(SQLiteBackend(Path(directory) / "cache.sqlite")) as cache:

        @cache.cached
        def lowercase(value: Text) -> Text:
            print("Computing")
            return Text(text=value.text.lower())

        for text in ("Hello", "Hello", "WORLD", "Hello"):
            print(lowercase(Text(text=text)).text)
```

Output:

```text
Computing
hello
hello
Computing
world
hello
```

The second call is a hit. Changing the input to `WORLD` computes another result; returning to
`Hello` reuses its earlier result. The cache can read an accepted result even before the background
writer persists it.
Closing the context drains accepted writes and closes the backend. Use a persistent local file
path instead of a temporary directory to reuse results between runs; create its parent directory
first. The `-> Text` return annotation selects the output model; the function source identifies
the computation. Run this example from a Python file so its source is available.

## Use the shared default

For normal use, the decorator needs no arguments. Keep the `Text` definition from above and
replace the temporary-cache block with. This uses the persistent database at
`$XDG_CACHE_HOME/triplum/cache.sqlite` (or `~/.cache/triplum/cache.sqlite`); set `XDG_CACHE_HOME`
to a temporary directory if you want an isolated trial:

```python
from triplum.cache import cached, close_default_cache


@cached
def lowercase(value: Text) -> Text:
    return Text(text=value.text.lower())


try:
    print(lowercase(Text(text="Hello")).text)
finally:
    close_default_cache()
```

`@cached` uses the shared cache; it does not create a separate cache for each function. The first
call opens
`$XDG_CACHE_HOME/triplum/cache.sqlite`, falling back to `~/.cache/triplum/cache.sqlite`.
Importing or decorating does not open the database. Stop callers before `close_default_cache()`;
it drains accepted writes and releases the shared owner. See [ownership and write policy](cache/policies.md)
for errors, threads and worker processes.

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
