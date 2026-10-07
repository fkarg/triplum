# Cached pipeline: identity and reuse

Status: the owner approved reuse of identical intermediate content across different upstream
processes, excluding bookkeeping timestamps, with Bazel's cache design as orientation. The
concrete encoding and example below are a draft for interface review, not an implemented API.

The owner subsequently clarified the performance target: a cache of a few dozen to a few hundred
GB, able to grow further; very low-overhead exact-key lookup; deferred background writes; and a
decorator interface constrained to fingerprintable inputs/outputs. SQLite and bundled chunk/vector
results are candidates, not selected contracts. The lookup-first extension below records the new
tradeoffs. The JSON example illustrates identity only, not the proposed high-performance codec.

## Purpose and identities

Reuse intermediate work while composing and changing pipelines. An input that changes A → B → A
recovers A's fingerprint and can reuse its retained results. Changing an upstream process does
not invalidate downstream work when its actual input is unchanged.

Three identities have different jobs:

| Identity | Contains | Purpose |
| --- | --- | --- |
| Data fingerprint | Value kind/encoding version and its semantic content | Recognize the same input or output, regardless of how it was produced. |
| Process fingerprint | Implementation and effective configuration/dependencies | Identify the operation that will run. |
| Computation key | Immediate input fingerprint, current process fingerprint and output encoding | Look up a previously computed result before executing the operation. |

Use the existing full SHA-256 `content_key` digests for these fingerprints and keys. Record UUIDs
remain storage identities with their separately reviewed layouts; short collection/source prefixes
are never cache identities. A record reference may be part of an operation's semantic input, but
its UUID is not a substitute for hashing additional values the operation reads.

An output fingerprint does not include its producing computation key. Run/provenance records may
retain that association separately. No new provenance record or graph executor is proposed here.

## What counts as data

Fingerprint an explicit, typed value, not an unrestricted dump of a runtime object:

- Include all values affecting the result, including copied references when caching records.
  List order and duplicates count. Strings are exact; there is no implicit whitespace, path,
  Unicode or newline normalization.
- Exclude creation, modification, access and execution timestamps used only as bookkeeping,
  along with durations, cache-hit flags and the upstream process history. Keep those outside the
  reusable value. A cache hit must not pretend the original execution happened again now.
- Do not strip timestamp-looking fields recursively. A date in source text remains content.
  An explicit temporal query constraint such as `as_of` affects the answer and therefore the
  computation key. This semantic-time distinction is proposed for the later query interface.
- Data kind and encoding labels define equality locally: source records, text batches and vectors
  have different encodings. Change the label when that encoding or equality contract changes.
- Encoded values use JSON-native shapes: string-keyed objects, lists, strings, booleans, null and
  finite numbers. Other types require an explicit encoding. The existing JSON helper does not
  enforce this restriction; concrete stage encoders own it. Do not silently equate an integer
  object key with a string key, or an arbitrary tuple with a list.
- Process identity must cover settings, relevant helper implementations, dependency/model revisions
  and effective requests/seeds where applicable. Runtime clients and mutable counters are not
  configuration. The current `Fingerprinted` mixin covers class/base code and instance state;
  it does not automatically discover helpers or external revisions. Overrides must supply them.

A step can receive an explicit projection of a record when it needs less information. Embedding
receives text, so its input fingerprint need not include a Source's origin or collection. A step
that actually reads provenance, visibility or source identity must include that context instead.
Do not feed a whole record to an arbitrary step while claiming only its text determines the result.

### Record identity remains separate

The proposed Source UUIDv8 payload is `[collection tag 24][scoped fingerprint 98]`; the owner
prefers at least 24 tag bits, with exact width still open. Proposed identity inputs are full
collection ID, exact origin and prepared text, excluding bookkeeping times. The agreed Chunk
layout remains `[tag 16][source prefix 42][ordinal 16][fingerprint 48]`. Full collection identity
must enter Source's digest, and full Source identity must enter Chunk's digest; differing short
tag widths do not remove scope from those hashes. These ID contracts are not implemented yet.

Today's `Source.fingerprint` and `Chunk.fingerprint` properties are not the proposed full-record
fingerprints: Source lacks collection membership, Chunk's fingerprint omits `source_id`, and its
Path-to-string conversion can normalize spelling. A model dump also includes fresh UUIDv7 IDs
and the computed fingerprint. Do not use these properties to key whole-record results under this
contract. Their replacement remains part of the record-identity review; the text-batch example
does not use them.

Two different Sources may produce the same embedding input and reuse the same vector computation.
That does not merge their record identity, provenance or permissions. Initially this is a local,
single-user cache; a shared service's authorization contract is deferred.

## Lookup and result contract

Keep the existing storage declarations unchanged:

```python
class Cache:
    def __init__(self, root: Path | str) -> None: ...
    def get_json(self, key: str) -> Any | None: ...
    def put_json(self, key: str, obj: Any) -> None: ...
```

`Path` is a filesystem path, `str` is also accepted for the explicit cache directory, and `Any`
reflects the current untyped JSON helper API, not a proposal to broaden a new interface. Each
concrete stage owns its value encoding and reconstruction. These are the current primitives;
the requested fingerprintable decorator interface is still to be declared and reviewed. A
fingerprint alone does not provide the result codec needed for disk persistence.

A cache entry is a JSON object with exactly these fields:

```text
{"output_fingerprint": <full digest>, "output": <encoded reusable value>}
```

For a single-input step, compute the input fingerprint from that value. For multiple inputs,
fingerprint their named or ordered aggregate so argument roles, ordering and multiplicity remain
part of the request. Then:

1. Compute the current process fingerprint and computation key.
2. Look up the key. A stored object is a hit; `None` means a miss. The envelope also permits an
   output value of JSON null without confusing it with a missing entry.
3. On a miss, execute, encode the result, fingerprint that encoded content and store the entry.
4. On a hit, reconstruct the saved output without calling the step.
5. For the next step, fingerprint the actual value it receives, including any projection or
   assembly performed between stages. If it receives the unchanged output under the same value
   kind/encoding, reuse the stored `output_fingerprint` directly. Otherwise recompute for the
   projected/assembled input. Never substitute the producer's computation key.

Equal computation keys permit reuse of a previous result under the declared process contract.
For deterministic stages, cold and warm runs must have equivalent semantic outputs. Caching a
stochastic operation reuses one realization; it does not establish that rerunning would reproduce
it. Independent samples must execute explicitly. This first example uses deterministic steps only.
Failed computations are not cached. Concurrent misses may compute twice; the existing atomic
file replacement prevents partial reads but does not provide execution deduplication. No locking,
eviction, remote service or second content-addressed blob store is added here.

### Concrete key example

This runnable example establishes key construction using existing interfaces. `text-batch-v1`
identifies the ordered text-list encoding; `vectors-f32-v1` identifies a vector result encoded as
an object containing its `dtype`, `shape` and row-major `values`. The demo uses finite float32
vectors, reconstructed as float32 arrays. NumPy's revision is explicit because this implementation
calls NumPy; automatic process fingerprinting does not include that dependency.
Encoding and reconstruction code are outside the step fingerprint: a semantic change to either
requires an explicit encoding-label bump. A constant containing the label does not automate that
decision. This demo uses exact encoded finite float32 values, not tolerance-based equivalence.

```python
import numpy as np

from triplum.steps.embedding import ZeroEmbedder
from triplum.utils.cache import content_key

texts = ["Returns are accepted within 30 days."]
embedder = ZeroEmbedder(dimensions=3)
input_fp = content_key("text-batch-v1", texts)
process_fp = content_key(
    "embedding-process-v1",
    {"step": embedder.fingerprint(), "numpy": np.__version__},
)
computation_key = content_key(
    "computation-v1",
    {"input": input_fp, "process": process_fp, "output_kind": "vectors-f32-v1"},
)

vectors = embedder(texts)
output = {"dtype": "float32", "shape": list(vectors.shape), "values": vectors.tolist()}
output_fp = content_key("vectors-f32-v1", output)
entry = {"output_fingerprint": output_fp, "output": output}
restored = np.asarray(output["values"], dtype=np.float32).reshape(output["shape"])
assert vectors.shape == (1, 3)
assert np.array_equal(restored, vectors)
assert len(computation_key) == len(output_fp) == 64
```

Origin, collection and earlier preprocessing identities do not enter this embedding request:
`Embedder` receives only the ordered text batch. Keep caching at that existing batch boundary;
per-text reuse for arbitrary embedders would require a separate batch-invariance guarantee.

## Reuse policy and benchmarking

Ordinary execution uses the supplied cache for reads and writes. Proposed bypass semantics:
execute without reading or writing cached results, leaving previous entries intact. Bypass is
execution policy, not an added timestamp, nonce or altered data fingerprint. Returning to ordinary
execution can still reuse the original entry.

For explicit benchmarking later, bypass must reach every cache within the measured work, including
nested expensive calls. Warm-cache performance can be measured separately and labeled. Refreshing
an existing entry is a different policy and is not needed for this example. The benchmark API,
policy flags and propagation mechanism remain deferred; no new flag is added to every step.

## Small example and verification

Use the existing steps in a plain example function, with no pipeline executor:

```text
Source → FixedSize → chunks → OriginalText → text batch → ZeroEmbedder → vectors
```

The initial example proposal caches only the embedding batch; chunking and embedding-text preparation run
each time. In particular, `FixedSize(100)` and `FixedSize(200)` over a source shorter than 100
characters produce the same text batch and should share the embedding entry. This exercises
upstream process changes without putting upstream process fingerprints in the embedding key.
The owner is now considering a bundled chunk result instead; final cache granularity is open.

The example must distinguish value reuse from record reconstruction. Today's `FixedSize` produces
chunks referencing the supplied Source and assigns fresh UUIDv7 IDs. A cache of complete chunks
keyed only on source text would return stale parent links. Before caching that stage, either
complete the deterministic record identity review, or cache identity-free slice payloads and bind
them to the current Source afterward. Those alternatives belong to the next boundary review;
neither is needed for this first text/vector reuse example.

Use a real temporary disk cache and show explicit HIT/MISS labels. Verify:

1. Cold run computes embeddings; an identical run with a newly opened Cache instance hits.
2. A → B → A reuses the retained A result; restoring process configuration also restores lookup.
3. Two upstream processes producing identical immediate inputs share downstream computation keys.
4. Changed actual embedding input or embedder settings misses. Changing only dimensions preserves
   the text-batch fingerprint but must miss the embedding entry. Ordered-batch changes miss.
5. Equal text from different records reuses text-only computation without reusing the wrong parent
   references. After deterministic IDs are implemented, cold/warm record identities also agree.
6. Bypass executes without reading or writing the cache; subsequent ordinary lookup still hits
   the original entry.
7. Empty batches reconstruct with shape `(0, dimensions)`, not `(0,)`; reconstruction always
   uses the saved shape.

Record actual execution counts outside fingerprinted step state. Zero-valued embeddings cannot
by themselves demonstrate correct invalidation. The example must work from an empty cache.

## Orientation and independent review

[Bazel remote caching](https://bazel.build/remote/caching) separates action lookup from output
content addressing. We adopt that identity distinction while retaining one simple disk store;
separate action/CAS storage is not required yet. Its
[hermeticity guidance](https://bazel.build/basics/hermeticity) motivates explicit effective inputs.
The [remote execution protocol](https://github.com/bazelbuild/remote-apis/blob/main/build/bazel/remote/execution/v2/remote_execution.proto)
distinguishes skipping lookup from preventing storage; our proposed benchmark bypass deliberately
disables both. These are project choices, not a claim of Bazel API compatibility.

### Initial review

Claude Opus 5.5 (`claude-opus-5-5`), review `638dc6908d9546fba7e060ff0630d79a`, tested cached
parent references, A → B → A, cross-collection IDs, reverted process settings, zero-valued
embeddings, record serialization and Path/string normalization.

- **Added verification:** cached parent linkage, cold/warm identity equivalence when IDs become
  deterministic, configuration reversion and explicit execution counts.
- **Changed the proposed design:** exposed the content-versus-process-chain choice. The owner
  approved content-based downstream reuse; upstream process history stays outside value identity.
- **Rejected as false positive:** its tag-width collision claim assumed hashes omitted full
  scope identity. Differing tag widths do not force identical IDs when full identities enter the
  remaining hashes. A registry and its claim of collision impossibility were not adopted.
- **Deferred:** observation/validity records, notebook autoreload, origin-type cleanup, per-text
  embedding caching and generalized provenance.

### Contract review

Claude Opus 5.5 (`claude-opus-5-5`), review `4eaaee85b41a4c398337ace4f728238c`, tested changed
dimensions, current record fingerprints, JSON encoding ambiguities, fresh UUIDs, float32
roundtrips, empty batches, equal outputs from different chunkers, kind/payload separation and
bypass behavior.

- **Changed the draft:** made the first cached boundary explicitly text batch → vectors; identified
  existing record fingerprints as insufficient for whole-record caching; specified JSON-native
  payloads and when the saved output fingerprint can directly identify the next input.
- **Found a unique defect / added verification:** an empty vector list loses its second dimension
  unless reconstruction uses the saved shape. Added reconstruction and the empty-batch check.
- **Added clarification:** changing dimensions misses embedding while preserving input identity;
  the earlier phrase "reuses earlier work" did not mean reusing incompatible vectors. Encoding
  changes require deliberate version bumps and fixed-value roundtrip verification.
- **Rejected as unnecessary:** flattening input/process fingerprints into one key discards the
  useful identities this example teaches; removing the output fingerprint defeats its explicit
  chaining purpose. Moving an encoding label into a constant does not automatically invalidate
  caches when codec code changes, so it does not solve that versioning responsibility.
- **Deferred:** equivalence across hardware for real embedders and notebook autoreload. The
  deterministic zero-vector example makes neither guarantee.

## Lookup-first extension under discussion

New owner constraints and current recommendations, not yet an approved runtime interface:

- Exact match on both configured process identity and actual input identity. A composite binary
  key can store that pair directly; another hash is optional. Include output encoding revision in
  process identity. IDs must account for the values actually consumed, not just a record name.
- Keep fingerprints available before lookup. Recomputing process state/JSON hashes on every hit
  works against the latency goal. Precomputed identities require immutable identity-bearing
  inputs and configured processes, or explicit invalidation when they change.
- Expose a typed decorator with fingerprintable input/output constraints plus a result codec.
  Existing strings, lists and NumPy arrays lack a fingerprint method; wrappers or typed adapters
  need their own narrow interface review. Decorating every existing step is not assumed.
- Prefer an explicitly owned cache instance shared by decorated steps, with connection lifetime
  spanning a run. Avoid a hidden global ORM session and per-lookup connection creation.
- A background writer batches persistence. A bounded pending map/queue makes newly computed
  results visible in-process before commit. Bound memory by bytes, not just entry count; retain
  pending entries until their commit completes. Enqueue immutable snapshots, not mutable results
  whose later edits could be stored under an old key. Normal close drains; crash recovery may
  lose pending entries and require recomputation. Cross-process pending visibility is not promised.
- Queue-full policy is a real tradeoff: blocking preserves insertion attempts but delays callers;
  skipping new cache inserts protects foreground latency but may cause later recomputation.
  Recommendation for the owner's stated priority: skip and count, not silently grow the queue.
  Writer errors must be surfaced; they are not equivalent to an ordinary cache miss.
- Measure SQLite and LMDB against the existing file cache, using the same binary values and key
  widths. No winner is established. SQLite rowid versus WITHOUT ROWID is a layout variable,
  especially with large result blobs. Do not load the whole cache into a Python dictionary.
- A chunk result may contain vectors without forcing a single cache key for all internal work.
  Caching an entire chunking/preparation/embedding block reduces lookups but couples invalidation;
  caching the expensive suboperation preserves finer reuse. Measure both if the distinction matters.
  Per-text embedding lookup needs a batch-invariance contract; the current batch Protocol does
  not provide one.

For the first comparison, separate precomputed-key lookup, full hit/decode, miss/compute/encode,
queue admission and background drain. Measure p50/p95/p99 reads while writing, index/payload size,
pending bytes and commit latency. Report memory residency and dataset size; a reopened connection
is not proof of a cold disk. Use representative payload sizes and a meaningful entry count, with
matched persistence guarantees. Do not populate hundreds of GB without agreeing resource limits.

A small exploratory local probe found vector JSON encoding/decoding much costlier than warm
storage reads: a 32×1536 float32 batch was 196,608 raw bytes versus 947,003 JSON bytes, with roughly
14.7 ms encoding and 7.8 ms decoding. Backend populations were only 32 or 256 entries and warm;
the probe omitted environment/version capture, writes and contention. It cannot establish a
backend winner or large-cache scaling. It motivates binary payloads in the proper comparison.

Primary references: [SQLite query planning](https://sqlite.org/queryplanner.html),
[WITHOUT ROWID tradeoffs](https://sqlite.org/withoutrowid.html),
[SQLite WAL](https://sqlite.org/wal.html),
[Python connection behavior](https://docs.python.org/3/library/sqlite3.html), and
[py-lmdb](https://lmdb.readthedocs.io/en/latest/). SQLite WAL and LMDB allow concurrent readers
with a serialized writer. LMDB also requires deliberate map growth and transaction/buffer
lifetimes; mmap does not make the entire database resident in RAM.

Claude Opus 5.5 (`claude-opus-5-5`), review `2f0bc747122245b2a62ef4d6c9541ddd`, tested hashing
cost, repeated process fingerprinting, bundled-key invalidation, possible batch dependence,
Protocol hashing and file-read/write races. Its own timings used in-memory SQLite and do not
establish on-disk performance.

- **Added verification / design detail:** separately measure hashing, serialization, value reads
  and lookup; keep configured process identities stable; define pending visibility and lifecycle.
- **Dissent retained:** it requires per-text embedding entries and rejects bundled computations.
  Per-text caching is not sound for every current Embedder without batch invariance; bundling
  trades reuse granularity for fewer lookups rather than being universally incorrect. No blanket
  per-text wrapper is approved.
- **Dissent retained:** it recommends blocking on a full queue; the current recommendation is to
  skip new cache writes to protect foreground latency. Owner decision remains open.
- **Rejected as unsupported:** predicted universal backend winners and a default WITHOUT ROWID
  layout were not established by its in-memory timings; official SQLite guidance makes row size
  relevant. Keep the comparison empirical.
