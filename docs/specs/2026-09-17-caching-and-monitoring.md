# Caching and run monitoring, end to end

Snapshot 2026-09-17. Status: **requirements and gap map, not yet a contract.** The owner is
redefining the interfaces layer by layer (see
[`../plans/2026-09-17-stack-walk.md`](../plans/2026-09-17-stack-walk.md)); each requirement
below names the layer that must satisfy it, and its interface is decided when the walk reaches
that layer. The existing contract this spec makes true is `docs/benchmarking.md` and design D6a.

## Why now

D9 sequences the documentation and examples work after "the extraction baseline, caching and
run monitoring are functional end to end". The baseline is in. A read-only audit of caching and
monitoring against the benchmarking contract (2026-09-17, findings below) shows they are not
functional end to end: hit and miss counts are wrong or absent for most stages, two expensive
stages recompute on every run, an identity lookup still parses the whole dataset, and the live
view is blind inside any long stage.

## Gap map

Findings against the contract, with the module that owns each. Line numbers are omitted on
purpose; the function names are stable enough to find.

### Accounting

1. **A cold extraction run reports zero cache misses.** `Recorder.stage` counts a miss only when
   the event carries tokens; the `extract` event passes zero tokens (`bench/runner.py`,
   `run_extraction`), so a run that computed every chunk counts as neither hit nor miss.
   `CachedExtractor` knows its misses and nobody reads them.
2. **The embedding stage always counts as a miss.** `ensure_embeddings` (`bench/index.py`)
   reports whitespace word counts as input tokens and never sets `cached`, even when every
   vector came from the call cache. `CachedEmbedder` has no hit counter.
3. **Retrieval counts nothing** for dense and fusion pipelines and stuffs the reranker pair
   count into `input_tokens` for hybrid (`run_benchmark`).
4. **Two cost columns measure different things.** `run_questions.usd` is the reader only, with
   cached-input tokens forced to zero; `usd_spent` in the report sums all non-cached events
   including the judge. Neither is "what this question cost".
5. **Cached-input tokens are dropped** by the reader's output schema (`generate/reader.py`), so
   provider prompt-cache discounts never reach a price.
6. **`retrieve` is one event for all questions**, so per-question latency is reader latency
   only; the contract promises per-question latency and cost.

### Recomputation

7. **Grounding and resolution run on every extraction run**, even when every chunk is a cache
   hit: the per-chunk cache stores spans and claims, and `stages.build` (`extract/stages.py`)
   rebuilds the frames and re-runs the resolver (quadratic for `fuzzy`) each time. The graph is
   written to the store, but the store is a single slot, so the `Extraction` value has no home
   of its own.
8. **Dataset parse and frame hashing run on every invocation**, including a pure identity
   lookup and `bench rerun`: `materialize` (`bench/inputs.py`) consumes the sources before
   `find_run` is consulted. The new dataset fingerprints (`datasets-and-loaders` spec) exist to
   make the lookup possible before reading; the runner does not use them yet. Local folders
   re-extract every PDF each time.
9. **`sha256_file(store)` at the end of every run** hashes a store of hundreds of MB, and the
   hash is stale by construction because later runs add tables to the same file; `inspect`
   only checks existence.

### Structure

10. **One graph per store, and the store is shared with QA runs.** `ensure_graph` refuses a
    second graph identity; comparing two extractors on one dataset means deleting embeddings or
    juggling `--store` by hand.
11. **Keys that omit something that changes the output.** `RerankSpec.revision` is the literal
    string `"hf"` for the cross-encoder; the small-model extractor's device (MPS versus CPU) is
    not in its spec; the LLM cache stores the raw response but no parse or retry provenance
    (D6 asks for it; nothing retries anywhere).
12. **Unimplemented spec items.** `cache_only` mode, retry with backoff, and recording whether a
    provider honours a seed (harness spec, "Caching and repeatability" and "Error handling").

### Monitoring

13. **`tail` is blind inside a long stage.** Events are written when a stage exits; extraction
    and embedding are one event each. For extraction runs `done` counts question rows, so it
    shows `0/n` until the end.
14. **No cache tooling.** Nothing lists, sizes, prunes or verifies the cache root; the contract
    tells the user to run `du`. The call cache's 256 shard directories sit directly beside
    `stores/`, `data/` and `runs.db`, and the key hashes the kind in, so the kind of an entry
    cannot be recovered from the file system.
15. **No logging.** The package never imports `logging`; the only stderr lines are three CLI
    notices. `inspect` prints per-event tokens and duration but not cost, and no per-question
    total. The marimo notebook shows two tables and no events.

### Documentation

16. D6a says cache hits are "recorded in the run identity"; `benchmarking.md` says they are
    deliberately outside it. The contract is right; the decision text is wrong.
17. `flow.md` places the call cache under `<root>/cache/` and datasets under the cache root;
    the cache is at the root and datasets follow `TRIPLUM_DATA` regardless of `--cache-root`.
18. The identity table in `benchmarking.md` omits `kind`, `extractor_spec`, `resolver_spec` and
    `graph_identity`, which `IDENTITY_FIELDS` contains; `diff` omits them too and includes the
    non-identity `code_version` and `dirty`.

## Requirements

Each requirement names the layer of the stack walk that owns it.

### Adapters (LLM, embedder, reranker, extractor)

- R1. Every cached adapter counts its own calls, hits and misses, and exposes them. Tokens never
  stand in for calls.
- R2. Every spec that is a cache key names the actual weights revision and, for local models,
  the device class. A key that cannot tell two versions apart is a defect.
- R3. `cache_only`: a cached adapter can be told to raise on the first miss, so a replay is
  exact or fails loudly.
- R4. An adapter declares whether the provider honours a seed; the run records it.
- R5. Retry and backoff live in the adapter that talks to a network, once, with the attempt
  count in the cached entry's provenance. The pydantic-ai adapter brings its own
  ([`../research/llm-adapter-pydantic-ai.md`](../research/llm-adapter-pydantic-ai.md)).

### Sources and store

- R6. Corpus identity is the source's `fingerprint()`, known before the source is read where
  the source allows it, so an identity lookup never parses a dataset.
- R7. A parsed source that is expensive to produce (a registry dataset, a folder of PDFs) is
  persisted once under an artifact key and read back on the next run.
- R8. A store file holds one corpus and at most one graph, and the store knows both identities.
  How a second graph over the same corpus is placed is a decision (below).

### Extraction

- R9. The `Extraction` value (the four frames plus claims) is an artifact keyed by the graph
  identity. Grounding and resolution run once per identity.
- R10. Grounding and resolution are separate events with their own durations; `chunks_per_s`
  measures extraction alone.

### Run store and runner

- R11. Events carry `calls` and `cache_hits`; `cached` is derived (all calls served, at least
  one call). Hit and miss totals on the run are sums over events.
- R12. One retrieval event per question. Per-question cost is the sum of that question's
  events, reader and judge included, cached-input tokens priced at the cached rate. The report
  has one cost quantity per question and one "paid" quantity per run, defined once.
- R13. A stage reports progress while it runs: one row per run that the stage updates in place
  with a unit name, done and total, so the live view moves inside extraction and embedding and
  extraction runs count chunks.
- R14. The store artifact recorded on a run is the store's own identity (corpus and graph
  identities from its meta table), not a file hash.
- R15. Identity fields in the run store, the benchmarking contract and `diff` are one list.

### Tooling and docs

- R16. `triplum cache status` (sizes and entry counts by kind and by artifact identity) and
  `triplum cache prune` by kind. The layout must make the kind recoverable from the path.
- R17. A `triplum` logger; the CLI attaches a stderr handler. No second event format: the run
  store stays SQLite-only, as `docs/research/tooling-event-logs.md` decided.
- R18. D6a, `flow.md` and `benchmarking.md` corrected in the same change as the code that makes
  them true.

## Decisions to take

Recorded here so the stack walk takes them at the right layer; each is an architectural fork
with real trade-offs.

- **D-a. Where a second graph over the same corpus lives** (store layer). Options: one store file
  per corpus and graph, made by copying the corpus store and named by both identities; a
  `graph_id` column on the four graph tables with every graph read filtered by it; keep the
  single slot and require `--store` for any graph work. Assessment: the first option needs no
  schema change and keeps the visibility SQL as it is, at the cost of one file copy per graph
  variant.
- **D-b. Cache layout** (bench layer). `calls/<kind>/<aa>/<key>` for call entries and
  `artifacts/<kind>/<identity>/` for stage outputs, under the one root. Existing entries are
  orphaned once; on a research machine that is acceptable and must be stated in `flow.md`.
- **D-c. Progress channel** (bench layer). A `progress` table in the run store updated in place,
  read by `tail`, versus a terminal progress bar in the process. The first keeps the run store
  the only observation surface and works for a run started elsewhere; the second is nicer to
  watch and invisible to any other process. Assessment: the table, with `tail` as the bar.
- **D-d. Whole-loop caching for agents** (LLM layer). Keyed on the agent specification plus
  inputs, valid only when every tool is a pure function of inputs already in the run identity
  (D6 amendment). Whether the loop cache is a second `WrapperModel`-style layer or a function
  `cached_run(agent_spec, inputs)` is decided with the adapter.

## Non-goals

- A second log format, JSONL export, or a cache index database. The run store is SQLite only;
  cache tooling reads the file system.
- Sharing caches between machines. The cache stays per machine (D9).
- Prefetching, workers, or a streaming runner. `DataLoader` batches lazily; making the runner
  bounded-memory is the store and extraction layers' boundary work, not this spec.

## Acceptance

- A cold extraction run on a fixture reports misses equal to its chunk count and a second run
  reports the same number of hits, zero misses, and no grounding or resolution time.
- A QA run served entirely from the call cache reports zero misses on embedding, retrieval,
  reading and judging, and its per-question cost equals the priced sum of its events.
- `bench rerun` and an identity lookup on a registry dataset complete without parsing it.
- Two extractors on one dataset produce two graphs without deleting anything.
- `tail` shows chunk progress during extraction and vector progress during embedding.
- `cache status` accounts for every byte under the root by kind.
- D6a, `flow.md` and `benchmarking.md` agree with the code and with each other.

## External references

- pydantic-ai adapter facts: [`../research/llm-adapter-pydantic-ai.md`](../research/llm-adapter-pydantic-ai.md).
- Why the run store stays SQLite-only: [`../research/tooling-event-logs.md`](../research/tooling-event-logs.md).
