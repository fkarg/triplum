# Small cached pipeline example — proposal

The owner wants a small example demonstrating pipeline composition and, particularly, cache
reuse through input fingerprints and process fingerprints. Source identity should recover the
original ID after text changes A → B → A. Query/benchmark reuse motivates the design but is not
part of this first example. No new implementation contract is approved here.

## Identity direction

- Source: proposed UUIDv8 payload `[collection tag 24][scoped fingerprint 98]`. The owner prefers
  at least 24 collection bits; exact width is not finalized.
- Proposed hash inputs: full collection ID, exact origin and exact prepared text, with an explicit
  record-kind/encoding label. Creation/change times are excluded. Future fields need deliberate
  identity decisions instead of automatically hashing the entire model.
- Chunk's agreed `[tag 16][source prefix 42][ordinal 16][fingerprint 48]` allocation is unchanged.
  Its short tag can use 16 bits of the same collection hash. Full collection identity participates
  in Source's digest; full Source identity must participate in Chunk's digest. Tags alone never
  establish scope or equality.
- A repeated content state is the same identity, not a new observation event. Recording when
  each state was current remains separate, deferred work.

UUIDv8 leaves 122 custom bits and permits application-specific layouts. Python's `uuid8` accepts
48/12/62-bit payload fields; packing must account for reserved version/variant bits. Sources:
[RFC 9562](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.8),
[Python UUID docs](https://docs.python.org/3.14/library/uuid.html#uuid.uuid8).

## Proposed demonstration

Use the existing step implementations in an ordinary example function:

```text
Source → FixedSize → chunks → OriginalText → text batch → ZeroEmbedder → vectors
```

Use the existing explicit-directory `Cache`, `content_key` and process `fingerprint()` methods.
Cache complete results under computation keys; no second blob store or general pipeline executor
is needed. Keep embedding caching at the existing batch boundary: the ordered text batch and
embedder fingerprint determine the key. Per-text caching for arbitrary embedders is not approved.

A computation key identifies a requested computation:

```text
key = hash(stage kind, process fingerprint, input fingerprint)
```

The pending choice is what feeds the next stage:

| Choice | Consequence |
| --- | --- |
| Previous computation key | Preserves the entire upstream process chain; upstream process changes invalidate downstream work even if output is identical. |
| Actual output fingerprint | Identical outputs can reuse downstream work; provenance must separately retain which upstream process produced them. |

Recommendation for discussion: distinguish content identity from computation identity, and use
actual input content/record identity for downstream lookup. Fingerprints must cover every value
affecting the cached result, including copied parent references when caching whole records.
Source/Chunk UUID work can precede the example, or complete cached records can be restored with
their parent records; caching chunks from one random Source and attaching them to a fresh random
Source is incorrect. The implementation sequence is still for owner review.

Demonstrate and test these behaviors with a real temporary disk cache:

1. Cold run computes stages; an identical run using a newly opened Cache instance hits.
2. A → B → A returns the original IDs and reuses A's retained results.
3. Changing a chunker setting changes its computation key; restoring it reuses the old result.
4. Changing only embedding dimensions reuses earlier stages and recomputes vectors.
5. Cached chunks refer to the correct Source, including across distinct collections.
6. Empty-cache and warm-cache runs agree on record identities under deterministic ID generation.

Print explicit HIT/MISS labels. Assert actual execution counts outside fingerprinted step state;
ZeroEmbedder's zero-valued outputs alone cannot establish that reuse/invalidation worked.
The existing process fingerprint covers class/base code and instance settings, but not called
helper code or dependency versions automatically. The example must state that existing limit.

## Research and independent review

[Hugging Face Datasets](https://huggingface.co/docs/datasets/about_cache) combines preceding
fingerprints and transforms; [Bazel](https://bazel.build/remote/caching) distinguishes action
lookup from output-content storage. Both inform the alternatives above; adopting their frameworks
or separate stores is unnecessary for this example.

Claude Opus 5.5 (`claude-opus-5-5`), review `638dc6908d9546fba7e060ff0630d79a`, challenged the
proposal. It examined cached parent references, A → B → A, cross-collection IDs, changed/reverted
process settings, zero-valued embeddings, record serialization, and Path/string normalization.

- **Added verification:** cached parent linkage, cold/warm identity equivalence, configuration
  reversion and explicit execution counts. These target concrete failures in caching today's
  records, whose IDs are generated randomly.
- **Decision impact:** exposed the content-versus-process-chain choice explicitly. The peer
  recommends content-based downstream keys; the owner's choice remains pending.
- **Rejected as false positive:** differing tag widths do not force identical Chunk IDs across
  collections when full collection/Source identities participate in the remaining hashes.
  Its collision claim assumed content-only hashes omitting scope. Its registry proposal and
  claim of collision impossibility are not adopted; finite hashed identities still admit collisions.
- **Deferred:** observation/validity records, notebook autoreload behavior, origin-type cleanup,
  per-text embedding caching and generalized provenance. These do not justify expanding the demo.
