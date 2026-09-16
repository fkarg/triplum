# Spec: benchmark harness, baselines and embedding sweep (sub-project 2, part 1)

Date: 2026-09-16. Status: draft for review. Parent: `docs/research/design.md`. Protocol source:
`docs/research/benchmarks-multihop-qa.md`. Storage source: `docs/research/storage-sqlite.md`.

## Goal

A working benchmark harness that reports numbers for the non-graph baselines on the three multi-hop
QA datasets, with the embedder as a first-class sweep dimension. When this is done we can answer:
"what does dense retrieval score under the generation-2 protocol with embedder X, and how far are
BM25, hybrid-with-rerank, closed-book and oracle from it?" The graph pipelines (2a), construction
variants (2b) and the Neo4j arm (2c) each get their own spec on top of this one.

## Scope

In:
1. Repository scaffold: uv-managed Python package `triplum` under `python/`, Cargo workspace under
   `crates/` with `triplum-core` (Arrow schemas, time and sentinel constants) and `triplum-py`
   (PyO3, maturin mixed layout). No other Rust yet.
2. Data layer: the eight canonical tables from design D2 as Arrow schemas, Polars frames in Python,
   plus `Viewer` and the time constants.
3. SQLite store, chunk side only: `documents`, `document_grants`, `chunks`, `chunk_embeddings`,
   FTS5 external-content index with an ACL token column, sqlite-vec `vec0` table per embedding
   spec partitioned by principal-set hash, `fact_*` tables created by the migration but unused.
   Capabilities: `vector_search`, `bm25`, `get_chunks`, all taking a `Viewer`.
4. `LLM` protocol with one OpenAI-compatible adapter (covers OpenAI, OpenRouter, vLLM, Ollama, LM
   Studio) and a CLI subprocess adapter; content-addressed disk cache keyed on the full effective
   request; structured output via JSON schema with parse-and-retry.
5. `Embedder` protocol with an `EmbeddingSpec` (model id, revision, dims, pooling, normalisation,
   query and passage prefixes, quantisation, runtime) and adapters: OpenAI-compatible,
   sentence-transformers (MPS on Apple Silicon), fastembed (ONNX). Same disk cache.
6. `Reranker` protocol with a cross-encoder adapter (sentence-transformers) and an API adapter.
7. Datasets: HotpotQA, MuSiQue, 2WikiMultiHopQA loaded from upstream releases into the canonical
   schema, corpus built by the HippoRAG protocol and verified by content hash against the HippoRAG
   `reproduce/dataset` files; pinned question-id lists; a committed 20-question smoke fixture per
   dataset.
8. Pipelines: closed-book, BM25-only, dense, hybrid (dense + BM25 fused + cross-encoder rerank),
   oracle gold passages. One reader prompt shared by all.
9. Evaluation: EM and token-F1 with HotpotQA normalisation and HippoRAG's max-over-aliases
   aggregation, Contain-Acc, Judge-Acc (single-answer correctness judge, model family recorded),
   R@2 and R@5 on supporting passages, tokens, cost, latency, and indexing cost.
10. Run store: one SQLite file with `runs`, `run_questions`, `run_artifacts`; the run identity from
    design D8; reports as Polars frames; one marimo notebook that slices runs.
11. Embedding sweep: run the dense pipeline once per `EmbeddingSpec` on the same corpus; report
    R@2, R@5, EM, F1 and indexing cost per embedder. Embedder list comes from
    `docs/research/embeddings.md`.
12. CLI: `triplum bench run`, `triplum bench report`, `triplum data fetch`.

Out: facts, entities, extraction, graph retrieval, Neo4j, temporal or ACL question families (the
schema is in place; the fixtures come with 2a), pairwise judge (BenchmarkQED path comes with the
gold-less corpus work), community summaries, agentic loops, any UI.

## Architecture

```
python/triplum/
  data/      schema.py (re-exports Arrow schemas from _core), viewer.py, frames.py (row views)
  llm/       protocol.py, cache.py, openai_compat.py, cli.py
  embed/     protocol.py (EmbeddingSpec, Embedder), openai_compat.py, sentence_transformers.py, fastembed.py
  rerank/    protocol.py, cross_encoder.py, api.py
  store/     protocol.py (Store, capabilities), sqlite/ (migrations.sql, store.py, fts.py, vec.py)
  ingest/    chunking.py (fixed-size and hierarchical; hierarchical is used by 2a)
  retrieve/  dense.py, bm25.py, hybrid.py (RRF fusion + rerank), oracle.py
  generate/  reader.py (one prompt, one call)
  eval/      datasets/{hotpotqa,musique,twowiki}.py, protocol.py (corpus build + hash check),
             metrics.py, judge.py
  bench/     config.py (frozen dataclasses), runner.py, runstore.py, report.py, cli.py
crates/
  triplum-core/   src/schema.rs (Arrow schemas), src/time.rs (constants)
  triplum-py/     src/lib.rs (exposes schemas via arrow-rs -> pyarrow C data interface)
notebooks/   runs.py (marimo)
tests/       unit per module; integration/test_pipelines_fixture.py
```

Stage contract: a stage is a callable taking frames and a `Viewer` and returning frames. A
pipeline is a function `run(question_frame, store, cfg, viewer) -> answer_frame`. Config is a
frozen dataclass; `cfg.hash()` is stable across processes.

`Viewer` for this sub-project is the all-access viewer over a single public principal; the
plumbing is exercised, the semantics are tested in 2a.

## Key interfaces

```python
class LLM(Protocol):
    def complete(self, messages: list[Message], *, schema: dict | None = None,
                 params: GenParams = GenParams()) -> Completion: ...
# Completion: text, parsed, usage(input, output, cached), cached: bool, request_hash

@dataclass(frozen=True)
class EmbeddingSpec:
    model: str; revision: str; dims: int; pooling: str; normalize: bool
    query_prefix: str; passage_prefix: str; quantization: str; runtime: str
    def hash(self) -> str: ...

class Embedder(Protocol):
    spec: EmbeddingSpec
    def embed_queries(self, texts: list[str]) -> np.ndarray: ...
    def embed_passages(self, texts: list[str]) -> np.ndarray: ...

class Store(Protocol):
    def put_documents(self, docs: pl.DataFrame, grants: pl.DataFrame) -> None: ...
    def put_chunks(self, chunks: pl.DataFrame) -> None: ...
    def put_embeddings(self, spec: EmbeddingSpec, emb: pl.DataFrame) -> None: ...
    def vector_search(self, spec: EmbeddingSpec, q: np.ndarray, k: int, viewer: Viewer) -> pl.DataFrame: ...
    def bm25(self, query: str, k: int, viewer: Viewer) -> pl.DataFrame: ...
    def get_chunks(self, ids: list[int], viewer: Viewer) -> pl.DataFrame: ...
    def capabilities(self) -> Capabilities: ...
```

Run identity (`runs` row): run id, created_at, code version (git sha, dirty flag), dataset id and
corpus content hash, question-list hash, pipeline name and config hash, embedding spec hash,
reranker spec, reader model id and params, judge model id, prompt hashes, seed, viewer, cache
hit rate, indexing cost (tokens, seconds, USD), total cost, wall time. `run_questions`: per
question the retrieved chunk ids with scores, the answer, every metric, tokens and latency.
`run_artifacts`: paths and hashes of the store file and any index used.

## Datasets and protocol

- Upstream: HotpotQA distractor dev (CC BY-SA 4.0), MuSiQue-Ans dev (CC BY 4.0), 2WikiMultiHopQA
  dev (Apache-2.0). Fetched by `triplum data fetch` into a local cache; never committed.
- Corpus: dedupe by (title, text) over all candidate paragraphs of the pinned 1000 questions,
  giving HotpotQA 9,811, 2Wiki 6,119, MuSiQue 11,656 passages; content hash compared to the
  HippoRAG release files and recorded. Question ids pinned in `python/triplum/eval/protocol/*.txt`.
- Chunking for this sub-project: one passage is one chunk (matches the protocol). Hierarchical
  chunking is implemented but only used by 2a.
- Smoke fixture: 20 questions per dataset with their gold and distractor passages, committed under
  `tests/fixtures/` with attribution. Every integration test runs on it; `--n 20` on the CLI uses it.
- Generation-2 configuration is the default label: reader `gpt-4o-mini` tier by default (cheap),
  `llama-3.3-70b-instruct` via an OpenAI-compatible endpoint as the comparison tier; top-5 passages.

## Metrics

EM and F1: HotpotQA `normalize_answer`, max over gold aliases, no yes/no zeroing, stated in the
report header. Contain-Acc: normalised gold substring of normalised answer. Judge-Acc: one LLM call
per question with the gold answer, binary, judge model recorded and required to be from a different
family than the reader. R@k: fraction of gold supporting passages in the top-k retrieved, HippoRAG
definition. Indexing cost: embedding tokens and seconds, reported per run, not amortised.

## Error handling

Provider errors retry with backoff and are recorded per question; a question whose reader call
ultimately fails scores zero and is flagged, never dropped. A corpus hash mismatch aborts the run
with both hashes printed. A cache hit is recorded as such; a run may be declared `cache_only` and
then fails on the first miss (for exact replays).

## Testing

- Unit: metrics against the official HotpotQA script on a hand-built case set; cache key
  stability; config hashing; FTS5 and vec0 round trips with a viewer that excludes some documents
  (the excluded rows must not appear in any result, and no embedding leaves the store for them).
- Integration: all five pipelines on the 20-question fixture with a deterministic fake LLM and a
  tiny local embedder; asserts the run store rows, metric ranges, and that oracle >= dense >= closed
  book on R@5 where defined.
- Replay: a `--cache-only` test that re-runs the fixture from the local LLM cache and asserts
  identical metrics; skipped when the cache is absent. Cached responses are not committed.
- `cargo test` for schema construction; a Python test that the `_core` schemas equal the
  documented column lists.

## Milestones

1. Scaffold builds: `uv sync`, `maturin develop`, `pytest` green with schema tests only.
2. Store + FTS5 + vec0 with viewer filtering, unit-tested.
3. LLM and embedder protocols, adapters, cache.
4. Datasets fetched, corpora built and hash-verified, fixtures committed.
5. Pipelines and metrics; integration test green on fixtures.
6. Run store, report, notebook, CLI.
7. First real numbers: dense on MuSiQue at 1000 questions with one embedder, all baselines on the
   table. Then the embedding sweep.

## Decisions to confirm

- maturin from day one with schemas in Rust (vs pure Python now, Rust later). Chosen: maturin.
- One passage per chunk for the baselines (protocol-faithful) rather than re-chunking. Chosen: one.
- Reader default `gpt-4o-mini` tier; 70B tier optional. Chosen: cheap default, both labelled.

## Open questions

- Which OpenAI-compatible endpoint serves Llama-3.3-70B for the comparison tier (OpenRouter vs a
  local server)? Decide when the first full run is scheduled.
- Whether the judge's A/A win-rate diagnostic belongs in this spec or with the pairwise judge. Left
  to the pairwise judge.
