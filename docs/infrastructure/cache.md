# Cache

The **cache** remembers the result of a computation on disk, so that the next run with the same
inputs can read the result instead of computing it again. It is a key/value store: you build a
key from everything that determines the result, and store bytes or JSON under it.

What exists today is only this building block: [`Cache`][triplum.utils.cache.Cache] and the key
function [`content_key`][triplum.utils.cache.content_key]. Steps are not cached automatically
yet; code that wants caching calls the cache itself, as below.

## Example

```python
from pathlib import Path

from triplum.utils.cache import Cache, content_key

cache = Cache(Path(".cache/triplum"))
key = content_key("word-count", {"text": "Returns are accepted within 30 days."})

result = cache.get_json(key)
if result is None:
    result = {"words": len("Returns are accepted within 30 days.".split())}
    cache.put_json(key, result)
print(result)
print(key[:16])
print(sorted(str(p) for p in Path(".cache").rglob("*") if p.is_file()))
```

Output (the same on the first and on every later run):

```text
{'words': 6}
428a53e347797f4c
['.cache/triplum/42/428a53e347797f4c18e35146dd70cfe6225a5458c209305ae8903bfb71a626e1']
```

1. `Cache(Path(".cache/triplum"))` chooses the cache directory. A relative path is relative to
   the current working directory. Nothing is created yet.
2. `content_key("word-count", {...})` builds the key: a SHA-256 digest of a *kind* string and a
   JSON-serialisable payload. The kind separates different computations that happen to get the
   same payload.
3. `get_json(key)` returns the stored value, or `None` on a miss. On the first run it misses, so
   the result is computed and stored with `put_json`. On later runs it hits.
4. Each entry is one file, named after its key, in a subfolder named after the key's first two
   characters. Directories are created on the first write.

## Building keys

The key must change whenever the result could change. Put everything that affects the result
into the payload: the input (or its [record or dataset fingerprint](fingerprints.md)), and the
configured step that computes it (its [object fingerprint](fingerprints.md#object-fingerprints)).
Anything left out means a stale result is returned when that thing changes.

- **Payloads are canonical JSON.** [`canonical_json`][triplum.utils.cache.canonical_json] sorts
  dictionary keys and removes whitespace, so `{"a": 1, "b": 2}` and `{"b": 2, "a": 1}` give the
  same key. List order matters: `[1, 2]` and `[2, 1]` give different keys.
- **Only JSON values are accepted**: dicts, lists, tuples (treated as lists), strings, numbers,
  booleans and `None`. Anything else, such as a `Path`, raises `TypeError`; convert it with
  `str(path)` first.
- `1` and `1.0` are different JSON and therefore different keys.
- Use keys made by `content_key`. The cache uses the key as a file name without checking it.

## Managing the cache directory

- **Where it lives** is whatever directory you pass; the cache has no default location.
- **Clearing it** means deleting the directory, for example `rm -rf .cache/triplum`. The next run
  recomputes everything and recreates the directory. Deleting a single entry means deleting its
  file.
- **It never shrinks by itself.** There is no expiry, size limit or eviction.
- **Concurrent writers are safe.** An entry is written to a temporary file and then renamed into
  place, so a reader sees either the complete entry or none. A process killed mid-write can leave
  a `*.tmp` file behind; it is never read and can be deleted.

## Cache versus store

The cache and the [store](store.md) are deliberately separate. The cache holds results you could
recompute; deleting it costs time, not data. The store holds the records you chose to keep, keyed
by their `id`. Do not use one as the other.

## Reference

- [`Cache`][triplum.utils.cache.Cache]
- [`content_key`][triplum.utils.cache.content_key] and
  [`canonical_json`][triplum.utils.cache.canonical_json]
