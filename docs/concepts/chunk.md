# Chunk

A **`Chunk`** is a contiguous excerpt of a [source](source.md)'s text. Chunks are the units that
get indexed and retrieved, so each one carries enough information to find it again in its source:
the source's `origin` and the character offset `start`.

## Example

```python
from triplum.datatype import Chunk, Collection, Source

collection = Collection(name="Research notes")
source = Source(
    collection_id=collection.id,
    origin="notes/returns.md",
    text="Returns are accepted within 30 days. Refunds take 5 days.",
)
chunk = Chunk(
    collection_id=source.collection_id,
    source_id=source.id,
    origin=source.origin,
    ordinal=1,
    start=37,
    text="Refunds take 5 days.",
)

assert source.text[chunk.start : chunk.start + len(chunk.text)] == chunk.text
```

1. Build a `Source` as before.
2. Create a `Chunk` pointing at its source: `source_id` is the source's `id`, and
   `collection_id` and `origin` are copied from it.
3. `ordinal` is the chunk's position in the list its chunker returned for that source, counting
   from 0. Here the chunk is the second of two.
4. `start` is the offset of the excerpt in `source.text`, and `text` is the excerpt, verbatim.
5. The assertion is the relationship every chunk has to its source: slicing the source text at
   `start` gives back the chunk text.

## What it guarantees

- `start` is a Python character offset: it counts code points, not bytes, so it matches Python
  string slicing directly. It must be non-negative; a negative value fails validation.
- `text` is copied verbatim from the source text, never rewritten. Text prepared for embedding
  (descriptions, questions, context) is a separate concern; see
  [chunk preprocessing](chunk-preprocessing.md).
- `ordinal` is between 0 and 65,535, so one source yields at most 65,536 chunks.
- Chunks are immutable, like sources. The `id` is a deterministic UUIDv8 derived from
  `collection_id`, `source_id`, `ordinal`, `start` and `text`. Running the same chunker on the
  same source again gives the same IDs. The chunker itself does not enter the `id`: two chunkers
  that produce the same chunks produce the same IDs. A supplied `id` that does not match fails
  validation.
- `fingerprint()` hashes the same five fields as the `id`, recomputing on each call. See
  [Fingerprints](../infrastructure/fingerprints.md#existing-record-fingerprints) for storage and
  cache behavior.
- `Chunk` cannot check the slicing relationship itself, because it does not hold the source; the
  code that creates chunks is responsible for it.

## Reference

[`Chunk`][triplum.datatype.chunk.Chunk] in the API reference.

Next: [Datasets and the DataLoader](datasets.md), where sources come from.
