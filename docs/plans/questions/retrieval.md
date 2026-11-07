# Retrieval results, Viewer and BM25 baseline

Questions use the `RT` prefix. Process: [questions index](README.md).

## Open

None. Next: P6/P7 declarations. Round 7 peer: gpt-6.1-sol, `c047f9c1bcbf400d94bf457f234e5905`.

## Answered

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

### RT5 (answered round 7). BM25 default preset

Option A exactly; other settings as presets.

### RT4 (answered round 6). BM25 settings

Mostly option A, under the owner policy that established baselines are named, configurable
presets and stay tunable: bm25s; default IRCoT/ES-like preset (lucene, k1 1.2, b 0.75, English
stopwords + Porter, global statistics, mask before top-k, drop zero scores); bm25s defaults with a
plain tokenizer as another preset. RT5 asks which part of A is excluded.
