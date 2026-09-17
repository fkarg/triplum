# Benchmarking and caching

Every measurement in triplum is a *run*: one pipeline, one dataset, one exact configuration,
recorded in the run store with everything needed to reproduce it. Expensive steps are cached and
reused across runs, and any run can be forced to recompute. This page is the contract.

## Run identity

A run's identity is the hash of these fields (see `IDENTITY_FIELDS` in
`python/triplum/bench/runstore.py`):

| field | what it pins |
|---|---|
| dataset, corpus_hash, questions_hash, n | which data: hashes of the parsed corpus and question frames, so a parser change is a new identity even when the source bytes did not change; how many questions |
| pipeline, config_hash | the pipeline name and the hash of the full `PipelineConfig` (top-k, candidates, embedder config, reranker config, reader config) |
| embedding_spec, reranker_spec | hashes of the model specs actually instantiated (model, revision, dims, prefixes, quantisation, runtime) |
| reader_model, judge_model, reader_prompt_hash, judge_prompt_hash | which models answered and judged, and the exact prompt text and output schema |
| seed | passed to the reader and judge requests, so it is part of the call-cache key too |
| viewer_json | the principals the run was executed as |
| code_hash | sha256 of the source files the pipeline executes (`python/triplum/bench/fingerprint.py` lists them per pipeline, plus `migrations.sql` and the Rust schema). Editing the CLI, the report or the docs does not change it; editing a stage does. The git sha and dirty flag are recorded on the run but do not identify it. |

Two runs with the same identity are the same experiment. `run_benchmark` looks the identity up
first and returns the existing run id unless `force` is set. Changing anything in the table above,
including editing a prompt string or a stage's source, produces a new identity.

Things deliberately *outside* the identity: host name and wall time (recorded, not identifying),
the git sha and dirty flag (recorded; the code hash above is what matters), cache state (recorded
as hits and misses), and prices (snapshotted per run, see below). A resumed run keeps its identity
only while the pipeline's code hash is unchanged; fixing a bug in a stage and resuming produces a
new run, which is the honest outcome.

## Cache levels

1. **Call cache** (`~/.cache/triplum`, or `TRIPLUM_CACHE`): every LLM completion, embedding and
   reranker score, keyed on the full effective request: adapter identity including endpoint or
   CLI argv, model, messages, output schema, generation parameters including seed. A hit is an exact
   replay and is recorded as `cached` on the event and on the question row. Cost is still computed
   for cached calls (nominal cost); the report shows `usd_total` (nominal) next to `usd_spent`
   (calls that actually ran).
2. **Artifact cache**: a store file is bound to one corpus hash (`meta.corpus_hash`); documents and
   chunks are ingested once; embeddings are stored per embedding spec and only missing chunks are
   embedded. Switching embedders is a full embed of the new spec, never a re-embed of an existing one.
3. **Run lookup**: identical identity returns the stored run.

Caches are per machine. Runs from different machines are not compared.

## Exact configuration, replay, force

```
triplum bench show <run_id>            # identity fields plus the full config JSON
triplum bench rerun <run_id>           # replay: returns the same run (lookup) if nothing changed
triplum bench rerun <run_id> --force   # recompute; call-cache hits still apply, artifacts are reused
triplum bench run ... --force          # same for a fresh command line
```

`--force` creates a new run id and a new set of events; it does not clear caches.

## Crash and resume

Each finished question is one transaction: its events and its `run_questions` row commit together.
A run that raises is marked `failed`; a hard crash leaves it `running`. Either way, finished
questions are kept. `--resume` (on `bench run` and `bench rerun`) finds the run with the same
identity in `running` or `failed` state, reuses its id, and processes only the questions that have
no row yet. Resume is opt-in so a partial run is never reused by accident; without it, a new run is
started and finished questions are served from the call cache.

## Inspecting runs

```
triplum bench inspect <run_id> [--question <id>] [--json]   # answer, metrics, retrieved passages, model calls
triplum bench diff <run_a> <run_b>                          # identity and config fields that differ, metric means, per-question deltas
triplum bench tail <run_id> [--once]                        # done/total and the latest stage of a running benchmark
```

Passage text in `inspect` is resolved from the store artifact recorded with the run (path and
sha256); if the file is gone, ids are shown. `diff` never averages over missing questions: ids
present in only one run are listed separately. These are projections over the SQLite run store
(`python/triplum/bench/inspect.py`), not a second log format; see
`docs/research/tooling-event-logs.md` for why the run store stays SQLite-only. To recompute
model calls as well, point `TRIPLUM_CACHE` at an empty directory. To rebuild a store, delete the
store file (`~/.cache/triplum/stores/<dataset>-<corpus_hash>.sqlite`); it is regenerated from the
verified protocol files.

## Disk

Everything downloadable lives in two places: model weights under the Hugging Face cache
(`~/.cache/huggingface/hub`) and triplum's own data, stores, call cache and run store under
`~/.cache/triplum` (override with `TRIPLUM_CACHE`; datasets with `TRIPLUM_DATA`). Budget on the
laptop: under 200 GB for models plus data combined, keeping at least 100 GB free. Sizes as of
2026-09-16: protocol data 40 MB; a corpus store with one embedder a few hundred MB; the Mac sweep
subset about 3 GB of weights; NV-Embed-v2 about 16 GB and Qwen3-Embedding-4B about 8 GB, which
are for the workstation. Check with `du -sh ~/.cache/huggingface/hub ~/.cache/triplum`.

## Cost and runtime

Every call and stage writes one row to `events` (stage, question, provider, model, start, end,
tokens in and out, cached-input tokens, cached flag, USD). Prices come from the `prices` table and
are copied into `run_prices` when a run starts, so a run's cost is computed from the prices in
force at that moment and stays stable after price updates. Local models have USD null and are
measured by wall time. Indexing cost is reported per run from the `index.*` events, never amortised.

Set a price with `RunStore.set_price(model, provider, usd_in_per_m=..., usd_out_per_m=...,
usd_cached_in_per_m=..., source=<url>)`; the source URL is required and travels with the run.

## What a results table must carry

Per `docs/research/benchmarks.md` §2: EM, F1, Contain-Acc, Judge-Acc, R@2, R@5, indexing
cost, per-question latency and cost, the reader and judge model ids (different families, enforced),
the embedding spec, the corpus hash, and the closed-book, BM25-only and oracle baselines on the
same rows. `triplum bench report` prints all of it from the run store; the marimo notebook in
`notebooks/runs.py` slices it.

## Rules for new stages

- A stage that costs more than a second on the full corpus must be content-addressed: key on the
  hash of its inputs and its config, persist its output, skip on rerun.
- A stage must work with an empty cache. The cache is an optimisation, never a dependency.
- Anything that changes an answer must be in the run identity. If you add a knob, add it to the
  config that is hashed, or to the prompt whose hash is recorded.
- Never filter, dedupe, or drop questions silently; a mapping failure raises.
