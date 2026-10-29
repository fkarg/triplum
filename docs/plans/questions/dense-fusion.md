# Dense retrieval and fusion

Questions use the `DF` prefix. Process: [questions index](README.md).

## Open

### DF1. Real embedder and query/passage encoding

`ZeroEmbedder` is a placeholder; `Embedder` has no query/passage distinction, and similarity,
normalization, truncation and batching semantics are open (see the embedding spec).

### DF2. Vector storage and search

No vector index or store capability exists. Needs Viewer-aware pre-filtering like the text index.

### DF3. Fusion

Fusion of several retrievers' rankings (RRF, weighted) as a block over retrieval hits.

## Answered
