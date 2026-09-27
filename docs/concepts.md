# Core Concepts

Each page explains one concept: what it is, a small example, and a link into the API reference.
Pages marked *planned* describe a step whose interface is not implemented yet.

## Indexing

Indexing turns input material into searchable chunks. The concepts in pipeline order:

1. [Source](concepts/source.md): identified input text.
2. [Chunk](concepts/chunk.md): an excerpt of a source, located by origin and offset.
3. [Datasets and the DataLoader](concepts/datasets.md): where records come from, and how they
   are consumed one at a time or in batches.
4. [Conversion](concepts/conversion.md) (*planned*): dataset records to sources.
5. [Chunking](concepts/chunking.md) (*planned*): sources to chunks.
6. [Chunk preprocessing](concepts/chunk-preprocessing.md) (*planned*): chunks to the text that
   gets embedded.
7. [Embedding](concepts/embedding.md) (*planned*): that text to one vector per chunk.

Steps are plain functions by default; datasets and loaders only provide and batch records.
[Indexing and retrieval](flow.md) shows how these steps fit into the larger flow.

## Retrieval

Retrieval concepts are not written yet; see [Indexing and retrieval](flow.md) for the intended
flow.
