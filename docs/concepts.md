# Core Concepts

Follow these pages for small examples in pipeline order. [Decision points](concepts/decisions.md)
compares the available implementations and explains how to plug in your own.

## Indexing

Start with a [Collection](concepts/collection.md) to identify the corpus scope. Its baseline
record exists; source membership and scope enforcement are not implemented yet.

Indexing turns input material into searchable chunks. The concepts in pipeline order:

1. [Source](concepts/source.md): identified input text.
2. [Chunk](concepts/chunk.md): an excerpt of a source, located by origin and offset.
3. [Datasets and the DataLoader](concepts/datasets.md): where records come from, and how they
   are consumed one at a time or in batches.
4. [Conversion](concepts/conversion.md): dataset records to sources.
5. [Chunking](concepts/chunking.md): sources to chunks.
6. [Chunk preprocessing](concepts/chunk-preprocessing.md): chunks to the text that gets
   embedded.
7. [Embedding](concepts/embedding.md): that text to one vector per chunk.

[Indexing and retrieval](flow.md) shows the larger flow; [Decision points](concepts/decisions.md)
explains the shared Protocol and configuration conventions.

## Retrieval

Retrieval concepts are not written yet; see [Indexing and retrieval](flow.md) for the intended
flow.
