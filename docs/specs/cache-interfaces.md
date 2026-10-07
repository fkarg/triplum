# Optional caching interfaces — first implementation for owner review

The owner wants interchangeable storage, policies configurable per run/step, manual access,
decorators and a CachedStep mixin. Cached calls require fingerprintable input AND output values;
our intermediate value types should support that contract. Plain uncached user steps need not.
Skip-and-count is the default when pending writes cannot be admitted; blocking is configurable.
The cache target is tens to hundreds of GB with room to grow. The owner authorized a first runtime
implementation in `triplum.cache`, including default Pydantic serialization. Benchmark policy and
large-scale performance comparisons remain later work. The explicit API and parameter-light defaults below are implemented for owner review.

## Recommended shape

One explicitly owned Cache coordinates policy and background persistence over a CacheBackend.
A decorator and a template-method CachedStep share the same lookup/compute/encode/submit path.
Manual get/put uses the same pending visibility and policy. Steps never own database connections.
Keep codecs separate from semantic fingerprints so storage representation does not redefine data.

## Fingerprintable values: settled constraint, two implementation choices

`Fingerprintable.fingerprint()` is a structural contract returning the current convention: a
64-character SHA-256 hexadecimal digest. Cache backends use the binary digest for key storage.
That conversion cost belongs in the benchmark; this draft does not change all existing fingerprint
return types or settle UUID allocation. Existing data-record fingerprint properties must become
methods through their own reviewed change. The existing configured-object `Fingerprinted` mixin
already has the method shape, but its automatic field selection is unsuitable for these values.

- **Recommended: explicit method per datatype.** Name the identity-bearing fields in the method.
  Adding a timestamp or diagnostic field does not silently change identity. This is short for
  our initial records, works without a common model base, and remains available to custom types.
- **Reasonable alternative: declarative identity-field whitelist.** A shared implementation reads
  named fields. Less repeated encoding code across many similar records, but field names become
  another declaration to maintain and special cases still need overrides. Revisit when repetition
  exists. Do not infer identity by excluding attributes whose names look like timestamps.

Fingerprint equality promises equal semantic content under a declared value-kind definition.
Distinguish unrelated meanings even when fields look equal. The owner clarified that manually
maintained version numbers are not required; changes should follow relevant data, structure and
computation definitions. Selecting those definitions is under review in identity-interfaces.md.
Current explicit projections do not automatically hash a data class implementation or schema.
Preserve meaningful dates inside text or explicit temporal inputs; exclude bookkeeping creation,
modification and execution times. Keep bookkeeping outside the reusable payload where possible.
A cached result is an earlier result, not a new observation event.

For example, this proposed intermediate value selects text as its content. Its observation time
remains bookkeeping; a semantic query cutoff would instead need to enter the digest.

```python
from dataclasses import dataclass
from triplum.utils import content_key


@dataclass(frozen=True)
class PreparedText:
    text: str
    observed_at: int

    def fingerprint(self) -> str:
        return content_key("prepared-text-v1", {"text": self.text})


assert PreparedText("A", 1).fingerprint() == PreparedText("A", 2).fingerprint()
assert PreparedText("A", 1).fingerprint() != PreparedText("B", 1).fingerprint()
```

This does not promise a fresh observed_at on a cache hit. If consumers need the current observation
time, attach it outside the cached value. Consumers must not use excluded fields to change a cached
computation's semantic result.

Native `str`, `list` and NumPy arrays do not implement the protocol. Our pipeline will need reviewed
fingerprintable text/batch/vector value types rather than weakening this cache boundary. This does
not authorize rewriting existing step Protocols now. Custom users can implement the method, wrap
their value, or leave that operation uncached. The method requirement alone does not prove a good
fingerprint: the value author must cover every semantic field and avoid stale cached digests after
mutation. Cacheable functions must not mutate their inputs or rely on unrepresented external state.

## Supporting types and exact declarations

`CacheKey` contains the full configured-process digest and full input digest. Both must match.
Encoding is not part of lookup identity. Incompatible output contracts require a new process
revision or clearing the computation; there are no codec format namespaces or row migrations.
Backend choice, file path, queue settings and policy never enter those semantic fingerprints.
Process IDs are full 64-character SHA-256 hex digests, not arbitrary labels; enabled bindings
validate them before use. CacheKey digest components are exactly 32 bytes. Input fingerprints
are validated at the caching boundary. Malformed identities raise ValueError.

`output_type=Model` selects Pydantic serialization by default. `Codec[T]` is an explicit override
that converts a fingerprintable result to immutable bytes and back. Decoding preserves the result's
fingerprint and semantic content. A codec is not a storage backend; binary vector codecs can work
with SQLite, LMDB or files. No pickle fallback or automatic serialization of arbitrary objects.

`CachePolicy` is immutable. A supplied policy replaces the cache default for that binding/write;
with only `on_full` currently exposed there is no ambiguous partial merge. More flags wait for a
concrete use case. `cache=None` on a cached binding bypasses lookup, fingerprinting and encoding.

```python
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Literal, Protocol, Self

from triplum.cache.protocols import _DefaultCache


class Fingerprintable(Protocol):
    @abstractmethod
    def fingerprint(self) -> str: ...


@dataclass(frozen=True)
class CacheKey:
    process: bytes
    input: bytes


@dataclass(frozen=True)
class CachePolicy:
    on_full: Literal["skip", "block"] = "skip"


class Codec[T: Fingerprintable](Protocol):
    @abstractmethod
    def encode(self, value: T, /) -> bytes: ...
    @abstractmethod
    def decode(self, payload: bytes, /) -> T: ...


class CacheBackend(Protocol):
    @abstractmethod
    def get(self, key: CacheKey, /) -> bytes | None: ...
    @abstractmethod
    def put_many(self, entries: Sequence[tuple[CacheKey, bytes]], /) -> None: ...
    @abstractmethod
    def close(self) -> None: ...


class Cache:
    def __init__(
        self,
        backend: CacheBackend | None = None,
        *,
        pending_bytes: int = 64 * 1024 * 1024,
        policy: CachePolicy = CachePolicy(),
    ) -> None: ...
    def get(self, key: CacheKey, /) -> bytes | None: ...
    def put(
        self, key: CacheKey, payload: bytes, /, *, policy: CachePolicy | None = None
    ) -> bool: ...
    @property
    def skipped_writes(self) -> int: ...
    def flush(self) -> None: ...
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


def cached[I: Fingerprintable, O: Fingerprintable](
    compute: Callable[[I], O] | None = None,
    /,
    *,
    cache: Cache | None | _DefaultCache = _DefaultCache.SHARED,
    process_id: str | None = None,
    output_type: type[O] | None = None,
    codec: Codec[O] | None = None,
    policy: CachePolicy | None = None,
) -> Callable[[I], O] | Callable[[Callable[[I], O]], Callable[[I], O]]: ...


class CachedStep[I: Fingerprintable, O: Fingerprintable](ABC):
    def __init__(
        self,
        *,
        cache: Cache | None | _DefaultCache = _DefaultCache.SHARED,
        output_type: type[O] | None = None,
        codec: Codec[O] | None = None,
        policy: CachePolicy | None = None,
    ) -> None: ...
    def __call__(self, item: I, /) -> O: ...
    @abstractmethod
    def fingerprint(self) -> str: ...
    @abstractmethod
    def compute(self, item: I, /) -> O: ...
```

## Backend and cache guarantees

Backend `get` returns bytes or `None` for a miss; empty bytes are a value. `put_many` completes the
batch before returning. Readers must never see a partial individual value; no atomicity across
keys is required. Backends may optimize a batch as one transaction. An error may leave some complete
entries visible and is reported. Backend implementations own engine connections and their thread
constraints: `get` may run concurrently with the Cache's one writer calling `put_many`. `close`
runs after callers/writer stop. SQLite is the first implementation, using one `cache_<full process hex>` table per computation, an input-digest primary key,
encoded values and WAL. Tables are created on writes; absent tables are misses.
LMDB and files remain comparison candidates; no performance winner has been established.

Cache supports concurrent callers and one background writer. The Cache owner chooses an explicit
pending-byte budget. `get` checks accepted pending writes
before storage. `put` returns True for accepted background persistence, False for a skipped write;
acceptance is not a durability acknowledgement. `skipped_writes` exposes the count. The budget
accounts for keys, immutable payloads and an entry overhead allowance, not total process RSS.

- `skip`: a full budget returns False and increments the counter; the computed result still returns.
- `block`: wait for capacity. An item larger than the entire budget cannot make progress: proposed
  behavior is ValueError for block, and skip/count for skip. The first implementation follows
  this proposal; the tradeoff remains visible for review:
  a blocking cached call would raise after computing an oversized result. An alternative is a
  coordinated synchronous handoff through the same writer, preserving the result but relaxing the
  pending budget for one oversized entry. Neither choice may wait for impossible admission.
- Accepted entries stay pending until commit completion, not merely until dequeue. Committing an
  older write must not remove a newer pending value for the same key. Concurrent misses may compute
  twice; there is no execution-deduplication promise.
- Serialize a result to immutable bytes before admitting it. This snapshots it against caller
  mutation. Encoding is foreground work in this first contract; only persistence is deferred.
  Zero-copy or deferred encoding would require a separate ownership/lifetime contract.
- `flush` waits for writes accepted before the call and reports writer failures. It does not
  retroactively persist skipped entries or upgrade the backend's crash-durability settings.
- `close` stops admission, drains, closes resources and reports failures. It is idempotent; use
  after close raises. Context exit closes. Abrupt process loss may lose pending cache entries.
- Queue saturation is not storage exhaustion. Disk-full/engine failures are surfaced on flush/close
  and subsequent operations; `on_full='block'` must not wait forever for disk space to appear.
  A writer failure becomes sticky: stop admission, release pending entries and wake all waiting
  writers/flush callers. Subsequent get/put/flush raise the recorded failure; close cleans up before
  reporting it. The original traceback is logged; retained failure state is textual so traceback
  frames cannot keep failed payloads alive. It is not counted as queue saturation. Normal draining close can wait on engine I/O;
  interrupt cancellation and crash durability are not guaranteed by this interface.

Pending visibility is in-process. Other processes may see only committed entries and recompute
while a write is pending. The convenient shared default is lazy and process-local; there is no distributed queue or
cross-process pending visibility. Explicit ownership remains available: create one Cache per
run/owner, lend it to steps, close it.

## Decorator and mixin: one mechanism, two authoring styles

`cached` decorates a one-input function, with or without parentheses. An explicitly identified
bound callable is also supported. When supplied, process_id is validated once when binding; it covers that callable's computation, effective configuration,
helpers and model/dependency revisions. Configuration affecting computation must not mutate while
bound. Reconfigure by making a new binding. The decorator does not guess closures or hash cache
handles. It returns the same input/output call shape, not a proxy for every attribute of a step
object; for example a plain function wrapper does not expose `Embedder.dimensions`.

A use sketch, with reviewed fingerprintable TextBatch/VectorBatch types still to be introduced:

```python
cached_embed = cached(
    cache=cache,
    process_id=plain_embed_step.fingerprint(),
    output_type=VectorBatch,
    codec=vector_batch_codec,
    policy=CachePolicy(on_full="block"),
)(plain_embed_step)
result = cached_embed(text_batch)
```

For class authors, `CachedStep[I, O]` owns `__call__` and calls the subclass's `compute` on a miss
(or with cache=None). The subclass implements `fingerprint()` from its computation and effective
configuration, excluding cache/codec/policy resources. There is no separate process_id constructor
argument to drift from those fields. The enabled call reads this method; immutable configurations
can precompute their digest for cheap repeated access. It can be combined with a compatible domain step Protocol and retains
ordinary attributes. Put CachedStep before domain Protocol bases so its concrete __call__ is
selected. It borrows the Cache; destroying a step does not close a shared backend.

- **Recommended: explicit `compute` hook**, as declared. Easy to read locally, no MRO-dependent
  choice of the computation. Existing classes must move/delegate their body when opting in.
- **Reasonable alternative: cooperative `super().__call__` mixin.** Can wrap existing classes
  without moving their method, but correctness depends on mixin order and cooperative signatures.
  Useful if many existing classes need retrofitting; currently that benefit is limited.

Both forms use the same cache policy, codec, error behavior and key construction. They may wrap a
large composed block; choosing a block boundary is the pipeline author's decision. A bundled
result does not force every internal operation to have its own entry. Cache identity excludes
upstream history that is absent from the immediate semantic input; larger boundaries deliberately
trade finer internal reuse for fewer lookups. A batch embedder caches the complete ordered batch;
changing batch membership misses even for overlapping texts. Per-text reuse requires a separately
reviewed guarantee that embedding each text is independent of batch membership/order.

Manual use stays explicit and uses the same key/policy rules:

```python
key = CacheKey(
    process=bytes.fromhex(process_id),
    input=bytes.fromhex(item.fingerprint()),
)
payload = cache.get(key)
if payload is None:
    result = compute(item)
    accepted = cache.put(key, result_codec.encode(result))
else:
    result = result_codec.decode(payload)
```

The byte-level manual interface does not enforce fingerprintability itself; typed decorators and
mixins do. Manual callers take responsibility for key/content correspondence.

## What does not need another option

Explicit ownership, a bounded queue, pending-write visibility and immutable snapshots solve
concrete lifecycle/consistency needs. The shared process default has a documented location and explicit close function. An unbounded
queue or mutable references for later encoding are not equivalent low-cost alternatives. No always-off benchmark
rule is selected here; cache=None supports uncached execution, while benchmark methodology waits.

## Optional backend optimization and verification

The owner accepted considering a Bloom filter below the public interfaces. It must cover the full
lookup key. A definite-negative may avoid storage lookup only while filter coverage includes the
backend read view; a maybe-positive still uses exact lookup. Pending accepted writes are checked
first. Other-process writes, growth and rebuilding cannot silently invalidate coverage. This is
an optional measured optimization, not an extra decorator requirement.

Declaration checks: the current ty checker accepts the strict generic decorator and compute-hook
mixin sketches, preserves example result types and rejects calls passing a non-fingerprintable int.
These are type/interface probes, not implementation tests. Later behavior tests must cover changed
inputs/config, policy/codec separation, input/output fingerprint roundtrips, empty values/vectors,
read-your-writes while a commit is in flight, duplicate-key writes, queue overflow/oversized entries,
worker errors and draining close. Real backend comparison uses the same binary codecs, policy and
representative key/payload sizes, measuring reads during writes as well as idle reads.

## Pydantic default and implementation checks

`PydanticCodec(Model)` reuses one TypeAdapter. Encoding produces JSON bytes with round_trip=True
and serialization warnings treated as errors, then validates them back and compares semantic
fingerprints before admission. This intentionally adds one decode to each insertion, while hits
only decode. It rejects top-level subclass values rather than silently dropping their fields.
Unsupported fields, non-finite values that do not survive the model's JSON settings, and semantic
roundtrip mismatches fail in the caller.

Encoding does not enter cache identity. Incompatible output model, serializer or validator changes
require revising process identity or clearing its table; automatic function identity does not
discover those external dependencies. Custom codecs remain responsible for fingerprint-preserving
roundtrips.

The first implementation has no per-hit output rehash, eviction, Bloom filter, Source/Chunk
migration or embedding-type rewrite. `examples/cached_pipeline.py` demonstrates content reuse
across upstream computations, A→B→A and database reopening. The unused file-cache class was
removed by owner request; `utils.cache` retains only identity helpers. Tests exercise real temporary SQLite databases, including two simultaneous owners,
and controlled commit/read boundaries for queue, failure and close behavior.

## Independent review and sources

Claude Opus 5.5 (`claude-opus-5-5`), review `7f21ce5134b344bab6762de2d3149eea`,
challenged the initial declarations. **Changed the draft:** replaced the mixin's disconnected
process_id argument with an abstract fingerprint method, required digest validation and explicit
value-kind/version separation, and specified concurrent access and sticky writer failure behavior.
**Added verification:** concurrent admissions, waking blocked callers on worker failure, and strict
input/output type probes. **Unresolved dissent:** Opus prefers synchronous persistence for oversized
blocking entries; this draft retains the bounded-budget error proposal and makes its consequence
explicit for owner review. Per-text embedding reuse is deferred because it needs a separate semantic
guarantee. Aggregate skip telemetry remains minimal; per-step metrics have no current contract.

Attempted falsifications included deriving a safe mixin ID using existing automatic Fingerprinted
(resource hashing prevents it), applying that criticism to a bound decorator (less applicable),
old commits evicting newer pending values (already guarded), oversized admission hangs (prevented,
but computed results can be lost to the error), codec namespace collisions (covered), and reversed
mixin order (fails rather than transparently supplying the intended call). The peer did not run a
type checker or measure batch reuse. Our ty probes accept the positive declarations and reject an
actual non-fingerprintable input call; an annotated int-taking definition alone can type as an
intersection and is not necessarily rejected until called.

External research informed the single-input generic constraint, method-binding boundary and
separation of queue saturation from worker/storage errors:

- [Python typing specification: generics and bounds](https://typing.python.org/en/latest/spec/generics.html)
- [Python descriptor guide: functions and methods](https://docs.python.org/3.14/howto/descriptor.html#functions-and-methods)
- [Python queue semantics](https://docs.python.org/3.14/library/queue.html)
- [Joblib Memory](https://joblib.readthedocs.io/en/stable/user_guide/memory.html)
- [cachetools cached methods](https://cachetools.readthedocs.io/en/stable/#cachetools.cachedmethod)
- [RocksDB Bloom filter guidance](https://github.com/facebook/rocksdb/wiki/RocksDB-Bloom-Filter)


### Implementation design review

Claude Opus 5.5 (`claude-opus-5-5`), review `6e694fe8b7fb4f57b9939bda6b230c55`.
**Changed/added verification:** require computation kind/revision in process fingerprints; enforce
Pydantic exact-type encoding and fingerprint roundtrips; use explicit SQLite lock timeout,
BEGIN IMMEDIATE, WAL verification, FIFO replacement and concurrent-owner/read-close tests.
**No decision impact:** duplicate-write sequence protection and rowid tables already followed the
proposal. **Not adopted:** per-hit output digest verification would add hashing to every lookup;
the then-current codec namespace contract used schema-derived defaults and encode-time checking.
That namespace was subsequently removed by explicit owner decision; see the table/CLI review below. A backend-wide maximum-entry API is deferred; SQLite size/engine errors
surface through the documented writer failure path, and ordinary admission remains bounded.

Attacks included actual Pydantic infinity/subclass/non-UTF8 serialization probes, a SQLite point-read
transaction/checkpoint probe (the suspected lingering transaction was refuted), digest parsing
leniency and cross-computation namespace collision examples. The current linked SQLite is 3.53.1;
this does not establish compatibility/performance on every deployment. The peer did not measure
large-database performance or real multi-process contention.

An independent consistency reviewer found two unique retention defects: completed batch locals
kept payloads alive while idle, and stored exception tracebacks retained failed payloads. Regression
tests reproduced both before fixes. Successful batches now release their local references; sticky
failure state holds text while the original traceback is logged. That review also added lifecycle
and simultaneous-owner coverage.

Additional official sources: [Pydantic TypeAdapter](https://docs.pydantic.dev/latest/api/type_adapter/),
[Pydantic serialization configuration](https://docs.pydantic.dev/latest/api/config/),
[Python sqlite3](https://docs.python.org/3/library/sqlite3.html),
[SQLite WAL](https://www.sqlite.org/wal.html),
[SQLite size limits](https://www.sqlite.org/limits.html),
[WITHOUT ROWID tradeoffs](https://www.sqlite.org/withoutrowid.html).


## Parameter-light defaults requested during implementation

Both entry points are supported:

```python
@cached
def transform(item: Text) -> Text:
    return Text(text=item.text.lower())


with Cache(SQLiteBackend(path)) as cache:

    @cache.cached(policy=CachePolicy(on_full="block"))
    def specialized(item: Text) -> Text:
        return Text(text=item.text.upper())
```

The output model comes from the return annotation unless output_type or codec is supplied.
Annotation resolution and codec creation happen lazily on first use. Explicit identity remains an
independent override. Cache.cached exposes the same decorator overrides and borrows that owner.
CachedStep also defaults its cache and infers the output from compute's return annotation; its
computation fingerprint remains an explicit subclass method.

The default cache opens only when used. Its SQLite file is
`$XDG_CACHE_HOME/triplum/cache.sqlite`, falling back to `~/.cache/triplum/cache.sqlite`.
Cache() uses that same default backend and a 64 MiB pending budget. default_cache() exposes the
shared owner, close_default_cache() drains/releases it, and normal process exit provides an atexit
fallback. Abrupt termination can lose pending writes. Initialize caches after worker creation;
inherited default handles after fork are rejected rather than reused or closed in the child.

Automatic function identity covers source AST (excluding the cache decorator/docstring), qualified
function name, evaluated defaults and captured configuration. Captures must remain immutable after
decoration. Source and capture identity freeze when the decorator is applied; only codec and
database initialization wait for first use. Bind before editing the source, or supply an explicit
process_id for an already-loaded callable whose on-disk source no longer matches it. The source-less/callable-object path needs explicit process_id. External helpers, module
globals, model/library revisions, files and environment still require explicit identity; the default
is not dependency tracking. Builtin scalar/container captures use exact supported types, mapping
order is preserved, and custom captures need fingerprint() or an explicit process_id.

Independent fresh-context review **found unique defects** in initial capture hashing: dictionary
order was lost and custom builtin subclasses collapsed to their builtin value. Both were reproduced
with cached-call regressions, then fixed. Official reference:
[Python function data model](https://docs.python.org/3.14/reference/datamodel.html#user-defined-functions),
[Python inspect](https://docs.python.org/3.14/library/inspect.html),
[Python atexit](https://docs.python.org/3.14/library/atexit.html).


### Implementation code reviews

Claude Opus 5.5 (`claude-opus-5-5`), core review `d255e8907b2d492881b7eaa06d382112`:
**Found unique defects:** simultaneous writer/cleanup errors could hide the writer failure and mark
cleanup complete prematurely; buffered logging could retain failed payloads via exc_info. Tests
reproduced both. Close now groups both errors and permits cleanup retry; logs retain formatted stack
text without traceback frames. **Added verification:** capacity waiters demonstrably remain pending
before the test releases a failing commit. **Historical tradeoff:** schema documentation changes
could cause misses under the now-removed format namespace. SQLite lock timeout remains sticky; nested subclass serialization
requires suitable Pydantic annotations and semantic fingerprints that include all consumed fields.
The automatic roundtrip check cannot repair an incomplete fingerprint. **No decision impact:**
explicit owners still require close, disabled caching skips identity checks, sequence numbers and
failure checks remain for readable lifecycle invariants; the backend Protocol intentionally permits
partial batches even though SQLite transactions are atomic.

Attacks included actual stale-read/overwrite probes (refuted), read/commit/removal and close/read
interleavings (no violation found), blocked-put and flush ordering, empty values, schema description
changes, nested subclass truncation, transaction rollback and unclosed-owner retention. The review
was not a performance benchmark and did not run the complete repository suite.

Claude Opus 5.5, convenience review `c1e067b6e066427b965267e5d7e74425`:
**Found unique defect:** lazily reading source on first call could hash edited code while executing
an older loaded function. A temporary-module regression reproduced a wrong hit. Source/capture
identity now binds at decoration; codec resolution and database opening remain lazy. **Changed:**
source parse errors and captured classes give explicit-identity guidance; a child with no inherited
cache recreates the inherited default lock; interpreter shutdown forbids reopening the default.
**Added verification:** a late atexit handler cannot reopen the database after cleanup.
**Documented tradeoff:** stop/join borrowed computations before closing their default owner;
in-flight computations are not silently converted to uncached results after close. Relative
XDG_CACHE_HOME is ignored, following the official specification. **No decision impact:** generic
return models require an explicit codec, cache=None bypasses validation, and mixin codec inference
remains lazy for uniform forward-reference behavior.

That peer reproduced source-file drift, shutdown reopening and source/capture error cases; attacked
polymorphic/generic returns, wrapped functions, scalar/container tags and forked handles. Unsupported
cases failed safely; it did not run our full tests or verify free-threaded CPython. XDG behavior was
subsequently checked against the [official specification](https://specifications.freedesktop.org/basedir/latest/).


## Per-computation tables and administration

The owner explicitly selected one SQLite table per full computation identity, keyed only by input
identity. No codec format identity, hidden schema digest or migration layer remains. Fingerprint
implementations select semantic fields and exclude bookkeeping timestamps; this is not an automatic
field-name filter. Incompatible output contracts require a process revision or an explicit clear.

`triplum cache stats` lists recognized computations and database/WAL/reusable bytes without scanning
entries. `--details` scans selected tables for exact committed counts and payload sizes, using one
snapshot; filesystem sizes are separate observations. `--path`, exact `--computation`, `--json`
and `--no-input` are supported. `triplum cache clear` drops all recognized computation tables or
the selected one, without VACUUM. Stop writers for lasting emptiness; accepted writes can recreate
tables. Missing database paths are not created. Read-only stats can require WAL/SHM sidecars and
write access to their containing directory. Unrelated/unrecognized tables are preserved. Library
functions live in `triplum.cache.admin`; the CLI is a thin wrapper.

Claude Opus 5.5 (`claude-opus-5-5`), design review `0055212ba7284728bf9314b6de79b8b9`:
**Rejected dissent:** the peer preferred a single table and hidden format identity, conflicting with
the owner's explicit per-table/no-format choice. **Changed/added verification:** snapshot statistics
and clear semantics. Attacks covered schema coverage, CLI availability, counter feasibility and
concurrency. No performance measurements were produced; table layout has no claimed speedup.

Claude Opus 5.5, diff review `4f2c16a9319a4bbebd3c8d3e2c22c70b`:
**Found unique defect:** legacy-table cleanup could drop an unrelated `cache_entries` table; cleanup
was removed so only recognized computation tables are affected. **Added documentation:** read-only
stats can manage SQLite sidecars. **No change to approved key design:** external output-contract
changes still require explicit process revision or clear. Attempts included SQL injection,
reader/clear races, old snapshots, multiple writers, corrupt files and read-only directories.
Dynamic SQL and clear concurrency survived those probes; this was not a performance benchmark.
