# Core Concepts

Each page explains one concept: what it is, a small example, and a link into the API reference.
[Decision points](concepts/decisions.md) lists every step where you choose or plug in an
implementation, with what the library provides today.

## Indexing

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

Each step is a `typing.Protocol` with one naive reference implementation; you can subclass it or
pass anything with a matching call signature. Datasets and loaders only provide and batch records.
[Indexing and retrieval](flow.md) shows how these steps fit into the larger flow.

## Retrieval

Retrieval concepts are not written yet; see [Indexing and retrieval](flow.md) for the intended
flow.
