# Inspect and clear committed results

Use cache administration to see which computations have stored results or to discard entries
whose computation/output contract has changed. The CLI wraps the importable
[`cache_stats`][triplum.cache.admin.cache_stats] and
[`clear_cache`][triplum.cache.admin.clear_cache] functions; inspection does not open a background
cache owner.

## Inspect and clear from Python

This complete example uses a temporary SQLite database. Save it as `cache_admin_example.py`
and run `uv run python cache_admin_example.py` from a checkout.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from triplum.cache import Cache, CacheKey, SQLiteBackend
from triplum.cache.admin import cache_stats, clear_cache
from triplum.utils.cache import content_key


computation = content_key("example.admin", {})
key = CacheKey(
    bytes.fromhex(computation),
    bytes.fromhex(content_key("example.input", {"text": "hello"})),
)

with TemporaryDirectory() as directory:
    path = Path(directory) / "cache.sqlite"
    with Cache(SQLiteBackend(path)) as cache:
        assert cache.put(key, b"hello")
    # Closing the owner commits accepted writes and stops its writer.

    quick = cache_stats(path)
    print(quick.exists, len(quick.computations))
    print(quick.computations[0].entries)

    detailed = cache_stats(path, computation=computation, details=True)
    row = detailed.computations[0]
    print(row.entries, row.payload_bytes)
    print(clear_cache(path, computation=computation))
    print(len(cache_stats(path).computations))
```

Output:

```text
True 1
None
1 5
1
0
```

The clear result counts dropped **computation tables**, not entries. Calling `clear_cache(path)`
without `computation` selects all recognized computation tables. Omitting `path` from either
function uses the shared default path described in [ownership and policies](policies.md).

## Use the CLI

The following shell example creates and operates on its own temporary database. Run it from a
checkout; it does not touch the shared user cache. The all-zero digest is an explicit example
computation identity, and the commands pass its complete 64 hexadecimal characters.

```sh
cache_demo_dir=$(mktemp -d)
trap 'rm -rf "$cache_demo_dir"' EXIT
uv run python - "$cache_demo_dir/cache.sqlite" <<'PYTHON'
import sys

from triplum.cache import Cache, CacheKey, SQLiteBackend

with Cache(SQLiteBackend(sys.argv[1])) as cache:
    assert cache.put(CacheKey(bytes(32), bytes.fromhex("11" * 32)), b"hello")
PYTHON

uv run triplum cache stats --path "$cache_demo_dir/cache.sqlite"
uv run triplum cache stats --path "$cache_demo_dir/cache.sqlite" --details --json
uv run triplum cache clear --path "$cache_demo_dir/cache.sqlite" \
  --computation 0000000000000000000000000000000000000000000000000000000000000000 \
  --no-input --json
uv run triplum cache clear --path "$cache_demo_dir/cache.sqlite" --no-input
```

Both commands accept `--path` and `--computation`. Leave off `--path` to administer the shared
user cache; leave off `--computation` to select all recognized computation tables. A selector
must be an exact full SHA-256 fingerprint, as shown by stats. Uppercase hexadecimal is accepted,
but abbreviated digests are not. This identity is the `process_id` used by a decorator or the
computation's automatic fingerprint, represented as bytes in `CacheKey.process`.

Commands never prompt; `--no-input` is accepted for scripts. `--json` emits structured output
to stdout, and errors go to stderr. `clear --json` returns `cleared_computations`.
A missing database is reported without creating either its file or its parent directory:
stats reports `exists=False`, and clear returns zero. An absent computation selects no tables.

## Read statistics correctly

SQLite creates `cache_<full computation fingerprint>` on a computation's first committed write.
Each table stores input digests and encoded payloads. See [storage](storage.md) for that layout.

| Observation | Meaning |
| --- | --- |
| Computations | Recognized committed computation tables, filtered by the optional selector |
| `database_bytes` | Observed size of the main database file |
| `wal_bytes` | Observed size of the SQLite write-ahead log, or zero when absent |
| `reusable_bytes` | Database free pages available for reuse |
| `entries` | Exact committed row count when `details=True`; otherwise `None` |
| `payload_bytes` | Sum of encoded value lengths when `details=True`; otherwise `None` |

Default stats lists tables and database sizes without scanning entries. `--details` scans the
selected tables for counts and payload totals and can be expensive for large caches. Payload
bytes exclude keys, table/index overhead and unused pages. Database/WAL/reusable sizes describe
the whole file even when a single computation is selected.

Detailed counts share one database snapshot. Filesystem sizes are separate observations and
need not describe the same instant. Stats cannot report in-memory pending writes, hit counts,
or owners' runtime `skipped_writes` counters. Use the owner directly for its skip count.

Although inspection opens a read-only SQLite connection, SQLite may need to create WAL/SHM
sidecar files. If they are absent, inspection can still require a writable containing directory.
The reported sizes do not include the SHM file.

## Clear without expecting file shrinkage

Clearing drops selected recognized computation tables and preserves unrelated tables, including
older layouts not recognized by this interface. It does not unlink the database or run
`VACUUM`. Freed pages remain available for reuse; the file need not shrink.

Stop writers before clearing if the cache must remain empty. Pending writes and subsequent
computations can recreate a dropped table immediately, including writes held by another owner
or process. Closing an owner drains its accepted writes, so close it **before** clear.
See [lifetime and failures](policies.md) for shutdown behavior.

Return to the [cache guide](../cache.md) to use the frontends, or read
[serialization](serialization.md) before changing an output format and clearing old results.
