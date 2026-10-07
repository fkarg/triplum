# Cache

Cache selected computations so later calls can reuse their results. Several steps can borrow
one [`Cache`][triplum.cache.Cache]; ordinary functions remain uncached. Use `@cached` for the
shared default or `@cache.cached` to choose the owner.

## Cache a function

Cached inputs and outputs implement `fingerprint()`, returning a SHA-256 hex digest of their
semantic content. The default output serializer accepts Pydantic models. This example deliberately
selects the text field, rather than hashing every attribute a model might acquire later.

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

        print(lowercase(Text(text="Hello")).text)
        print(lowercase(Text(text="Hello")).text)
```

Output:

```text
Computing
hello
hello
```

The second call can read the accepted result even before the background writer persists it.
Closing the context drains accepted writes and closes the backend. Use a persistent local file
path instead of a temporary directory to reuse results between runs; create its parent directory
first. The `-> Text` return annotation selects the output model; the function source identifies
the computation. Run this example from a Python file so its source is available.

For the shared default, the decorator needs no arguments:

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

This continues the `Text` definition above. The first call opens
`$XDG_CACHE_HOME/triplum/cache.sqlite`, falling back to `~/.cache/triplum/cache.sqlite`.
Importing or decorating does not open the database. Stop or join all callers before
`close_default_cache()`, which drains and releases the shared owner; later calls reopen it during
normal execution. Once interpreter shutdown begins, reopening is refused. An exit handler is a
fallback, not a replacement for
explicit cleanup when writer errors need to reach the caller. `Cache()` opens the same default
database with a separate owner and a 64 MiB pending-write budget. Initialize caches inside
worker processes; an inherited shared default after `fork` is rejected.

## What identifies a computation?

A lookup matches **all three** parts: computation fingerprint, immediate input fingerprint and
serialization format. The computation fingerprint must include its kind/revision and effective
configuration, including relevant helper or model revisions. The automatic identity covers
function source, module/qualified name, evaluated defaults and captured configuration. This identity
freezes at decoration, so later source-file edits cannot change the key of the already-loaded
function. Captured configuration must remain fixed after decoration. The codec and database remain
lazy. Automatic identity does **not** track globals, helper
functions, model revisions, files or environment variables.

For those dependencies, supply an explicit digest covering everything that affects the result:

```python
@cache.cached(process_id=content_key("lowercase-v1", {}), output_type=Text)
def lowercase(value: Text) -> Text:
    return Text(text=value.text.lower())
```

This decorator form belongs inside the owned-cache context above. When you provide `process_id`,
you own revision changes, including edits to the function body. Source-unavailable functions and
callable objects require explicit identity. Automatic identity is a convenience for self-contained
functions, not dependency discovery.

Equivalent configured steps can share entries across pipelines. Pipeline position, object identity,
cache location and queue policy do not belong in the fingerprint. Neither does upstream processing
history when the immediate input is identical. Separate cache instances are useful for independent
storage or resource budgets, but are not required to separate different computations.

Choose value identity fields explicitly. Exclude bookkeeping timestamps; retain dates that affect
the answer. Computations must not depend on excluded fields, mutate their input, or read hidden
changing state. Both inputs and outputs must be fingerprintable; custom output types also need a
[`Codec`][triplum.cache.Codec]. Source and Chunk have not yet migrated to this method-based contract.

## Serialization and other entry points

The concrete return annotation, or an explicit `output_type=Text`, selects [`PydanticCodec`][triplum.cache.PydanticCodec] by default. It serializes
JSON bytes and validates them back into the model, checking on each write that the semantic
fingerprint survives the round-trip. This adds a decode to the write path; reads only decode.
The default format namespace includes the model's qualified name and its validation/serialization
schemas, so schema documentation edits can conservatively cause misses. Custom serializers or validators whose behavior changes without a schema change need an
explicit versioned `format_id`. Supply `codec=PydanticCodec(Text, format_id="text-json-v2")`, or a
custom codec for another representation. Serialization performance has not been benchmarked.

For configured classes, [`CachedStep`][triplum.cache.CachedStep] owns `__call__`; implement
`compute(item)` and `fingerprint()` for the computation. Put the mixin before domain Protocol
bases. The mixin defaults to the shared cache and infers the model from `compute`'s return
annotation, while its computation fingerprint remains an explicit abstract method. It borrows its
cache and never closes it. The decorator accepts a one-input function or an already-bound callable
(with explicit identity); it does not proxy additional object attributes.

Pass `cache=None` to either frontend to bypass fingerprints, serialization and lookup. Manual
`Cache.get(CacheKey(...))` and `Cache.put(key, payload)` operate on bytes; the caller owns the
codec and identity checks at that boundary. See the generated API reference for their signatures.

## Background writes and ownership

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

## Cache versus store

The cache holds recomputable results. The [store](store.md) holds records selected for persistence,
keyed by record ID. Reusing an intermediate payload must not copy another source's provenance or
record references. Cache whole records only when their inputs account for those references.

The older [`triplum.utils.cache.Cache`][triplum.utils.cache.Cache] remains an independent,
synchronous file-per-key utility with byte and JSON methods. Existing callers are unchanged;
new optional step caching uses `triplum.cache`.
