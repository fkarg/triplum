# Chunk preprocessing

!!! note "Status: planned"
    Chunk preprocessing is not implemented yet. The module `triplum.steps.chunk_preprocessing`
    is a placeholder, and no interface has been decided.

**Chunk preprocessing** decides what text represents a [chunk](chunk.md) when it is embedded.
The simplest choice is the chunk text unchanged. Richer choices add a generated description,
questions the chunk answers, or context from its source.

## Intended shape

Two kinds of operation are planned:

```text
Chunk  ──▶  Chunk                  (e.g. filter or adjust chunks)
Chunk  ──▶  text to embed          (e.g. chunk text, plus description or questions)
```

A chunk may have several text representations, but it gets **one vector per embedding
configuration**. Generated descriptions and questions feed into that one vector; they are not
indexed as separate vectors. How several representations combine into the embedding input is
undecided.

```text
Original:    Returns are accepted within 30 days of purchase.
Description: This shop's returns policy.
Question:    How long do I have to return a purchase?
                         ↓ preparation and embedding
                    One chunk vector
```

The chunk's own `text` stays verbatim. Generated text must stay distinguishable from the original
evidence; its record type is still open.

Next: [Embedding](embedding.md).
