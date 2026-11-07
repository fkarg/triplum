# Retrieval results, Viewer and BM25 baseline

Questions use the `RT` prefix. Process: [questions index](README.md).

## Open

Round 8, presented 2026-11-07. Peer: gpt-6.1-sol, `2093cf26166c43c998114f9d3709ff77`. Declarations
in the [retrieval spec](../../specs/retrieval.md) (P8).

### RT5 (reopened). BM25 default preset

Round 6 said the IRCoT/ES-like preset matched IRCoT and HippoRAG 1. Research found HippoRAG 1 used
the ES `standard` analyzer (lowercase only) on one `title\ntext` field; IRCoT used `english` on
two summed fields. Claude and peer both: default `HIPPORAG1` (k1 1.2, b 0.75, lowercase, no
stopwords or stemming), `IRCOT` (one-field approximation) and `BM25S_DEFAULT` as presets.

### RT7. Index corpus, masking and statistics scope

Claude and peer: `BM25(store, *, viewer, settings)` indexes what a declared corpus viewer sees
(term statistics over that set); each call intersects the query viewer's visible source ids with
the index before ranking; snapshot, rebuilt after writes. Divergence: Claude memoizes visible ids
per principal set, peer re-reads per query except a fixed viewer. Open sub-question: private
corpora, global statistics over the declared corpus (leaks term statistics) or viewer-scoped
indexes (one per visible corpus).

### RT8. Tokenizer ownership and fidelity

Claude and peer: a small library tokenizer described by data settings (pattern, lowercase,
possessive, stopwords, PyStemmer `porter`), bm25s for scoring only, own visible-row selection and
`(source_id, ordinal)` tie order; presets documented as approximations, no JVM.

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

### RT5 (answered round 7, reopened round 8). BM25 default preset

Option A exactly; other settings as presets. Reopened: its HippoRAG 1 premise was wrong (see Open).

### RT4 (answered round 6). BM25 settings

Mostly option A, under the owner policy that established baselines are named, configurable
presets and stay tunable: bm25s; default IRCoT/ES-like preset (lucene, k1 1.2, b 0.75, English
stopwords + Porter, global statistics, mask before top-k, drop zero scores); bm25s defaults with a
plain tokenizer as another preset. RT5 asks which part of A is excluded.
