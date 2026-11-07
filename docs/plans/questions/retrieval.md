# Retrieval results, Viewer and BM25 baseline

Questions use the `RT` prefix. Process: [questions index](README.md).

## Open

None. Next interfaces: dense retrieval and fusion ([DF](dense-fusion.md)), evidence formatting (RT4
remains under LQ1).

## Answered

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
