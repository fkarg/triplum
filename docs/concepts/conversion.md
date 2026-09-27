# Conversion

!!! note "Status: planned"
    Conversion is not implemented yet. The module `triplum.steps.conversion` exists but contains
    no functions, and no interface has been decided. This page describes the intended role only.

**Conversion** turns a dataset's records into [sources](source.md). A dataset may yield file
paths, raw bytes, HTML pages or scanned images; chunking only understands `Source`. Conversion is
the step in between: reading and decoding a file, extracting text from HTML, or running OCR.

## Intended shape

```text
record of some type A  ──conversion──▶  Source(origin=..., text=...)
```

- Input: one record from a dataset, of whatever type that dataset yields.
- Output: a `Source` whose `origin` identifies the record and whose `text` is the extracted text.

Datasets whose records are already sources skip this step. The
[MultiHop-RAG corpus](datasets.md) is one: its records are sources.

Steps are intended to be plain functions by default, so a converter would be any function from a
record to a `Source`. Its exact form, and whether one record may produce several sources, is
still open.

Next: [Chunking](chunking.md).
