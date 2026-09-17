# triplum

Snapshot 2026-09-17. Composable, benchmark-first sandbox for LLM knowledge-graph work: KG
construction, GraphRAG retrieval, storage backends and evaluation. Python-first with a Rust core
behind an Arrow boundary. Bi-temporal facts and provenance-derived permissions are first-class
and enforced in the store.

## What works

The non-graph half: canonical schemas, a SQLite store with viewer-filtered BM25 and vector
search over chunks, cached LLM, embedder and reranker protocols with real and fake adapters, a
registry of 37 pinned datasets with committed fixtures, six baselines (closed-book, BM25, dense,
RRF fusion, hybrid with rerank, oracle), the metrics, and a run store keyed by run identity. The
first graph half: a non-LLM extraction baseline (`rules` over spaCy, `small_model` over GLiNER and
GLiREL), entity resolution as supported `same_as` facts, the store's graph side under the chunk
visibility rule, and intrinsic triple scoring via `triplum bench extract`. Graph retrieval is
next. [Flow](flow.md) keeps the implemented versus planned list exact.

## Five minutes

```
uv sync --all-extras
uv run triplum bench run --pipeline bm25 --dataset musique --n 20 --fixture --reader fake
uv run triplum bench report
```

The first command builds the Rust extension. The second runs the BM25 baseline over the
committed 20-question MuSiQue fixture with the deterministic fake reader, entirely offline, and
prints the run's summary. The third lists stored runs. Swap `--reader openai --reader-model
<id>` with `OPENAI_API_KEY` set for a real reader, drop `--fixture` to fetch the pinned protocol
files, and `--embedder st:<model>` with the `local` extra for a dense pipeline. The same run as
Python is in the [README](https://github.com/fkarg/triplum#use-it-as-a-library).

## Where to go

- [Flow](flow.md): what a benchmark run does step by step, which modules implement each step,
  and what is implemented versus planned.
- [Datasets](datasets.md): the built-in benchmarks, the record types, identity without reading,
  and how to bring your own corpus, questions or folder.
- [Modules and interfaces](api/index.md): every module with its status, key symbols and the
  cross-module contracts, plus the API reference generated from the source.
- [Benchmarking and caching](benchmarking.md): the contract for run identity, caching, replay,
  crash recovery and inspection.
- [Design record](research/design.md): the decisions, the alternatives rejected, and the order of
  sub-projects; the [research notes](research/README.md) behind them.
- [Licences](licences.md): every third-party dataset, model and dependency with its terms.
