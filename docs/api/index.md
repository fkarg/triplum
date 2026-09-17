# Modules and interfaces

Snapshot 2026-09-17. Every module below is importable on its own; the benchmark runner is one
composition of them, not a framework they depend on. The pages in this section are generated
from the source signatures, so they are exact as of the build. Where a docstring is missing the
signature is still shown.

## Module map

| module | status | key symbols | role |
|---|---|---|---|
| `triplum.utils.data` | done | `Dataset`, `IterableDataset`, `Source`, `Take`, `RecordDataset`, `DataLoader` | author-defined records, indexed or streaming access, prefix selection, in-memory records, lazy batching and custom collation |
| `triplum.settings` | done | `Settings` | data root, cache root and URL mirrors from `TRIPLUM_*`; never part of an identity |
| `triplum.datasets` | done | `registry.load`, `registry.verify`, `base.Pinned`, `base.ListSource`, `base.InlineCorpus`, `base.Entry`, `files.Files`, `collate.*`, `fixtures.*`, `FrameDataset` | lazy built-in sources over pinned files (fetched on first use, fingerprinted without reading), the catalog, collators onto the canonical frames, committed fixtures |
| `triplum.data.corpus` | done | `Document`, `Segment`, `content_id`, `chunk_id`, `CorpusBatch` | the corpus record with its source-declared id and segments; the canonical three-frame batch it projects onto |
| `triplum.bench.inputs` | done | `Benchmark`, `PreparedBenchmark`, `materialize`, `check` | compose independent lazy sources; the explicit eager bridge for existing algorithms, with the cross-source integrity checks and identities from the sources' fingerprints |
| `triplum.stage` | done | `stage`, `Stage`, `Run`, `active`, `Artifact`, `Stream`, `Manifest`, `derive` | a plain function with a data key from its arguments, a trace-discovered code manifest, a published artifact and an invocation row; lookup by key, validity along the lineage; live streams tee to parquet |
| `triplum.data.schema` | done | `DOCUMENTS`, `DOCUMENT_GRANTS`, `CHUNKS`, `ENTITIES`, `FACTS`, `FACT_SUPPORT`, `MENTIONS`, `chunk_embeddings(dims)`, `now_us()` | the eight canonical Arrow schemas, owned by the Rust core |
| `triplum.data.viewer` | done | `Viewer`, `Viewer.of(*principals)` | who is asking and as of when; every store read takes one |
| `triplum.cache` | done | `Cache`, `content_key`, `canonical_json`, `default_root` | content-addressed disk cache shared by all adapters |
| `triplum.llm` | done | `LLM`, `Message`, `GenParams`, `Completion`, `CachedLLM`, `OpenAICompatLLM`, `CliLLM`, `FakeLLM` | one completion protocol; adapters, never provider SDKs, in pipeline code; every adapter declares `seed_sensitive`, and the perturbing fake answers per seed for replicate tests |
| `triplum.embed` | done | `EmbeddingSpec`, `Embedder`, `CachedEmbedder`, sentence-transformers, fastembed, OpenAI-compatible and fake adapters | embedding identity and adapters |
| `triplum.rerank` | done | `RerankSpec`, `Reranker`, `CachedReranker`, cross-encoder and fake adapters | pointwise reranking |
| `triplum.store` | done | `Store`, `Capabilities`, `SqliteStore`; graph side `put_graph`, `facts`, `mentions`, `neighbours` | viewer-filtered BM25 and vector search over chunks; facts visible only through a fully visible support group and both as-of instants; k-hop over visible `same_as` |
| `triplum.retrieve.pipelines` | done | `PIPELINES`, `NAMES`, `get`, `closed_book`, `bm25`, `dense`, `rrf`, `hybrid`, `oracle` | named compositions of the stages with defaults; the one pipeline list the runner, CLI and fingerprint read |
| `triplum.retrieve.stages` | done | `none`, `oracle`, `bm25`, `dense`, `fusion`, `hybrid`, `rrf` | retrieval stages, frames in and out |
| `triplum.generate.reader` | done | `read`, `build_messages`, `PROMPT_HASH` | the one reader prompt |
| `triplum.eval` | done | `Question`, `Triple`, `GoldMappingError`, `metrics.*`, `triples.score`, `judge.judge_correct` | evaluation records and schemas, QA metrics, intrinsic triple metrics (exact and partial, one-to-one), judge |
| `triplum.bench` | done | `RunConfig`, `run_benchmark`, `run_experiment`, `ExtractConfig`, `run_extraction`, `stages.*`, `RunStore`, `summary`, `extraction_summary`, `variance`, `format_summary`, `inspect_run`, `diff_runs`, `tail_run` | the pipeline as stages composed under a `Run`; identity from source fingerprints before any read, stored runs matched by validating manifests, replicates under derived seeds with the variance report; `RunStore` owns its connection (context manager) and every write |
| `triplum.bench.cli` | done | `app`, `bench`, `data` | dataset status, fetch and verify, recent-run overview, `bench extract`, finite-choice resolution and interactive drill-down |
| `triplum.bench.selection` | done | `resolve`, `adapter`, `SelectionGroup` | shared exact/prefix/fuzzy CLI selection, terminal-only prompts, canonical values and stderr diagnostics |
| `triplum.bench.bench_view` | done | `print_overview`, `print_summary`, `print_inspect`, `print_diff`, `print_tail` | width-aware benchmark projections, literal values and terminal-aware colors; no data access |
| `triplum.bench.data_view` | done | `print_overview` | width-aware dataset table, colored status summary and fetch hints; no data access |
| `triplum.ingest.files` | done | `FolderCorpus`, `FolderQuestions`, `document`, `chunk`, `entry` | a folder of PDF, Word, Markdown and text files as a streamed corpus with portable identity from file bytes, optional `questions.jsonl`; a directory path is accepted wherever a dataset name is |
| `triplum.extract` | done (baseline) | `Extractor`, `ExtractorSpec`, `ResolverSpec`, `Extraction`, `extract`, `resolve`, `RulesExtractor`, `SmallModelExtractor`, `CachedExtractor` | an extractor returns spans and claims; `extract` grounds them into the four graph frames with document-scoped entity ids; `resolve` adds supported `same_as` facts; `rules` (spaCy) and `small_model` (GLiNER + GLiREL) behind one protocol |
| `triplum.ingest` chunking | planned (2a) | hierarchical chunking | replaces paragraph packing for the graph pipelines |
| `triplum.store` graph kernels | planned (2a, 2c) | PPR, pattern queries | beyond k-hop; Neo4j arm |
| `triplum.retrieve` graph pipelines | planned (2a) | graph-augmented retrieval | the next spec; `neighbours` exists so it can start |

The contracts that hold across modules:

- **Records at the source, frames at the stage.** A source yields `Document`, `Question` or
  `Triple` records and identifies itself without reading; a collator projects them onto the
  canonical frames, and a stage takes those frames and returns one. The consumer chooses the
  batch size.
- **Viewer everywhere.** Any read that could leak data takes a `Viewer`; the store filters
  inside its indexes before ranking.
- **Identity is a spec.** `EmbeddingSpec` and `RerankSpec` are frozen dataclasses, `LLMConfig`
  and `PipelineConfig` frozen pydantic models; their hashes name cache entries, index tables
  and runs; a dataset's
  `fingerprint()` names its corpus and evaluation identities the same way.
  A stage's artifact is addressed by a data key over those identities and validated by the
  manifest of the code that produced it and its inputs, so a code edit reruns exactly the
  stages that executed it.
- **Pipelines are functions.** A named pipeline in `retrieve.pipelines` is a composition of
  stages with defaults; the runner calls the same function a notebook would.
- **Extractors produce claims, not facts.** An `Extractor` returns spans and every claim it
  considered with a status; `extract.stages.extract` is the one place entity ids, facts and
  support groups are made, so extractors never disagree on identity.
- **Cache wrappers, not cache logic.** `CachedLLM`, `CachedEmbedder` and `CachedReranker` wrap
  any adapter; the key is the full effective request.

## Composing by hand

The same pieces the runner uses, without the runner (this snippet runs against the committed
fixture with the fake embedder and fake reader):

```python
import tempfile
from pathlib import Path

from triplum.bench.inputs import materialize
from triplum.data.viewer import Viewer
from triplum.embed.fake import FakeEmbedder
from triplum.eval import metrics
from triplum.datasets import registry as datasets
from triplum.generate.reader import read
from triplum.llm.fake import FakeLLM
from triplum.llm.protocol import DEFAULT_PARAMS
from triplum.retrieve import stages
from triplum.store.sqlite.store import SqliteStore

ds = materialize(datasets.load_fixture("musique", n=5))
assert ds.qa is not None
store = SqliteStore(Path(tempfile.mkdtemp()) / "demo.sqlite")
store.put_documents(ds.corpus.documents, ds.corpus.grants)
store.put_chunks(ds.corpus.chunks)

embedder = FakeEmbedder(dims=64)  # any Embedder; wrap a real one in CachedEmbedder
store.put_embeddings(
    embedder.spec,
    ds.corpus.chunks["id"].to_list(),
    embedder.embed_passages(ds.corpus.chunks["text"].to_list()),
)

viewer = Viewer.of("public")  # every read is scoped to a viewer
hits = stages.dense(ds.qa, store, embedder, k=5, viewer=viewer)
answers = read(ds.qa, hits, store, FakeLLM(), viewer, DEFAULT_PARAMS)

q = ds.qa.row(0, named=True)
ids = hits.filter(hits["question_id"] == q["id"]).sort("rank")["chunk_id"].to_list()
print(answers.columns)  # question_id, answer, tokens, cached, latency_s, n_chunks
print(metrics.recall_at_k(q["gold_chunk_ids"], ids, 5))
```

Swap `FakeEmbedder` for `triplum.embed.sentence_transformers.from_model(...)` inside a
`CachedEmbedder`, and `FakeLLM` for `OpenAICompatLLM` inside a `CachedLLM`, and the snippet is
the dense baseline. `bench.factories` does exactly that from the frozen configs.
