# Core Concepts

Follow these pages for small examples in pipeline order. [Decision points](concepts/decisions.md)
compares the available implementations and explains how to plug in your own.

## Indexing

The examples work directly with Sources. A [Collection](concepts/collection.md) identifies a
corpus scope: listing sources and BM25 search take a collection id, but collection records are
not stored yet.

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

## Retrieval and evaluation

1. [Benchmark inputs](concepts/benchmark-inputs.md): a benchmark's corpus and its questions,
   with the answers and gold evidence that only evaluation reads.
2. [Retrieval](concepts/retrieval.md): the chunks a viewer may read that best answer a query,
   ranked by BM25.
3. [Store-managed text search](concepts/text-search.md): build and search a collection snapshot
   through the store, using BM25 or native SQLite FTS5.
4. [Retrieval recall](concepts/recall.md): how much of a question's gold evidence the top `k`
   hits contain.

Answer generation and answer scoring are not implemented yet; see
[Indexing and retrieval](flow.md) for the intended flow.
