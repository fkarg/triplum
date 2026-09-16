# Modules and interfaces

Snapshot 2026-09-16. Every module below is importable on its own; the benchmark runner is one
composition of them, not a framework they depend on. The pages in this section are generated
from the source signatures, so they are exact as of the build. Where a docstring is missing the
signature is still shown.

## Module map

| module | status | key symbols | role |
|---|---|---|---|
| `triplum.data.schema` | done | `DOCUMENTS`, `DOCUMENT_GRANTS`, `CHUNKS`, `ENTITIES`, `FACTS`, `FACT_SUPPORT`, `MENTIONS`, `chunk_embeddings(dims)`, `now_us()` | the eight canonical Arrow schemas, owned by the Rust core |
| `triplum.data.viewer` | done | `Viewer`, `Viewer.of(*principals)` | who is asking and as of when; every store read takes one |
| `triplum.cache` | done | `Cache`, `content_key`, `canonical_json`, `default_root` | content-addressed disk cache shared by all adapters |
| `triplum.llm` | done | `LLM`, `Message`, `GenParams`, `Completion`, `CachedLLM`, `OpenAICompatLLM`, `CliLLM`, `FakeLLM` | one completion protocol; adapters, never provider SDKs, in pipeline code |
| `triplum.embed` | done | `EmbeddingSpec`, `Embedder`, `CachedEmbedder`, sentence-transformers, fastembed, OpenAI-compatible and fake adapters | embedding identity and adapters |
| `triplum.rerank` | done | `RerankSpec`, `Reranker`, `CachedReranker`, cross-encoder and fake adapters | pointwise reranking |
| `triplum.store` | chunk side done | `Store`, `Capabilities`, `SqliteStore` | viewer-filtered BM25 and vector search over chunks; graph tables exist but are unused |
| `triplum.retrieve.stages` | done | `none`, `oracle`, `bm25`, `dense`, `hybrid`, `rrf` | retrieval stages, frames in and out |
| `triplum.generate.reader` | done | `read`, `build_messages`, `PROMPT_HASH` | the one reader prompt |
| `triplum.eval` | done | `metrics.*`, `judge.judge_correct`, `datasets.hipporag.load` | metrics, judge, datasets under the HippoRAG protocol |
| `triplum.bench` | done | `RunConfig`, `run_benchmark`, `RunStore`, `summary`, `inspect_run`, `diff_runs`, `tail_run`, `code_hash` | run identity, caching, recording, reporting |
| `triplum.bench.cli` | done | `app`, `bench`, `data` | dataset status and read-only recent-run overview, state explanations and generated subcommand help |
| `triplum.ingest` | planned (2a) | chunking | hierarchical chunking for the graph pipelines |
| `triplum.extract` | planned (2a, 2b) | entity and fact extraction | fills `entities`, `facts`, `fact_support`, `mentions` |
| `triplum.store` graph side | planned (2a, 2c) | k-hop, PPR, pattern queries | graph kernels on the viewer's projection; Neo4j arm |

The contracts that hold across modules:

- **Frames in, frames out.** A stage takes Polars frames in the canonical column layout and
  returns one; no module defines its own row model.
- **Viewer everywhere.** Any read that could leak data takes a `Viewer`; the store filters
  inside its indexes before ranking.
- **Identity is a spec.** `EmbeddingSpec`, `RerankSpec`, `LLMConfig` and `PipelineConfig` are
  frozen dataclasses whose hashes name cache entries, index tables and runs.
- **Cache wrappers, not cache logic.** `CachedLLM`, `CachedEmbedder` and `CachedReranker` wrap
  any adapter; the key is the full effective request.

## Composing by hand

The same pieces the runner uses, without the runner (this snippet runs against the committed
fixture with the fake embedder and fake reader):

```python
import tempfile
from pathlib import Path

from triplum.data.viewer import Viewer
from triplum.embed.fake import FakeEmbedder
from triplum.eval import metrics
from triplum.eval.datasets import hipporag as hr
from triplum.generate.reader import read
from triplum.llm.fake import FakeLLM
from triplum.llm.protocol import DEFAULT_PARAMS
from triplum.retrieve import stages
from triplum.store.sqlite.store import SqliteStore

ds = hr.load_fixture("musique", n=5)     # questions, documents, grants, chunks as Polars frames
store = SqliteStore(Path(tempfile.mkdtemp()) / "demo.sqlite")
store.put_documents(ds.documents, ds.grants)
store.put_chunks(ds.chunks)

embedder = FakeEmbedder(dims=64)         # any Embedder; wrap a real one in CachedEmbedder
store.put_embeddings(
    embedder.spec, ds.chunks["id"].to_list(), embedder.embed_passages(ds.chunks["text"].to_list())
)

viewer = Viewer.of("public")             # every read is scoped to a viewer
hits = stages.dense(ds.questions, store, embedder, k=5, viewer=viewer)
answers = read(ds.questions, hits, store, FakeLLM(), viewer, DEFAULT_PARAMS)

q = ds.questions.row(0, named=True)
ids = hits.filter(hits["question_id"] == q["id"]).sort("rank")["chunk_id"].to_list()
print(answers.columns)                   # question_id, answer, tokens, cached, latency_s, n_passages
print(metrics.recall_at_k(q["gold_chunk_ids"], ids, 5))
```

Swap `FakeEmbedder` for `triplum.embed.sentence_transformers.from_model(...)` inside a
`CachedEmbedder`, and `FakeLLM` for `OpenAICompatLLM` inside a `CachedLLM`, and the snippet is
the dense baseline. `bench.factories` does exactly that from the frozen configs.
