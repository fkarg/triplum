# triplum

Composable, benchmark-first sandbox for LLM knowledge-graph work: KG
construction, GraphRAG retrieval, storage backends and evaluation. Python-first with a Rust core
behind an Arrow boundary. Bi-temporal facts and provenance-derived permissions are first-class
and enforced in the store.

## Current state

Six non-graph QA baselines and the non-LLM extraction baseline run end to end. The runner now
uses cached stages; the foundation rewrite continues at the store ingestion boundary.
[Flow](flow.md) records implemented behavior and the [stack walk](plans/stack-walk.md)
records open interfaces.

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

- [Learn](guide/documents.md): short examples for documents, sources, loading batches, corpus
  frames, and viewers.
- [Flow](flow.md): what a benchmark run does step by step, which modules implement each step,
  and what is implemented versus planned.
- [Datasets](datasets.md): the built-in benchmarks, the record types, identity without reading,
  and how to bring your own corpus, questions or folder.
- [Modules and interfaces](api/index.md): every module with its status, key symbols and the
  cross-module contracts, plus the API reference generated from the source.
- [Benchmarking and caching](benchmarking.md): the contract for run identity, caching, replay,
  crash recovery and inspection.
- [Design record](research/design.md): the decisions, the alternatives rejected, and the intended research direction; the [research notes](research/README.md) behind them.
- [Licences](licences.md): every third-party dataset, model and dependency with its terms.
