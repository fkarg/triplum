# Embedding

!!! note "Status: planned"
    Embedding is not implemented yet. The module `triplum.steps.embedding` is a placeholder, and
    no embedder interface has been approved.

**Embedding** turns the text prepared for a chunk into a vector, so that chunks can be found by
similarity to a query's vector.

## Intended shape

```text
text to embed  ──embedding──▶  vector
```

- Input: the text produced by [chunk preprocessing](chunk-preprocessing.md).
- Output: one vector per chunk for the chosen embedding configuration (model and settings).

Benchmarks hold the embedding configuration fixed across the pipelines they compare, so that
differences in results come from the pipelines, not the embedder. Encoding a user's question at
retrieval time is a separate use of the same model and is not part of indexing.
