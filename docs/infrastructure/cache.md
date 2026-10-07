# Cache

Cache selected computations so later calls can reuse their results. Several steps can borrow
one explicitly owned [`Cache`][triplum.cache.Cache]; ordinary functions remain uncached.

## Cache a function

Cached inputs and outputs implement `fingerprint()`, returning a SHA-256 hex digest of their
semantic content. The default output serializer accepts Pydantic models. This example deliberately
selects the text field, rather than hashing every attribute a model might acquire later.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import BaseModel

from triplum.cache import Cache, SQLiteBackend, cached
from triplum.utils.cache import content_key


class Text(BaseModel):
    text: str

    def fingerprint(self) -> str:
        return content_key("text-v1", {"text": self.text})


with TemporaryDirectory() as directory:
    with Cache(SQLiteBackend(Path(directory) / "cache.sqlite"), pending_bytes=1_000_000) as cache:

        @cached(
            cache=cache,
            process_id=content_key("lowercase-v1", {}),
            output_type=Text,
        )
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
first.

## What identifies a computation?

A lookup matches **all three** parts: computation fingerprint, immediate input fingerprint and
serialization format. The computation fingerprint must include its kind/revision and effective
configuration, including relevant helper or model revisions. Changing a function body does not
automatically change the explicit `process_id` in this example: update its revision yourself.

Equivalent configured steps can share entries across pipelines. Pipeline position, object identity,
cache location and queue policy do not belong in the fingerprint. Neither does upstream processing
history when the immediate input is identical. Separate cache instances are useful for independent
storage or resource budgets, but are not required to separate different computations.

Choose value identity fields explicitly. Exclude bookkeeping timestamps; retain dates that affect
the answer. Computations must not depend on excluded fields, mutate their input, or read hidden
changing state. Both inputs and outputs must be fingerprintable; custom output types also need a
[`Codec`][triplum.cache.Codec]. Source and Chunk have not yet migrated to this method-based contract.

## Serialization and other entry points

`output_type=Text` selects [`PydanticCodec`][triplum.cache.PydanticCodec] by default. It serializes
JSON bytes and validates them back into the model, checking on each write that the semantic
fingerprint survives the round-trip. This adds a decode to the write path; reads only decode.
The default format namespace includes the model's qualified name and its validation/serialization
schemas. Custom serializers or validators whose behavior changes without a schema change need an
explicit versioned `format_id`. Supply `codec=PydanticCodec(Text, format_id="text-json-v2")`, or a
custom codec for another representation. Serialization performance has not been benchmarked.

For configured classes, [`CachedStep`][triplum.cache.CachedStep] owns `__call__`; implement
`compute(item)` and `fingerprint()` for the computation. Put the mixin before domain Protocol
bases. It borrows its cache and never closes it. The decorator accepts a one-input function or an
already-bound callable; it does not proxy additional object attributes.

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
