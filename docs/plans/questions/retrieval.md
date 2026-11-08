# Retrieval results, Viewer and BM25 baseline

Questions use the `RT` prefix. Process: [questions index](README.md).

## Open

### RT10. Collection at retriever construction or per query

Follows Q33 (queries select one collection, per-collection optimization only). Either a retriever
is bound to one collection when built (`BM25(store, collection_id=..., viewer=...)`, `Retriever`
call unchanged), or the call takes it (`(query, /, *, collection_id, viewer, k)`).

- Claude: bind at construction; it matches the snapshot index and keeps statistics per
  collection without index routing; fusion components must be built for the same collection.
- Peer (gpt-6.1-sol, 2026-11-08): same, independently. Per-call selection would need BM25 to
  route to or build per-collection indexes (new lifecycle decisions); a constructor plus a call
  override duplicates selection. Neither gives run identity automatically: runs must record the
  collection, indexed content and construction viewer.

Owner (2026-11-08): explore further before storage: expand options and tradeoffs, starting with
detailed walkthroughs. Investigation: [RT10 collection scope](../rt10-collection-scope.md)
(designs A–J, six walkthroughs, external evidence, 14 sub-questions).

Claude, after the investigation and before the second peer pass: RT10 is three decisions:
index scope (which chunks define statistics), per-query eligibility (viewer; later time and
per-question sets), and index lifecycle/identity. Keep index scope at construction (A), and move
to an explicit index object (D) when indexes persist or need content identity (BE6, BE17);
several collections through a composite retriever that merges per-collection results (I),
matching "optimize per collection only". Per-call selection (B/C) suits per-query eligibility
filters, not index scope; decide that with BE11 and time. Fusion legs on one collection: caller's
job, documented (a check needs a protocol attribute). Snapshot vs live: stated per
implementation. Collection is selection, not authorization (not E). Unknown collection: raise once
collections are stored records (Q13).

Peer, second pass (gpt-6.1-sol, 2026-11-08, over the investigation; ran 10 focused tests and
probes on both backends, spot-checked Elastic RRF and Qdrant): keep A; do not add D's index
object or a multi-collection composite now (several-collection retrieval is outside the owner's
single-collection rule; the "several ids" remark concerns listing). Strongest alternatives: B1
(per-call selection over eagerly built indexes, no lazy cache: the research overstated B's cache
cost), D without routing, F (collection-scoped store handle). Sub-questions: unknown collection
stays empty and raising is not pre-decided (existence disclosure is a storage question); fusion
legs on one collection are the caller's stated obligation; BE11/time filters stay deferred. Most
discriminating scenario: fusion (A permits legs on different collections; probe confirmed mixed
output). Dispositions: unique defect, run identity must include access state (identical content
and viewers, different grants, different results; observed) and the selected collection
explicitly (two empty collections give equal chunk digests; observed) → added to the record and
the owner presentation; changed framing, B1 compared separately from lazy B2 → accepted;
dissent kept: Claude's D-later and composite-for-several and raise-on-unknown versus the peer's
deferring all three.

Next interfaces: dense retrieval and fusion ([DF](dense-fusion.md)), evidence formatting (RT4
remains under LQ1).

## Answered

### RT9. Retriever protocol obligations beyond the approved three

The approved `Retriever` rules are: at most `k` hits, best first, only visible sources. `BM25`
additionally orders ties by `(source_id, ordinal)`, is deterministic, raises `ValueError` for
`k < 1` and reads a snapshot. A persona integrator asked which of these a custom retriever must
meet; the retrieval page now says only the three are required. Fusion consumes ranks, and recall
trusts hit lists, so tie order can change R@k at the cutoff.

- Claude: keep the protocol at the three rules; each implementation states its own tie and
  determinism behaviour; reproducibility belongs to the benchmark runner's run identity when it
  is designed.
- Peer (gpt-6.1-sol, 2026-11-08): promote only cheap universal behaviour (the `k < 1` rule) into
  the protocol; keep the tie key and snapshot reads implementation-specific; add a separate
  benchmark requirement: same ordered results for fixed inputs, configuration, randomness and
  corpus. Note: the brief sent to the peer misstated BM25's `k < 1` behaviour as returning `[]`;
  it raises `ValueError`, so the peer's rule would be "`k < 1` raises `ValueError`".

Owner (2026-11-08): **keep as is.** Agrees with Claude.

### RT5 (answered round 8). BM25 default preset, after the corrected HippoRAG 1 facts

Owner: **(a) `HIPPORAG1`** for now (ES `standard` analyzer approximation: lowercase, no stopwords or
stemming); Claude and peer agreed. `BM25S_DEFAULT` ships; `IRCOT` waits for stemming (RT8).

### RT7 (answered round 8). Index corpus, masking and statistics scope

Owner: **(c)** global statistics over the declared corpus viewer's chunks now, leak documented,
viewer-scoped indexes later; policy "simpler version now, full privacy suite eventually". Applied:
visibility read on every call (Claude's memo dropped; the peer's per-call read is simpler).

### RT8 (answered round 8). Tokenizer

Owner: the tokenizer is part of indexing; stemming etc. later, possibly towards database-level
analysis. Applied: pattern and lowercase only; stopwords, possessives, Porter deferred.

### RT1/RT2 (answered round 7). Hit and Retriever call

`RetrievalHit(chunk, score: float | None)`, list order is rank, producer recorded by the stage.
`Retriever.__call__(query: str, /, *, viewer: Viewer, k: int) -> list[RetrievalHit]`: owner chose k
per call (peer's view) over k in `__init__` (Claude's). Fuser, reranker and oracle selector share
the output type with their own input Protocols.

### RT3 (answered round 7). Where access lives

Store-owned grants keyed by Source id; `Viewer(principals: frozenset[str])`; `"public"` is an
ordinary principal; no principals see nothing; time axes later with defined semantics.

### RT6 (answered round 7). Reads and writes under a Viewer

No existence leak; a source without grants is invisible; grants written atomically with sources,
equal repeat no-op, conflicting grants raise, no revoke yet. Owner prefers raising over `None`
here: `source(id, *, viewer)` raises the same error for missing and invisible sources (result
types fit sometimes but must always be checked). Chunk reads of an invisible parent: P6 draft.

### RT5 (answered round 7, reopened round 8). BM25 default preset

Option A exactly; other settings as presets. Reopened: its HippoRAG 1 premise was wrong (see Open).

### RT4 (answered round 6). BM25 settings

Mostly option A, under the owner policy that established baselines are named, configurable
presets and stay tunable: bm25s; default IRCoT/ES-like preset (lucene, k1 1.2, b 0.75, English
stopwords + Porter, global statistics, mask before top-k, drop zero scores); bm25s defaults with a
plain tokenizer as another preset. RT5 asks which part of A is excluded.
