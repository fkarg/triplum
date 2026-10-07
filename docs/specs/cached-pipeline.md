# Cached pipeline: identity and reuse

Status: the owner approved reuse of identical intermediate content across different upstream
processes, excluding bookkeeping timestamps, with Bazel's cache design as orientation.
The implemented optional cache contract and its review decisions live in
[Cache interfaces](cache-interfaces.md). The current [identity interface draft](identity-interfaces.md)
audits the remaining shared fingerprint contract; it does not authorize implementation.
[Record types](record-types.md#decisions) remains authoritative for record identity decisions.

This page preserves the reuse, provenance and measurement constraints behind those interfaces.
The earlier file-cache declarations, JSON-envelope example and output-format key proposal have
been superseded by the cache contract. They are available in Git history.

## Purpose and identities

Reuse intermediate work while composing and changing pipelines. An input that changes A → B → A
recovers A's fingerprint and can reuse its retained results. Changing an upstream process does
not invalidate downstream work when its actual input is unchanged.

| Identity | Contains | Purpose |
| --- | --- | --- |
| Data fingerprint | Value kind/version and its semantic content | Recognize the same input or output, regardless of how it was produced. |
| Process fingerprint | Implementation and effective configuration/dependencies | Identify the operation that will run. |
| Computation key | Immediate input fingerprint and current process fingerprint | Look up a previously computed result before executing the operation. |

The cache contract uses full SHA-256 identities. Storage codecs do not add a key component;
incompatible output contracts require process revision or clearing, as specified in
[Cache interfaces](cache-interfaces.md). Record UUIDs and short collection/source prefixes do not
replace these full identities. A reference may be part of an operation's semantic input, but its
UUID does not identify additional values the operation reads.

An output fingerprint does not include its producing computation key. Run/provenance records may
retain that association separately. No new provenance record or graph executor is proposed here.
For the next step, fingerprint the actual value it receives, including any projection or assembly
between stages. Never substitute the producer's computation key for the value fingerprint.

## What counts as data

Fingerprint an explicit, typed value, not an unrestricted dump of a runtime object:

- Include all values affecting the result, including copied references when caching records.
  List order and duplicates count. Strings are exact; there is no implicit whitespace, path,
  Unicode or newline normalization.
- Exclude creation, modification, access and execution timestamps used only as bookkeeping,
  along with durations, cache-hit flags and upstream process history. A cache hit must not
  pretend the original execution happened again now.
- Do not strip timestamp-looking fields recursively. A date in source text remains content.
  An explicit temporal query constraint such as `as_of` affects the answer and therefore the
  computation key. This semantic-time distinction remains proposed for the later query interface.
- Value kind/version distinguishes semantic contracts; changing storage representation alone
  does not redefine semantic equality. The supported canonical value domain is part of the
  [identity interface review](identity-interfaces.md). Existing JSON helpers do not enforce one;
  do not silently equate integer and string object keys, or arbitrary tuples and lists.
- Process identity must cover settings, relevant helper implementations, dependency/model revisions
  and effective requests/seeds where applicable. Runtime clients and mutable counters are not
  configuration. Automatic class/function hashing does not discover every external dependency;
  explicit process identity must cover those dependencies.

A step can receive an explicit projection of a record when it needs less information. Embedding
receives text, so its input fingerprint need not include a Source's origin or collection. A step
that reads provenance, visibility or source identity must include that context instead.
Do not feed a whole record to an arbitrary step while claiming only its text determines the result.

### Record identity remains separate

The agreed UUID allocation, Source A → B → A requirement, collection scope and unresolved record
inputs are recorded in [Record types](record-types.md#decisions). Those decisions remain in force;
the identity audit does not reopen them or authorize the unimplemented migration.

Today's Source and Chunk fingerprint properties are insufficient for general whole-record
caching: Source lacks collection membership and Chunk omits its parent reference. Model dumps
also include generated UUIDv7 IDs and computed fingerprints. Their replacement remains under
review; changing a property into a method alone does not settle semantic equality.

Two different Sources may produce the same embedding input and reuse vector computation.
That does not merge their record identity, provenance or permissions. Cached complete records
must preserve the correct parent references. Initially this is a local, single-user cache;
a shared service's authorization contract remains deferred.

## Execution and reuse constraints

Equal computation keys permit reuse under the declared process contract. For deterministic
stages, cold and warm runs must have equivalent semantic outputs. Caching a stochastic operation
reuses one realization; it does not establish that rerunning would reproduce it. Independent
samples must execute explicitly. Failed computations are not cached, and concurrent misses may
compute twice; execution deduplication is not promised.

Steps or larger composed blocks may opt in. Bundling reduces lookups but couples invalidation;
caching expensive suboperations preserves finer reuse. Per-text embedding reuse needs a
batch-invariance contract, which the current batch Protocol does not provide. Concrete
fingerprintable intermediate types require their own review; arbitrary adapters and changes to
all existing steps are not authorized.

The implemented reuse example is [examples/cached_pipeline.py](../../examples/cached_pipeline.py).
Its contract and verification belong to [Cache interfaces](cache-interfaces.md), rather than the
superseded text/vector encoding example. Future record/vector integrations must additionally verify
parent linkage, relevant ordering and dimensions, and reconstruction of empty vector batches.
Record execution counts outside fingerprinted step state: identical or zero-valued results alone
cannot demonstrate correct invalidation. Every stage must work from an empty cache.

## Reuse policy and benchmarking

The cache contract keeps resources, backend choice, queue settings and execution policies outside
semantic fingerprints. The selected queue-full default is skip and count; blocking remains an
option. Background visibility, drain and failure guarantees live in
[Cache interfaces](cache-interfaces.md), without a second lifecycle specification here.

Benchmark methodology, including whether caches should always be disabled, remains deferred.
The intended benchmark bypass executes without reading or writing cached results and leaves
previous entries intact. It is policy, not an added timestamp, nonce or altered data fingerprint.
A future uncached measurement needs bypass to reach nested caches in the measured work;
warm-cache measurement is a separate possibility. Neither is a selected benchmark policy.
Refreshing entries is different from bypass; its benchmark API and propagation remain deferred.

The owner requested very low-overhead exact-key lookup at a few dozen to a few hundred GB, with
room to grow. No backend performance winner has been established. A meaningful comparison must
separate precomputed-key lookup, full hit/decode, miss/compute/encode, queue admission and drain.
Measure read latency while writing, index/payload size, pending bytes and commit latency, with
representative payloads and matched persistence guarantees. Report memory residency and dataset
size: reopening a connection is not proof of a cold disk. Do not populate hundreds of GB without
agreeing resource limits.

Earlier warm probes with small populations suggested serialization deserved separate measurement;
they omitted sufficient environment capture, scale and contention to support a backend choice.
Optional Bloom filtering remains a backend proposal under [Cache interfaces](cache-interfaces.md),
not a new requirement on steps or decorators.

## Orientation and independent review

[Bazel remote caching](https://bazel.build/remote/caching) and
[hermeticity guidance](https://bazel.build/basics/hermeticity) informed the distinction between
computation and output identity and the need for explicit effective inputs. Separate action/CAS
storage is not a project requirement, and no Bazel API compatibility is claimed.

The earlier reviews below informed constraints retained here. Later cache-specific decisions and
reviews are authoritative in [Cache interfaces](cache-interfaces.md).

- Claude Opus 5.5 (`claude-opus-5-5`), review `638dc6908d9546fba7e060ff0630d79a`, tested parent
  references, A → B → A, cross-collection IDs, reverted process settings, zero-valued embeddings,
  serialization and Path/string normalization. **Changed the decision:** downstream reuse follows
  content, not upstream process history. **Added verification:** parent linkage, configuration
  reversion, execution counts and cold/warm identity equivalence after deterministic IDs.
  **Rejected as false positive:** tag-width collisions were argued assuming full scope identity
  was omitted from hashes; short tags do not replace full scope inputs.
- Claude Opus 5.5 (`claude-opus-5-5`), review `4eaaee85b41a4c398337ace4f728238c`, tested dimensions,
  record fingerprints, JSON ambiguities, fresh UUIDs, float32 roundtrips, empty batches, equal
  outputs from different chunkers, kind separation and bypass. **Changed the draft:** identified
  insufficient whole-record fingerprints and the need to fingerprint actual downstream values.
  **Unique defect / added verification:** an empty vector list loses its second dimension unless
  reconstruction retains shape. Its encoding-envelope details were superseded by the codec contract.
- Claude Opus 5.5 (`claude-opus-5-5`), review `2f0bc747122245b2a62ef4d6c9541ddd`, tested hashing cost,
  process rehashing, bundled invalidation, batch dependence, Protocol hashing and file I/O races.
  **Added verification:** measure hashing, serialization and storage separately and define pending
  visibility/lifecycle. **Dissent retained:** it required per-text entries and rejected bundling;
  batch invariance is unapproved and bundling is a legitimate granularity tradeoff. **Dissent
  retained:** it preferred blocking on a full queue; the owner selected configurable skip and count.
  **Rejected as unsupported:** universal backend/layout winners did not follow from in-memory timings.
