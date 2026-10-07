# Replace cache storage

A storage backend maps cache keys to immutable bytes. It does not choose fingerprints, serialize
models or decide which writes to skip. [`Cache`][triplum.cache.Cache] handles admission and pending
writes; [`CacheBackend`][triplum.cache.CacheBackend] is the boundary you implement to change storage.

## Implement a small backend

This disposable dictionary backend illustrates the three methods. It keeps results only for the
lifetime of this owner, with no eviction or persistence. Save the complete example as
`cache_storage.py` and run `uv run python cache_storage.py` from a checkout:

```python
from collections.abc import Sequence
from threading import Lock

from triplum.cache import Cache, CacheBackend, CacheKey
from triplum.utils.cache import content_key


class DictionaryBackend(CacheBackend):
    def __init__(self) -> None:
        self._values: dict[CacheKey, bytes] = {}
        self._lock = Lock()

    def get(self, key: CacheKey, /) -> bytes | None:
        with self._lock:
            return self._values.get(key)

    def put_many(self, entries: Sequence[tuple[CacheKey, bytes]], /) -> None:
        with self._lock:
            self._values.update(entries)

    def close(self) -> None:
        self._values.clear()


key = CacheKey(
    process=bytes.fromhex(content_key("example.storage", {})),
    input=bytes.fromhex(content_key("example.Text", {"text": "Hello"})),
)
backend = DictionaryBackend()
with Cache(backend) as cache:
    print("Accepted:", cache.put(key, b"hello"))
    print("Owner reads:", cache.get(key))
    cache.flush()
    print("Backend reads after flush:", backend.get(key))
```

Output:

```text
Accepted: True
Owner reads: b'hello'
Backend reads after flush: b'hello'
```

`put` accepts bytes into the owner's pending queue. The immediate `get` can read that pending
value even if storage has not received it. The writer may also finish before that read; its timing
is deliberately unspecified. `flush()` waits for all writes accepted before the call, so the
subsequent backend read observes the completed write. Here completion means an in-memory update,
not disk durability. Exiting the context drains accepted writes and calls `backend.close()`.

This example uses the manual byte interface, so the caller constructs the key and payload. A
decorator or `CachedStep` works with the same `Cache(backend)` and supplies those for you; see the
[cache introduction](../cache.md).

## Responsibilities at the boundary

[`CacheKey`][triplum.cache.CacheKey] has two 32-byte digests: `process` identifies the computation,
and `input` identifies its immediate input. Keep both in the backend key. See
[computation identities](computations.md) and [value fingerprints](fingerprints.md).

| Method | Required behavior |
| --- | --- |
| `get(key)` | Return the stored bytes, or `None` for a miss. Empty bytes are a value. |
| `put_many(entries)` | Store the key/value pairs. Once it returns successfully, subsequent reads must see those writes. |
| `close()` | Release owned resources after all other backend calls have finished. |

Each value must become visible atomically; readers must never receive half a payload. The
contract allows a failed batch to have stored some entries. The dictionary's lock makes its
whole update atomic to readers, which is stronger than required.

Support concurrent reads and one background writer **per cache owner**. This example protects
reads and writes with one lock. `Cache.close()` waits for its writer and readers before closing
the backend, so this backend does not need a lock in `close`. Lend the cache to steps, and let
that owner close its backend. Each owner closes the backend supplied to it. To share a SQLite
database between independent owners, give each owner a separate `SQLiteBackend` instance pointing
to the same file, rather than sharing one backend instance.

Raise storage errors rather than returning a miss. Read errors reach the caller directly.
A background write failure is logged and becomes a sticky owner error, surfaced by subsequent
operations, `flush()` or `close()`; batches are not retried. Cache admission skipping is a separate
policy, not a way to hide storage failures. Stop caller threads before closing their owner.

The default [`SQLiteBackend`][triplum.cache.SQLiteBackend] stores each computation in its own
table. The dictionary example does not implement SQLite administration: `cache stats` and
`cache clear` inspect SQLite files, not arbitrary backends.

Continue with [serialization](serialization.md) to choose the bytes stored for each result.
