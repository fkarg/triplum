# Source

A **`Source`** is identified input text: the full text of one document, webpage or article,
together with an `origin` that says where it came from. It is what chunking consumes and what
every chunk points back to.

Upstream steps (reading files, extracting HTML, OCR) exist to produce sources. Everything after
them works on plain text and never needs to know the original file format.

## Example

```python
from pathlib import Path

from triplum.datatype import Source

source = Source(
    origin=Path("notes/returns.md"),
    text="Returns are accepted within 30 days. Refunds take 5 days.",
)
print(source.origin, len(source.text))  # notes/returns.md 57
```

1. Import `Source` from `triplum.datatype`.
2. Set `origin` to something that identifies the text. Here it is a file path; a URL or another
   string identifier works too (`Path | str`).
3. Set `text` to the full text, already decoded. The source holds it in memory.

## What it guarantees

- `Source` is a plain [Pydantic](https://docs.pydantic.dev/) model, so construction validates the
  field types. It has no storage behavior of its own.
- `text` may be empty; chunking then produces no chunks.
- Every source gets an `id` (a time-ordered UUIDv7) when it is created. Chunks refer back to their
  source through `source_id`, which is that `id`. Creating a second `Source` with the same text
  gives a different `id`.
- `fingerprint` is a hash of `origin` and `text`: two sources with the same content have the same
  fingerprint, whatever their `id`. See [Fingerprints](../infrastructure/fingerprints.md).
- `origin` is for people and for matching back to the original document; it is not checked for
  uniqueness.

## Reference

[`Source`][triplum.datatype.source.Source] in the API reference.

Next: [Chunk](chunk.md), an excerpt of a source.
