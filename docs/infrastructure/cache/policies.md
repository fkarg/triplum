# Own a cache and control pending writes

A [`Cache`][triplum.cache.Cache] owns a storage backend and one background writer. Steps borrow
that owner; several steps can share it. [`CachePolicy`][triplum.cache.CachePolicy] controls whether
new writes skip or wait when the pending-write budget is full. Configure it to trade caller
latency against retaining computed results.

## See admission and persistence separately

This complete example uses raw bytes so the admission decision is visible without a computation
or serializer. Save it as `cache_policy_example.py` and run
`uv run python cache_policy_example.py` from a checkout.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from triplum.cache import Cache, CacheKey, CachePolicy, SQLiteBackend
from triplum.utils.cache import content_key


key = CacheKey(
    bytes.fromhex(content_key("example.policy", {})),
    bytes.fromhex(content_key("example.input", {"text": "hello"})),
)

with TemporaryDirectory() as directory:
    with Cache(
        SQLiteBackend(Path(directory) / "cache.sqlite"),
        pending_bytes=512,
        policy=CachePolicy(on_full="skip"),
    ) as cache:
        # This entry cannot fit even when the queue is empty.
        print(cache.put(key, b"x" * 1024))
        print(cache.skipped_writes)

        # Override the owner's policy for this write.
        print(cache.put(key, b"hello", policy=CachePolicy(on_full="block")))
        print(cache.get(key))
        cache.flush()
```

Output:

```text
False
1
True
b'hello'
```

`put` returning `True` means the owner accepted the write. `get` on that same owner can already
read it, including while it is pending. `flush()` waits for writes accepted before the flush
call to finish persisting; leaving the context drains accepted writes and closes the backend.
Other owners see committed backend data, not this owner's pending queue.

## Choose the scope of a policy

The policy is a configuration value with two supported choices, not a callback or plugin
Protocol. Pass `CachePolicy(on_full="skip")` or `CachePolicy(on_full="block")` at the scope
that needs it:

| Scope | Configuration | Effect |
| --- | --- | --- |
| Owner | `Cache(backend, policy=...)` | Default for all writes through that owner |
| Decorated step | `@cache.cached(policy=...)` or `@cached(policy=...)` | Override for misses computed by this function |
| Configured step | `super().__init__(cache=owner, policy=...)` in a `CachedStep` subclass | Override for this step instance |
| Manual write | `cache.put(key, payload, policy=...)` | Override for this one write |

Omitting a step/write policy, or passing `None`, inherits the owner's policy. Choosing a policy
does not change computation identity or invalidate existing entries. The
[cache guide](../cache.md) and [configured-step example](computations.md) show these entry points; their
`policy` argument takes the same value used above.

- **Skip** is the default. When a write does not fit, `put` returns `False` and increments
  `cache.skipped_writes`. A decorated function or `CachedStep` still returns the computed result;
  a subsequent call may need to compute again.
- **Block** waits until sufficient capacity becomes available. An entry larger than the entire
  budget raises `ValueError` instead of waiting forever. In a cached step, this can happen after
  computation and serialization have finished, so the step call raises rather than returning
  that result.

Serialization runs in the caller before admission. Skipping a write therefore does not avoid
its computation or encoding cost. See [serialization](serialization.md) to choose a codec.

## Size the pending budget

The default budget is 64 MiB. `pending_bytes` must be positive and charges each queued or
in-flight write for its payload, both 32-byte key digests, and a 256-byte bookkeeping allowance.
The example's five-byte payload therefore needs 325 bytes of capacity.

This budget does not cap database size, process memory, or temporary serialization buffers.
It also does not evict old results. Persisted results accumulate until you
[clear their computation tables](administration.md). There is no measured performance guarantee
for caches of hundreds of GB.

## Choose and close the owner

Bare `@cached` and `CachedStep` subclasses using default cache options share the process cache. Importing or decorating does not
open it: the first cached call does. `default_cache()` obtains that shared owner explicitly.
Its SQLite path is `$XDG_CACHE_HOME/triplum/cache.sqlite` when `XDG_CACHE_HOME` is a nonempty
absolute path, otherwise `~/.cache/triplum/cache.sqlite`.

Use `close_default_cache()` after stopping or joining callers. It drains accepted writes and
releases the shared owner. Later use can reopen it during normal execution, but cannot reopen
it once interpreter shutdown begins. The exit handler is a fallback; explicit cleanup lets
writer failures reach your code. For an isolated shared-cache trial, set `XDG_CACHE_HOME` to a
temporary absolute directory before first use.

`Cache()` creates a separate owner at the default database path immediately. To choose a
database, use `Cache(SQLiteBackend(path))`, as above, with an existing parent directory.
The context manager provides explicit lifetime; without one, call `close()` in `finally`.
Decorators and `CachedStep` borrow their cache and never close it. Pass `cache=None` to these
frontends to bypass caching entirely.

Stop callers before closing: closing does not wait for computations that have borrowed the
owner but have not yet submitted their result. Such a computation can fail when it later tries
to insert. Steps may share an owner across caller threads, but concurrent misses can compute
the same result twice. Initialize caches inside worker processes. A shared default opened
before `fork` cannot be reused in the child; use a fresh process or create an explicit owner
inside each worker.

## Handle failures at the ownership boundary

`flush()` and `close()` report background writer failures. After a writer failure, later cache
operations also fail; a disk error or SQLite writer-lock timeout is not converted into a miss
or counted as a skipped admission. Computation and codec errors likewise reach the caller.
A crash can lose accepted writes that have not persisted.

Keep every computation able to run with an empty cache. Continue with
[storage backends](storage.md) for the persistence boundary or
[inspection and clearing](administration.md) for committed data.
