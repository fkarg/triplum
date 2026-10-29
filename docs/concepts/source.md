# Source

A **`Source`** is identified input text: the full text of one document, webpage or article,
together with an `origin` that says where it came from. It is what chunking consumes and what
every chunk points back to.

Upstream steps (reading files, extracting HTML, OCR) exist to produce sources. Everything after
them works on plain text and never needs to know the original file format.

## Example

```python
from triplum.datatype import Collection, Source

collection = Collection(name="Research notes")
source = Source(
    collection_id=collection.id,
    origin="notes/returns.md",
    text="Returns are accepted within 30 days. Refunds take 5 days.",
)
print(source.origin, len(source.text))  # notes/returns.md 57
print(source.id.version)  # 8
```

1. Import `Source` from `triplum.datatype`.
2. Set `collection_id` to the `id` of the [collection](collection.md) the source belongs to.
3. Set `origin` to something that identifies the text. Here it is a file path; a URL or another
   identifier works too. It is always a string.
4. Set `text` to the full text, already decoded. The source holds it in memory.

## What it guarantees

- `Source` is a [Pydantic](https://docs.pydantic.dev/) model, so construction validates the
  field types. It has no storage behavior of its own.
- Sources are immutable: assigning to a field raises a validation error. To change the text,
  create a new `Source`.
- `text` may be empty; chunking then produces no chunks.
- The `id` is a deterministic UUIDv8 derived from `collection_id`, `origin` and `text`. Creating
  the same source again gives the same `id`; changing any of the three gives a different one, and
  changing the text back gives the original `id` again. IDs repeat across program runs only
  when the same collection `id` is reused: a new `Collection(name=...)` has a fresh `id`. Supplying an `id` that does not match
  these fields fails validation. Chunks refer back to their source through `source_id`, which is
  that `id`.
- `origin` and `text` enter the `id` exactly as given: `"notes/a.md"` and `"./notes/a.md"` give
  different IDs. Normalize them before creating the source if they should match.
- `fingerprint()` hashes the same three fields as the `id`, recomputing on each call. See
  [Fingerprints](../infrastructure/fingerprints.md#existing-record-fingerprints) for storage and
  cache behavior.
- `origin` is for people and for matching back to the original document; it is not checked for
  uniqueness.

## Reference

[`Source`][triplum.datatype.source.Source] in the API reference.

Next: [Chunk](chunk.md), an excerpt of a source.
