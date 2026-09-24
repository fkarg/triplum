# Stack walk: interfaces bottom-up, then recombination

Snapshot 2026-09-24. The data sources, stage contract and runner have been reworked. The next
boundary is store ingestion from `CorpusBatch` streams. Settle each remaining interface walking
up the stack, then recombine components into pipelines and sub-projects.

This plan lists the layers in walking order, what each layer currently is, the questions its
interface must answer, and which requirements from the caching and monitoring spec
([`../specs/2026-09-17-caching-and-monitoring.md`](../specs/2026-09-17-caching-and-monitoring.md),
"R" numbers) and which later sub-projects depend on it. Each layer gets its own spec section or
spec, a cross-model design review, and a commit before the next layer starts.

## Layers, in order

### 0. `utils.data` and `datasets` (done, owner's rework)

`Dataset[T]`, `IterableDataset[T]`, `DataLoader[T, B]`, `Take`, `RecordDataset`; sources own
`fingerprint()`. Built-in datasets reworked 2026-09-17 (historical record in the
[temporary note](../notes/previous-foundation.md)):
lazy source classes over pinned files, pydantic records (`Document` with segments, `Question`,
`Triple`), ids from each source's declared key, `Benchmark` holds datasets and the consumer
batches, identity without reading. Stages added 2026-09-18 (same note):
the runner is a composition of stages with data keys, trace-discovered code manifests,
artifacts and provenance rows; the corpus is read once into a frames artifact and every later
run fetches it. Consuming a corpus in batches into the store, with the store's `effects` table
as the first form of its ingestion log, is layer 1.

### 1. Store ingestion boundary

Now: `put_documents(docs, grants)` and `put_chunks(chunks)` take whole frames; the runner binds
`corpus_hash` from materialized content; a second corpus is a refusal.

Questions: how a store consumes `Iterable[CorpusBatch]` so that a batch's documents, grants
and chunks publish together (the review's "never publish partial ingestion, never widen an
ACL" verification); when the corpus identity is bound (before the first batch, from the source
fingerprint, with an in-progress marker until the last batch); whether binding and refusal live
in the store or in the bench layer; where a second graph over one corpus lives (D-a).
Satisfies R6, R8. Needed by: owner corpora (streams of documents with real `observed_at` and
`uri`), the chunk `metadata` column question for media offsets and page numbers, 2c.

### 2. Embedder and reranker

Now: list-in, list-out protocols with a per-item call cache; specs are frozen dataclasses.

Questions: call, hit and miss counting on the cached wrappers (R1); a real weights revision and
device class in every spec (R2); `cache_only` (R3); whether `ensure_embeddings` becomes a
loader-driven stage over chunk batches. Satisfies R1 to R3 for these adapters.

### 3. LLM

Now: `complete(messages, schema, params) -> Completion`, adapters OpenAI-compatible, CLI
subprocess, fake; the disk cache keyed on the full effective request.

Questions: the pydantic-ai adapter over the direct API with the request cache in a
`WrapperModel` ([`../research/llm-adapter-pydantic-ai.md`](../research/llm-adapter-pydantic-ai.md));
whether the protocol keeps its frozen `Message` and `Completion` or adopts pydantic-ai's
types (assessment: keep, convert at the edge; the owner leans to adopting, to be decided with
the evidence); `Usage` gaining cache-read and cache-write tokens (R5, R12); seed declaration
(R4); retries with provenance (R5); the whole-loop cache for agents (D-d). Needed by: the LLM
extractor, the judge, every reader, 2b.

### 4. Extraction

Now: `Extractor.run(chunks) -> (spans, claims)` over one frame; `stages.extract` and
`stages.resolve` produce `Extraction`; the per-chunk cache; `build` composes both.

Questions: extraction over chunk batches from a loader while resolution stays global (the
review's "do not turn global resolution into per-batch resolution"); the `Extraction` artifact
keyed by graph identity (R9); grounding and resolution as separate events (R10); the LLM
extractor's spec (prompt hash, output schema, vocabulary, decomposition on or off) under the
same protocol; span grounding for model output that cannot produce offsets (exact substrings
located in the chunk). Needed by: 2b, owner corpora.

### 5. Retrieval and generation

Now: stages over a questions frame and a store with a `Viewer`; six pipelines as plain
functions; one reader prompt.

Questions: per-question events (R12); the graph retrieval stages (`seed`, `expand`, `ppr`
over a CSR built from the viewer's visible adjacency) and the store capabilities they need
(`adjacency_batches`, entity lookup by name); a graph-disabled ablation with the same evidence
budget; what a retrieval result carries (chunk ids and scores, or facts and their support).
Needed by: 2a, the owner corpora search.

### 6. Evaluation

Now: QA metrics, intrinsic triple metrics, judge; `QAEvaluation` and `ExtractionEvaluation`
as independent sources.

Questions: the temporal and ACL contract fixtures (seven families, toy scale, gold "refuse")
as a `Benchmark` composition; evaluation identity from source fingerprints; whether the judge is
a stage of generation or of evaluation for event accounting. Needed by: the leakage gate before
2a.

### 7. Bench: identity, caching, monitoring, tooling

Now: `RunConfig`, `ExtractConfig`, `run_benchmark`, `run_extraction`, the run store, the
fingerprint, the CLI.

Open questions: artifact cache layout (D-b); events with calls and hits (R11); progress rows
(D-c, R13); `cache status` and `prune` (R16); the logger (R17); the remaining docs corrections
(R18). Source-fingerprint lookup and persisted corpus artifacts (R6, R7), store identity (R14),
and the shared identity field list (R15) landed with stages. `graph_identity` is currently
filled after extraction, so its slot in the pre-run identity hashes `None`; decide whether to
remove that ineffective slot when this layer settles the identity contract. This layer closes
the caching and monitoring spec.

## Recombination, after the walk

In this order, each with its own spec and plan, on the settled interfaces:

1. **Caching and monitoring end to end**, closing the spec above (mostly layer 7 with the
   adapter counters from layers 2 to 4).
2. **pydantic-ai adapter and the LLM extractor** (layers 3 and 4), the first 2b variant.
3. **Temporal and ACL contract fixtures, then graph retrieval** (layers 5 and 6), sub-project
   2a with the leakage gate.
4. **Owner corpora ingest**: papers through GROBID (sections as hierarchical chunks,
   references as linkable entities, captions), transcripts through the canonical transcript
   model; both cite `(source, offset)` spans. Research:
   [`../research/ingestion-sources.md`](../research/ingestion-sources.md).
5. **Transcription**: yt-dlp captions and audio, mlx-whisper on the laptop, whisperX or
   Parakeet on the workstation, pyannote diarisation as a separate stage; a separate
   sub-project by the design record.
6. **Documentation and examples** (D9): tutorial pages with runnable, tested examples, the
   curated top-level namespace, the reference generated from the documented surface.

## Rules for the walk

- One layer at a time. A layer's spec names its callers and what they may assume; a layer does
  not reach past the one below it.
- No code for a layer before its interface is agreed and cross-model reviewed; record the
  review outcome in `design.md`.
- Existing behaviour stays green through the walk: the fixture pipelines and the extraction
  fixture tests are the regression harness at every step.
- `flow.md` and `docs/api/index.md` change in the same commit as the layer they describe.
