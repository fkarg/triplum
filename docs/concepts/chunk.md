# Chunk

A **`Chunk`** is a contiguous excerpt of a [source](source.md)'s text. Chunks are the units that
get indexed and retrieved, so each one carries enough information to find it again in its source:
the source's `origin` and the character offset `start`.

## Example

```python
from pathlib import Path

from triplum.datatype import Chunk, Source

source = Source(
    origin=Path("notes/returns.md"),
    text="Returns are accepted within 30 days. Refunds take 5 days.",
)
chunk = Chunk(origin=source.origin, start=37, text="Refunds take 5 days.")

assert source.text[chunk.start : chunk.start + len(chunk.text)] == chunk.text
```

1. Build a `Source` as before.
2. Create a `Chunk` with the same `origin` as its source.
3. `start` is the offset of the excerpt in `source.text`, and `text` is the excerpt, verbatim.
4. The assertion is the relationship every chunk has to its source: slicing the source text at
   `start` gives back the chunk text.

## What it guarantees

- `start` is a Python character offset: it counts code points, not bytes, so it matches Python
  string slicing directly. It must be non-negative; a negative value fails validation.
- `text` is copied verbatim from the source text, never rewritten. Text prepared for embedding
  (descriptions, questions, context) is a separate concern; see
  [chunk preprocessing](chunk-preprocessing.md).
- Like `Source`, `Chunk` is a plain Pydantic model. It cannot check the slicing relationship
  itself, because it does not hold the source; the code that creates chunks is responsible for it.

## Reference

[`Chunk`][triplum.datatype.chunk.Chunk] in the API reference.

Next: [Datasets and the DataLoader](datasets.md), where sources come from.
