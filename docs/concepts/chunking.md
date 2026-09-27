# Chunking

!!! note "Status: planned"
    Chunking has no public interface yet. The module `triplum.steps.chunking` is a placeholder.
    The only working code that chunks is a prototype, described below; it is not an approved API.

**Chunking** splits a [source](source.md) into [chunks](chunk.md): the pieces that will be
indexed and retrieved. Choosing the pieces is a retrieval decision. Keeping the whole text as one
chunk is valid; so are fixed-size pieces, overlapping pieces, or pieces that follow sections.

## Intended shape

```text
Source  ──chunking──▶  Chunk, Chunk, ...
```

- Input: one `Source`.
- Output: zero or more `Chunk`s with the source's `origin`, each satisfying
  `source.text[chunk.start : chunk.start + len(chunk.text)] == chunk.text`.
- An empty source produces no chunks.

## Sketch: fixed-size slices

The simplest chunker cuts the text every `n` characters. This is what the indexing prototype in
`triplum.steps.indexing` does internally. It runs, but it is a sketch, not a triplum function:

```python
from triplum.datatype import Chunk, Source

source = Source(
    origin="notes/returns.md",
    text="Returns are accepted within 30 days. Refunds take 5 days.",
)
chunks = [
    Chunk(origin=source.origin, start=start, text=source.text[start : start + 20])
    for start in range(0, len(source.text), 20)
]
# starts 0, 20, 40: 'Returns are accepted', ' within 30 days. Ref', 'unds take 5 days.'
```

1. Step through the text in increments of 20 characters.
2. For each step, slice the text and record the offset as `start`.
3. Every chunk keeps the source's `origin`, so it can be traced back.

This ignores words, sentences and structure, which is why it is only a baseline. Hierarchical
chunking (sections containing passages) and how containment is represented are still open.

Next: [Chunk preprocessing](chunk-preprocessing.md).
