# Benchmarking and caching

Every measurement in triplum is a *run*: one pipeline, one dataset, one exact configuration,
recorded in the run store with everything needed to reproduce it. Expensive steps are cached and
reused across runs, and any run can be forced to recompute. This page is the contract.

## Run identity

A run's identity is the hash of these fields (see `IDENTITY_FIELDS` in
`python/triplum/bench/runstore.py`):

| field | what it pins |
|---|---|
| dataset, corpus_hash, questions_hash, n | which data, byte-exact (sha256 of the protocol files), how many questions |
| pipeline, config_hash | the pipeline name and the hash of the full `PipelineConfig` (top-k, candidates, embedder config, reranker config, reader config) |
| embedding_spec, reranker_spec | hashes of the model specs actually instantiated (model, revision, dims, prefixes, quantisation, runtime) |
| reader_model, judge_model, reader_prompt_hash, judge_prompt_hash | which models answered and judged, and the exact prompt text and output schema |
| seed | passed to the reader and judge requests, so it is part of the call-cache key too |
| viewer_json | the principals the run was executed as |
| code_version, dirty | git sha, and whether the working tree had uncommitted changes |

Two runs with the same identity are the same experiment. `run_benchmark` looks the identity up
first and returns the existing run id unless `force` is set. Changing anything in the table above,
including editing a prompt string or running with uncommitted code, produces a new identity.

Things deliberately *outside* the identity: host name and wall time (recorded, not identifying),
cache state (recorded as hits and misses), and prices (snapshotted per run, see below).

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

`--force` creates a new run id and a new set of events; it does not clear caches. To recompute
model calls as well, point `TRIPLUM_CACHE` at an empty directory. To rebuild a store, delete the
store file (`~/.cache/triplum/stores/<dataset>-<corpus_hash>.sqlite`); it is regenerated from the
verified protocol files.

## Cost and runtime

Every call and stage writes one row to `events` (stage, question, provider, model, start, end,
tokens in and out, cached-input tokens, cached flag, USD). Prices come from the `prices` table and
are copied into `run_prices` when a run starts, so a run's cost is computed from the prices in
force at that moment and stays stable after price updates. Local models have USD null and are
measured by wall time. Indexing cost is reported per run from the `index.*` events, never amortised.

Set a price with `RunStore.set_price(model, provider, usd_in_per_m=..., usd_out_per_m=...,
usd_cached_in_per_m=..., source=<url>)`; the source URL is required and travels with the run.

## What a results table must carry

Per `docs/research/benchmarks-multihop-qa.md`: EM, F1, Contain-Acc, Judge-Acc, R@2, R@5, indexing
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
