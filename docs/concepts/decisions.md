# Decision points

Indexing is a chain of small steps, and each one is a place where you choose an implementation or
plug in your own. This page lists them in pipeline order. Each concept page explains its step in
detail.

| Step | Contract | Provided today | A custom implementation must |
| --- | --- | --- | --- |
| [Dataset](datasets.md) | [`Dataset`][triplum.utils.data.dataset.Dataset] (indexed) or [`IterableDataset`][triplum.utils.data.dataset.IterableDataset] (streaming) | [`MultiHopRAGCorpus`][triplum.datasets.multihoprag.MultiHopRAGCorpus], [`MarkdownFolder`][triplum.datasets.markdownfolder.MarkdownFolder] for local `.md` files, [`RecordDataset`][triplum.utils.data.dataset.RecordDataset] for in-memory records | implement `__len__`/`__getitem__` or `__iter__`, plus `fingerprint()`: equal fingerprints promise the same records in the same order, and computing it must not consume the data |
| [Loader batching](datasets.md) | [`DataLoader`][triplum.utils.data.loader.DataLoader] arguments `batch_size`, `collate_fn` | `DataLoader` | `collate_fn` receives one list of records and returns the batch to yield (for example a table); converting records to sources is not its job |
| [Conversion](conversion.md) | [`Converter[A]`][triplum.steps.conversion.Converter]: item → `list[Source]` | [`Utf8File`][triplum.steps.conversion.Utf8File] | return zero or more sources for one item, each with an `origin` identifying its text |
| [Chunking](chunking.md) | [`Chunker`][triplum.steps.chunking.Chunker]: `Source` → `list[Chunk]` | [`FixedSize`][triplum.steps.chunking.FixedSize] | keep the source's `origin`; each chunk's `start` and `text` are an exact slice of the source text |
| [Embedding text](chunk-preprocessing.md) | [`EmbeddingText`][triplum.steps.chunk_preprocessing.EmbeddingText]: `Chunk` → `str` | [`OriginalText`][triplum.steps.chunk_preprocessing.OriginalText] | return one string per chunk, without modifying the chunk |
| [Embedding](embedding.md) | [`Embedder`][triplum.steps.embedding.Embedder]: `list[str]` → [`Vectors`][triplum.steps.embedding.Vectors], plus `dimensions` | [`ZeroEmbedder`][triplum.steps.embedding.ZeroEmbedder] (placeholder, all zeros) | return a `float32` matrix of shape `(len(texts), dimensions)`, rows in input order |
| [Store](../infrastructure/store.md) | [`RecordStore`][triplum.store.protocols.RecordStore]: add and read sources and chunks by `id` | [`MemoryStore`][triplum.store.memory.MemoryStore], [`SQLAlchemyStore`][triplum.store.sql.generic.SQLAlchemyStore] (SQLite by default) | replace a record whose `id` is already stored, reject a chunk whose source is not stored, return a source's chunks ordered by `start`; storing and searching vectors is not built yet |

Datasets whose records are already sources, such as the MultiHop-RAG corpus, skip conversion.

## How the pieces fit

- **Contracts are Protocols.** Each step declares a `typing.Protocol` with an abstract
  `__call__`. triplum's own implementations subclass the protocol, so the type checker verifies
  them where they are defined, and a subclass missing `__call__` cannot be instantiated.
- **Fitting without inheriting.** Third-party classes and plain functions fit a protocol
  structurally when their signature matches. A plain function fits the call-only steps
  (conversion, chunking, embedding text), but not `Embedder`, which also needs `dimensions`.
  The protocols are not `runtime_checkable`: an `isinstance` check against a call-only protocol
  could only confirm that `__call__` exists, so the type checker does this job instead.
- **Configuration lives in `__init__`.** Settings such as `FixedSize(20)` or
  `ZeroEmbedder(dimensions=4)` are passed once when creating the step, because some steps hold
  resources such as models or network and GPU clients.
- **Steps handle one item.** A converter takes one item, a chunker one source, an embedding text
  step one chunk, an embedder one batch. Iterating over a dataset or `DataLoader` and feeding the
  steps is the pipeline's job. Loaders only batch; they never convert.
- **Type aliases describe data, not behaviour.** `Vectors` names the shape of an embedding
  result; behaviour is always a protocol.

## Reference

The generated API reference lists every module under `triplum.steps`, starting with
[`triplum.steps.conversion`][triplum.steps.conversion].

Next: [Source](source.md).
