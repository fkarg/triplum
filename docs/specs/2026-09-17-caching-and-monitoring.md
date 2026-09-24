# Caching and run monitoring, end to end

Snapshot 2026-09-24. R6, R7, R9, R14 and R15 landed with stages (commits
`25861fe` to `40c5260`). Status: **open requirements, not yet an implementation contract.**
Interfaces are settled layer by layer in the
[`../plans/2026-09-17-stack-walk.md`](../plans/2026-09-17-stack-walk.md)); each requirement
below names the layer that must satisfy it, and its interface is decided when the walk reaches
that layer. The existing contract this spec makes true is `docs/benchmarking.md` and design D6a.

## Open gaps

The stage rewrite closed repeated dataset parsing, redundant grounding/resolution, and
whole-file store hashing (R6, R7, R9, R14, R15). The remaining work is adapter call
accounting and cache control; stable model/weight specs; per-question retrieval and cost
accounting; separate timed events for grounding and resolution (R10); progress inside long
stages; cache inspection/pruning; and logging. A corpus store
still holds only one graph variant. The original audit, including its closed findings, is
recoverable with `git show 977f1ac:docs/specs/2026-09-17-caching-and-monitoring.md`.

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
  store stays SQLite-only; the earlier comparison is in the temporary foundation note.
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
- Why the run store stays SQLite-only: [temporary foundation note](../notes/previous-foundation.md).
