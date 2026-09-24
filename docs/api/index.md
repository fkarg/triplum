# API reference

Use [Learn](../guide/index.md) for small examples. This section lists the importable interfaces
and their signatures from source. A `done` status describes the current implementation, not a
promise that the interface has finished evolving; [Flow](../flow.md) records what a run does now.

## Data and execution

| Module | Status | Key symbols | Contract |
|---|---|---|---|
| [`triplum.data`](data.md) | done | `Document`, `Segment`, `CorpusBatch`, `Viewer`, canonical schemas | Records describe source text; frames cross the store boundary; reads take a viewer. |
| [`triplum.utils.data`](utils-data.md) | done | `Dataset`, `IterableDataset`, `RecordDataset`, `DataLoader` | Sources own records and fingerprints; loaders choose how to consume them. |
| [`triplum.datasets`](datasets.md) | done | `registry.load`, `registry.verify`, `Pinned`, `InlineCorpus`, `corpus_batch` | Built-in sources remain lazy until read; collators project records to frames. |
| [`triplum.stage`](stage.md) | done | `stage`, `Stage`, `Run`, `Artifact`, `Stream` | Calls identify results from inputs and record code provenance for reuse. |
| [`triplum.cache`](cache.md) | done | `Cache`, `content_key` | Adapter calls use content-addressed disk entries. |
| `triplum.settings` | done | `Settings` | Runtime paths and mirrors configure access, not data identity. |

## Processing and search

| Module | Status | Key symbols | Contract |
|---|---|---|---|
| [`triplum.ingest`](ingest.md) | done | `FolderCorpus`, `FolderQuestions`, `document`, `entry` | Local files become source records. |
| [`triplum.extract`](extract.md) | baseline | `Extractor`, `Extraction`, `extract`, `resolve`, `RulesExtractor` | Extractors return claims; the stages ground them into graph frames. |
| [`triplum.store`](store.md) | done | `Store`, `Capabilities`, `SqliteStore` | Writes accept frames; search and graph reads filter for a `Viewer`. |
| [`triplum.retrieve`](retrieve.md) | done | `bm25`, `dense`, `rrf`, `hybrid`, `oracle`, `PIPELINES` | Stages take frames; named pipelines compose them as functions. |
| [`triplum.generate`](generate.md) | done | `read`, `build_messages` | The reader turns retrieved passages into an answer. |

## Models and experiments

| Module | Status | Key symbols | Contract |
|---|---|---|---|
| [`triplum.llm`](llm.md) | done | `LLM`, `Message`, `Completion`, `CachedLLM` | Pipeline code calls one completion protocol. |
| [`triplum.embed`](embed.md) | done | `EmbeddingSpec`, `Embedder`, `CachedEmbedder` | The spec identifies the embedding used in an index and run. |
| [`triplum.rerank`](rerank.md) | done | `RerankSpec`, `Reranker`, `CachedReranker` | Rerankers rescore candidate passages. |
| [`triplum.eval`](eval.md) | done | `Question`, `Triple`, `metrics`, `score` | Scores answer and extraction results. |
| [`triplum.bench`](bench.md) | done | `Benchmark`, `RunConfig`, `run_benchmark`, `RunStore`, `summary` | The runner composes sources and pipelines, then records results by identity. |

## Contracts across modules

- A source's `fingerprint()` identifies its **ordered records** before a read; benchmark runs use
  those identities. See [sources](../guide/sources.md) and [benchmark caching](../benchmarking.md).
- Collators turn records into canonical frames at processing and store boundaries. See
  [corpus frames](../guide/frames.md).
- Store reads take a `Viewer` and filter before ranking. See
  [viewers](../guide/viewers.md) and [reading from a store](../guide/store.md).
- The benchmark runner calls importable pipeline functions. See
  [run a benchmark](../guide/benchmark.md) and [benchmark runs](../flow.md).
