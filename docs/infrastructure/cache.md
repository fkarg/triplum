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
        return content_key("text-v1", {"text": self.text})


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
it drains accepted writes and releases the shared owner. See [lifetime details](#control-background-writes-and-lifetime)
for errors, threads and worker processes.

## Decide when a result can be reused

The key is `(computation fingerprint, input fingerprint)`. Each is a full SHA-256 digest.
`process_id` is the decorator argument for an explicit computation fingerprint; `CacheKey.process`
holds its bytes. The same digest appears in `cache stats` and is accepted by `--computation`.
The encoded output is the value. Its own semantic fingerprint can become the input identity of
another cached step: that is how equal intermediate results reuse downstream work even when
different upstream computations produced them. See the runnable two-step example:

```sh
uv run python examples/cached_pipeline.py
```

It demonstrates equivalent inputs, different upstream normalizers and reuse after reopening the
database. A step does not need to cache every operation inside its computation.

| Change | Expected effect | Your responsibility |
| --- | --- | --- |
| Input text or other consumed data | Different input key | Include every consumed field in the value's `fingerprint()` |
| Bookkeeping time, such as when input was observed | Same key | Exclude it, and ensure the computation does not use it |
| Function source, defaults or captured configuration | Different automatic computation key | Keep captured configuration fixed after decoration |
| External helper, model weights, file, environment or library dependency | Not detected automatically | Supply an explicit `process_id` covering the dependency and revision |
| Output model, serializer or validator changes | No separate format key | Revise the computation identity or clear its table when old results are no longer valid |
| Cache location, queue policy or pipeline position | Same semantic key | Keep these out of fingerprints |

Choose semantic fields deliberately; there is no automatic timestamp filter. Dates that affect
the answer are input data. Computations must not mutate their inputs or depend on excluded fields.
[Fingerprints](fingerprints.md) explains the differences between cache values, configured objects
and existing record fingerprints. `Source` and `Chunk` have not migrated to the cache's
method-based contract and cannot be passed directly to these cached functions.

### Take responsibility for external dependencies

Automatic function identity hashes source, module/qualified name, evaluated defaults and captured
configuration at decoration time. Defaults and captures may be plain scalar values, lists, tuples,
string-keyed dictionaries or objects with `fingerprint()`. Unlike the configured-object utility,
it does not directly support `Path` or arbitrary Pydantic model configuration. Lambdas need an
explicit `process_id`. It does not discover the dependency graph. Inside an owned cache
context, an explicit identity looks like this:

```python
@cache.cached(process_id=content_key("lowercase-v1", {}))
def lowercase(value: Text) -> Text:
    return Text(text=value.text.lower())
```

With `process_id`, you own all revision changes, including edits to the function body. Include
relevant configuration in the dictionary and change the revision when implementation or output
contracts change. Source-unavailable functions and callable objects also need explicit identity.

## Cache a configured class

Use [`CachedStep`][triplum.cache.CachedStep] when configuration belongs on an instance. It supplies
`__call__`; you supply `compute` and the computation's `fingerprint`. This example continues the
`Text` definition above and uses the shared default:

```python
from triplum.cache import CachedStep, close_default_cache


class Append(CachedStep[Text, Text]):
    def __init__(self, suffix: str) -> None:
        super().__init__()
        self.suffix = suffix

    def fingerprint(self) -> str:
        return content_key("append-v1", {"suffix": self.suffix})

    def compute(self, value: Text) -> Text:
        return Text(text=value.text + self.suffix)


try:
    first, equivalent, different = Append("!"), Append("!"), Append("?")
    value = Text(text="Hello")
    print(first(value).text, equivalent(value).text, different(value).text)
finally:
    close_default_cache()
```

Output is `Hello! Hello! Hello?`. The first two instances have equal computation fingerprints
and can reuse one entry; the third has different configuration. The mixin borrows its cache and
never closes it. To choose an owner, pass `cache=owner` to `super().__init__`; put `CachedStep`
before any domain Protocol bases. Exclude the cache, codec and policy from the step fingerprint.
Do not reuse `Fingerprinted.fingerprint` unchanged here: it visits every instance attribute,
including the mixin's lock and cache resources.

## Choose serialization or bypass caching

The concrete return annotation, or an explicit `output_type=Text`, selects [`PydanticCodec`][triplum.cache.PydanticCodec] by default. It serializes
JSON bytes and validates them back into the model, checking on each write that the semantic
fingerprint survives the round-trip. This adds a decode to the write path; reads only decode.
Returned values must have the exact configured model type; a subclass is rejected.
Encoding is not part of the lookup key. When output models, validators or serializers become
incompatible, revise the computation identity or clear that computation's entries. There are no
codec format namespaces or cache-row migrations. Automatic function identity does not detect
external output-contract changes. Supply a custom codec for another representation; serialization
performance has not been benchmarked.

Pass `cache=None` to either frontend to bypass fingerprints, serialization and lookup. Manual
`Cache.get(CacheKey(...))` and `Cache.put(key, payload)` operate on bytes; the caller owns the
codec and identity checks at that boundary. See the generated API reference for their signatures.

## Control background writes and lifetime

An owned `Cache()` uses the default database with a separate background writer and a 64 MiB
pending-write budget. Use its context manager, as in the first example, to drain and close it.
The shared default can reopen after `close_default_cache()` during normal execution, but not once
interpreter shutdown begins. Its exit handler is only a fallback: explicit cleanup lets writer
errors reach the caller. Stop or join callers before closing either kind of owner. Initialize
caches inside worker processes; an inherited shared default after `fork` is rejected.

Serialization happens in the caller; persistence happens on one background writer. `pending_bytes`
counts queued and in-flight key/payload bytes plus a bookkeeping allowance, not total process
memory or temporary serialization buffers.

- The default full-queue policy skips the new write, returns the computed result, and increments
  `cache.skipped_writes`.
- `CachePolicy(on_full="block")` waits for capacity. Set it on the cache or override it on a
  decorator, mixin or manual `put`. An entry larger than the entire budget raises `ValueError`
  under this policy, including after a cached computation has already finished.
- `put` returning `True` means accepted, not durable. `flush()` waits for previously accepted
  writes; `close()` drains and closes. Both report background writer failure. Subsequent
  operations also fail after a writer failure; disk errors are not treated as cache misses.
  A SQLite writer lock timeout is also a sticky storage error, not a skipped queue admission.

Steps may share a cache across caller threads. SQLite uses separate reader/writer connections;
multiple cache owners can share the database file, but only their own pending writes are immediately
visible. Concurrent misses may compute twice. A crash can lose pending writes. There is no eviction,
size cap for the database, or measured performance guarantee at hundreds of GB yet.

## Inspect and clear

SQLite stores each computation in `cache_<full computation fingerprint>`, with the input digest
as its primary key and the encoded result as its value. Tables are created on the first committed
write. Different computations still share the database's writer; separate tables make no speed
claim.

```sh
uv run triplum cache stats
uv run triplum cache stats --details --json
uv run triplum cache clear
```

Both commands accept `--path /path/to/cache.sqlite` and `--computation` followed by an exact,
full 64-character computation fingerprint. Without a computation selector, they cover all
recognized computation tables. Missing database paths are reported without creating a database
or its directory. Commands never prompt; `--no-input` is accepted for scripted callers.

Default stats lists computation identities, database/WAL file bytes and reusable database bytes
without scanning entries. `--details` scans the selected tables for exact committed entry counts
and payload bytes; this can be expensive for a large cache. Counts share a database snapshot;
file sizes are separate observations. Pending writes, hits and runtime skip counts are not
available. Read-only inspection can still require SQLite WAL/SHM sidecars and a writable directory
if those files are absent.

`clear` drops selected computation tables, preserving unrelated tables. It does not run `VACUUM`
or shrink the database file; freed pages remain reusable. Stop writers first for a lasting empty
cache: pending or later writes can recreate the tables immediately. The importable equivalents
are `cache_stats(...)` and `clear_cache(...)` in `triplum.cache.admin`.

## Cache versus store

The cache holds recomputable results. The [store](store.md) holds records selected for persistence,
keyed by record ID. Reusing an intermediate payload must not copy another source's provenance or
record references. Cache whole records only when their inputs account for those references.

The former `triplum.utils.cache.Cache` file utility has been removed. Use `triplum.cache.Cache`;
`triplum.utils.cache` now contains only the `canonical_json` and `content_key` identity helpers.
