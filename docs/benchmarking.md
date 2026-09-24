# Benchmarking and caching

Every measurement in triplum is a *run*: one pipeline, one dataset, one exact configuration,
recorded in the run store with everything needed to reproduce it. Expensive steps are cached and
reused across runs, and any run can be forced to recompute. This page is the contract.

## Run identity

A run's identity is the hash of these fields (see `IDENTITY_FIELDS` in
`src/triplum/bench/runstore.py`):

| field | what it pins |
|---|---|
| kind | QA or extraction run |
| dataset, corpus_hash, questions_hash | which data: the sources' fingerprints (pinned file digests, parser version, record contract, selection), computed without reading a file, so a parser version bump is a new identity even when the source bytes did not change; the selection (`n`) is inside the questions' fingerprint |
| pipeline, config_hash | the pipeline name and the hash of the full `PipelineConfig` (top-k, candidates, embedder config, reranker config, reader config) |
| embedding_spec, reranker_spec | hashes of the model specs actually instantiated (model, revision, dims, prefixes, quantisation, runtime) |
| reader_model, judge_model, judge_hash, reader_prompt_hash, judge_prompt_hash | which models answered and judged (the reader's full config is inside `config_hash`, the judge's inside `judge_hash`: endpoint, argv, generation parameters), and the exact prompt text and output schema |
| seed, replicate | the root seed and the replicate index; each replicate's stages draw from a seed derived from both, which reaches seed-sensitive adapters' requests and cache keys |
| viewer_json | the principals the run was executed as |
| extractor_spec, resolver_spec | the extraction and resolution configuration |
| (code, validated) | code is not a hashed field. Every stage a run executed recorded a manifest of the first-party functions it ran, the constants they read and the distributions involved; a stored run matches only when every one of those manifests still hashes the same in the current process (`runner.run_valid`). Editing the CLI, the report or the docs changes nothing; editing a helper a stage calls, or a prompt constant, invalidates exactly the runs and artifacts that executed it. `code_hash` on the run summarises the manifests afterwards; the git sha and dirty flag are bookkeeping. |

Two runs with the same identity are the same experiment. `run_benchmark` looks the identity up
first and returns the existing run id unless `force` is set. Changing anything in the table above
produces a new identity; editing a prompt string or a stage's source keeps the identity and fails
the manifest validation, which is the same outcome: the pipeline runs, and each stage fetches its
artifact when its own code and inputs are unchanged and recomputes otherwise.

The `graph_identity` column is filled after extraction. Its value is therefore a result, not a
pre-run discriminator: the `IDENTITY_FIELDS` tuple contains its slot, but extraction hashes
`None` there before the graph exists. Graph artifacts and store effects carry the resolved
identity. The stack walk tracks whether this field should remain in that tuple.

Things deliberately *outside* the identity: host name and wall time (recorded, not identifying),
the git sha and dirty flag (recorded; the manifests are what matters), cache state (recorded as
hits and misses), and prices (snapshotted per run, see below). A resumed run keeps its id; the
stages whose code changed since the crash recompute, the others fetch.

## Cache levels

1. **Call cache** (`~/.cache/triplum`, or `TRIPLUM_CACHE`): every LLM completion, embedding and
   reranker score, keyed on the full effective request: adapter identity including endpoint or
   CLI argv, model, messages, output schema, generation parameters including seed. A hit is an exact
   replay and is recorded as `cached` on the event and on the question row. Cost is still computed
   for cached calls (nominal cost); the report shows `usd_total` (nominal) next to `usd_spent`
   (calls that actually ran).
2. **Artifacts**: every stage output under `artifacts/<stage>/<key>/<code>/`, addressed by a data
   key over the stage's inputs and validated by the manifest of the code that produced it and
   its inputs; the corpus frames, the questions, the retrieval hits, the answers, the claims and
   the graph frames. Store effects (documents, embeddings per spec, the graph) live in the store
   file, which is bound to one corpus hash (`meta.corpus_hash`) and records each effect in its
   `effects` table. Switching embedders is a full embed of the new spec, never a re-embed of an
   existing one.
3. **Run lookup**: identical identity with validating manifests returns the stored run.

Caches are per machine. Runs from different machines are not compared.

## Exact configuration, replay, force

```
triplum bench show <run_id>            # identity fields plus the full config JSON
triplum bench rerun <run_id>           # replay: returns the same run (lookup) if nothing changed
triplum bench rerun <run_id> --force   # recompute; call-cache hits still apply, artifacts are reused
triplum bench run ... --force          # same for a fresh command line
```

`--force` creates a new run id and a new set of events; it does not clear caches, so its stages
fetch what they can. `--replicates N` runs the pipeline N times under derived seeds (replicate 0
is the run), then prints which stages added or absorbed variance and the metric spread;
`triplum bench variance <run_id>` shows it again.

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
store identity); if the file is gone, ids are shown. `diff` never averages over missing questions: ids
present in only one run are listed separately. These are projections over the SQLite run store
(`src/triplum/bench/inspect.py`); see
the [temporary foundation note](notes/previous-foundation.md) for the earlier event-log comparison. To recompute
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

EM, F1, Contain-Acc, Judge-Acc, R@2, R@5, indexing
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
