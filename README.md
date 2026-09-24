# triplum

A composable, benchmark-first sandbox for knowledge-graph work with LLMs: building a KG from
text, GraphRAG retrieval over it, storage backends, and evaluation. It is a Python library with a
Rust core behind an Arrow boundary. Two properties are enforced in the store rather than added
later: every fact is bi-temporal (valid time and transaction time), and visibility derives from
the provenance of a fact's supporting chunks, so a viewer never sees a fact, entity or summary
built on text they could not read.

The project is public and research-oriented, and it is run with industrial priorities: numbers
over novelty, every result reproducible from its run identity, and non-commercial components
allowed only where [`docs/licences.md`](docs/licences.md) records what that costs.

## Status

The library runs six non-graph QA baselines and a non-LLM graph extraction baseline over lazy,
fingerprinted datasets. The runner uses cached stages and validates executed code before
reusing results. The active work is a bottom-up foundation rewrite; store ingestion from
`CorpusBatch` streams is the next boundary. See [the current flow](docs/flow.md) for implemented
behavior and [the stack walk](docs/plans/stack-walk.md) for open interfaces.

## Install

```
pip install triplum                # abi3 wheels for Linux x86_64/aarch64 and macOS arm64
uv sync --all-extras               # from a clone: builds the Rust extension via maturin
```

Real models need `OPENAI_API_KEY` (or an OpenAI-compatible `--base-url`), or a local
`claude` CLI; the `local` extra adds sentence-transformers and fastembed embedders.

## Use it as a library

Data access is independent of the benchmark harness: subclass `Dataset[T]` for indexed data or
`IterableDataset[T]` for streaming, and implement `fingerprint()` to identify its logical content.
`DataLoader` lazily batches either shape (or ordinary iterables), supports custom collation, and
preserves native batches with `batch_size=None`. See the [data loading example](docs/api/utils-data.md).
Sources yield `Document`, `Question` and `Triple` records; the built-in sources and the catalog
live in `triplum.datasets`, and a `Benchmark` composes a corpus with optional question and gold
triple sources, all lazy ([docs/datasets.md](docs/datasets.md)). Current benchmark algorithms
still explicitly materialize those sources; the generic loading API does not.

Experiments are Python. A run is a frozen configuration; identical configurations return the
stored run instead of recomputing (the contract is [`docs/benchmarking.md`](docs/benchmarking.md)).

```python
from triplum.bench.config import LLMConfig, PipelineConfig, RunConfig
from triplum.bench.report import format_summary, summary
from triplum.bench.runner import run_benchmark, runstore_path
from triplum.bench.runstore import RunStore

cfg = RunConfig(
    dataset="musique",
    pipeline=PipelineConfig(name="bm25", reader=LLMConfig(kind="fake"), top_k=5),
    n=20,
    fixture=True,  # the committed 20-question fixture; drop it to fetch the pinned files
)
run_id = run_benchmark(cfg)
with RunStore(runstore_path(cfg)) as rs:
    print(format_summary(summary(rs, [run_id])))
```

The named pipelines are plain functions over a store and a viewer, so the same retrieval runs
without the harness:

```python
from triplum.retrieve import pipelines

hits = pipelines.rrf(questions, store, viewer, embedder=embedder, k=5, candidates=50)
```

Every stage is also usable on its own: load a dataset, put it in a store, embed, retrieve with
one of the stages, read with any `LLM`. [`docs/api/index.md`](docs/api/index.md) has the module
map, the contracts that hold across modules, and a worked composition without the runner.

## The command line

`triplum` is the operator surface for the same library: fetch data, run and sweep benchmarks,
and inspect stored runs. It resolves names forgivingly (unique prefixes, typo matches, numbered
choices when ambiguous) and never prompts under `--no-input`.

```
uv run triplum data                              # every dataset and its local state
uv run triplum data fetch                        # the default protocol files, sha256-verified
uv run triplum bench run --dataset ~/papers --pipeline bm25 --reader fake   # your own folder
uv run triplum bench run --pipeline dense --dataset musique --n 20 --fixture \
    --embedder st:sentence-transformers/all-MiniLM-L6-v2 --reader fake
uv run triplum bench report                      # summary table over stored runs
uv run triplum bench inspect <run_id>            # per-question answers, passages, model calls
uv run triplum bench diff <run_a> <run_b>        # what changed and by how much
uv run marimo edit notebooks/runs.py             # browse runs in a notebook
uv run python examples/run_a_benchmark.py        # the examples/ folder: scripts and a notebook
```

The full command table, what each step does and which module does it are in
[`docs/flow.md`](docs/flow.md).

## Documentation

- [`docs/flow.md`](docs/flow.md): a run step by step; implemented versus planned.
- [`docs/api/index.md`](docs/api/index.md): module map, cross-module contracts, composition
  by hand; the per-package pages are generated from the source.
- [`docs/benchmarking.md`](docs/benchmarking.md): run identity, caching, replay, resume.
- [`docs/research/design.md`](docs/research/design.md): the decision record with rejected
  alternatives; [`docs/research/`](docs/research/README.md) holds the research notes behind it.
- [`docs/licences.md`](docs/licences.md): every third-party dataset, model and dependency.
- [`CONTRIBUTING.md`](CONTRIBUTING.md): checks, tests, fixtures, docs rules, pre-commit.

Serve the site with `uv run mkdocs serve`.

## Reference papers

- Liao, Collarana, Pack, Graß, Both, Decker, Beecks. *Best Practices in Graph Retrieval-Augmented
  Generation: A Systematic Evaluation.* SEMANTiCS 2026. The first reproduction target.
- Schmidt, Kharlamov, Paschke. *Better Be Sure: A Verification and Validation Taxonomy for
  Industrial KG Construction.* SGKi workshop at SEMANTiCS 2026. The V&V structure the evaluation
  module maps onto.

The ledger with status per paper is [`docs/research/papers.md`](docs/research/papers.md).

## License

Apache-2.0 for this repository. Third-party datasets and models keep their own terms, mapped in
[`docs/licences.md`](docs/licences.md).
