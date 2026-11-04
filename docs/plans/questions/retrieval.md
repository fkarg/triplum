# Retrieval results, Viewer and BM25 baseline

Questions use the `RT` prefix. Process: [questions index](README.md).

## Open

Round 3 peer: gpt-6.1-sol, review `a1347712184249d3a9dfb7431bd9c534`. Working frame:
[interface map](../interface-map.md).

### RT1. Retrieval hit record

`RetrievalHit(chunk: Chunk, score: float | None)`, list order is rank, producer recorded with the
stage. Claude and peer agree.

### RT2. Retriever and oracle

Retriever configured with k, called per question with the public input and Viewer. Oracle is a
privileged selector receiving evidence (Claude revised to the peer). Open: one input record versus
separate arguments.

### Round 6 (peer `95db7880fa8342b8b991f335601f11be`)

- RT1/RT2: `RetrievalHit(chunk, score | None)`; k in `__init__`; call shape one input record
  (Claude) vs `(question, /, *, viewer)` (peer).
- RT3: `Source.access` field outside the id (Claude, conflicts with insert-only writes) vs a
  store-owned `SourceAccess` snapshot keyed by Source id plus `Viewer(principals, as_of)` (peer).
  All store reads take `viewer=`.
- RT4: bm25s. Claude: k1 1.2, b 0.75, English stopwords + Porter, global statistics, mask then drop
  zero scores. Peer: k1 1.5, b 0.75, plain tokenizer, index only the viewer's eligible chunks.

### Round 7 (peer `c047f9c1bcbf400d94bf457f234e5905`)

Re-presented RT1–RT3 with producer/consumer and access context; new RT6 (read/write semantics
under a Viewer) and RT5 (which part of BM25 option A the owner excludes). RT2 divergence: k in
`__init__` (Claude) vs per call (peer).

### RT3. Viewer contract

Store reads take no Viewer today; the Retriever cannot be access-safe until they do. One `as_of`
cannot express both valid and transaction time.

## Answered

### RT4 (answered round 6). BM25 settings

Mostly option A, under the owner policy that established baselines are named, configurable
presets and stay tunable: bm25s; default IRCoT/ES-like preset (lucene, k1 1.2, b 0.75, English
stopwords + Porter, global statistics, mask before top-k, drop zero scores); bm25s defaults with a
plain tokenizer as another preset. RT5 asks which part of A is excluded.
