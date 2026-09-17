# triplum

*triplum* (Latin: "triple"; also the third, independent voice in medieval polyphony) is a composable,
benchmark-first sandbox for LLM-based knowledge-graph work: KG construction from text, GraphRAG
retrieval, graph serialisation for prompts, storage backends, and thorough evaluation. Python-first,
with a Rust core wherever it is measurably worth it. Every module is usable on its own or in
composition, over one shared Arrow-native data layer.

Two things are first-class citizens from day one, because they cannot be bolted on later:

- **Bi-temporal facts.** Every fact carries validity time (when it was true in the world) and
  transaction time (when the system learned or invalidated it). Ingestion is episodic; later
  documents can invalidate earlier facts. Queries take an "as-of" on both axes.
- **Permissions derived from provenance.** Documents carry principals. A fact is visible to a viewer
  iff at least one supporting chunk is; an entity is visible iff a visible fact touches it. Filtering
  happens in the store, never post-hoc, so nothing leaks through neighbours or summaries.

This is an industry-first project, not a research project: the goal is one high-performing system
that reproduces and extends state-of-the-art techniques, measured on public and (later) private
benchmarks.

## Status

The benchmark harness for the non-graph baselines exists and runs end to end (2026-09-16). What
works: the canonical schemas (Rust core, exposed to Python), a SQLite store with viewer-filtered
BM25 and vector search, cached LLM / embedder / reranker protocols with OpenAI-compatible, CLI and
local adapters, the HippoRAG 1000-question protocol data with pinned hashes and 20-question
fixtures, five baselines (closed-book, BM25, dense, hybrid with rerank, oracle), the metrics, and a
run store that records identity, cost and timing for every run. Nothing graph-shaped yet.

```
uv sync --all-extras                        # builds the Rust extension via maturin
uv run pytest -m "not model"                 # fast, offline fixtures and fakes
uv run pytest                               # includes installed optional real-model adapters
uv run triplum data                         # local state of each supported dataset
uv run triplum data fetch                   # HippoRAG protocol files, verified by sha256
uv run triplum bench                        # recent local runs, states and available commands
uv run triplum bench run --pipeline dense --dataset musique --n 20 --fixture \
    --embedder st:sentence-transformers/all-MiniLM-L6-v2 --reader fake
uv run triplum bench report
uv run marimo edit notebooks/runs.py        # browse runs
uv run mkdocs serve                         # these docs in the browser, http://127.0.0.1:8000
uv run triplum bench show <run_id>          # exact configuration and identity of a run
uv run triplum bench rerun <run_id> --force # recompute it
uv run triplum bench run ... --resume       # finish a crashed run in place
uv run triplum bench inspect <run_id>       # per-question answers, passages, model calls
uv run triplum bench diff <run_a> <run_b>   # what changed and by how much
uv run triplum bench tail <run_id>          # progress of a running benchmark
```

## CLI discovery and test feedback

Forgiving discovery is a priority throughout the CLI. Use full names or unique prefixes:
`triplum ben insp 43a` resolves the command and run ID. Omit the run ID to choose a stored
run. Single substring or typo matches also resolve automatically; multiple matches offer numbered terminal choices;
`q`, EOF or Ctrl-C cancels. Dataset, pipeline, reader/judge and adapter-kind choices follow
the same policy. An omitted `--question` still shows all questions; a supplied question ID
is resolved within the selected run. Omitted required pipeline/dataset options offer choices.

Scripts accept exact names and single prefix/substring/typo matches but never prompt; use full names for stable
automation as new commands or runs can make prefixes ambiguous. `--no-input` explicitly
disables prompts at the root, group or prompting command. Diagnostics and prompts go to
stderr, including with `inspect --json`. Option spelling errors retain Typer's suggestions;
paths, URLs, model IDs and JSON configuration stay exact. Only the kind before `:` is
resolved in an adapter spec. The [selection contract](docs/specs/2026-09-16-cli-selection.md)
applies to new commands too.

Tests report their slowest cases. `uv run pytest -m "not model"` runs without loading real
models; `uv run pytest` also exercises optional model adapters when installed (weights may
download). For branch coverage, run `uv run pytest -m "not model" --cov
--cov-report=term-missing:skip-covered` on one line; CI measures coverage explicitly.
Coverage stays opt-in locally to keep single-test feedback quick. Match/selection behavior
lives in one focused module and tests exercise CLI workflows over temporary SQLite stores.

What a run does step by step, which module does it, and what is implemented versus planned is
in [`docs/flow.md`](docs/flow.md). Runs are identified by the hash of their exact configuration and
looked up before they are computed; expensive stages are cached and reused. The contract is in
[`docs/benchmarking.md`](docs/benchmarking.md).

Readers and judges are `--reader openai --reader-model <id>` with `OPENAI_API_KEY` (or any
OpenAI-compatible `--base-url`), or `--reader claude-cli`. The first concrete task has three threads
on this harness and one corpus set (HotpotQA, MuSiQue, 2WikiMultiHopQA):

- **Retrieval pipelines**: the baselines above, then best-practice GraphRAG per Liao et al.
  (SEMANTiCS 2026) and personalised PageRank over the KG (HippoRAG 2 style), with a
  graph-disabled ablation.
- **KG-construction variants**: open IE vs schema-based vs ontology-aware extraction, with and
  without atomic-fact decomposition, several entity-resolution strategies; measured intrinsically
  and by downstream QA delta.
- **Store comparison**: the same graph in SQLite and Neo4j, to find where a graph database starts
  to pay off for basic GraphRAG usage.
- **Embedding sweep**: `triplum bench sweep --embedders specs.json` reruns the dense baseline per
  embedding spec; the winner is pinned for the graph pipelines.

## Design in one screen

- **Data layer:** eight canonical tables (documents, document_grants, chunks, chunk_embeddings,
  entities, facts, fact_support, mentions) defined once as Arrow schemas in the Rust core crate.
  Entity names, types, aliases and resolution merges are facts, so they carry time and provenance.
  Python sees Polars DataFrames, zero-copy across PyO3. Thin row dataclasses exist for notebook
  ergonomics only.
- **Composition:** a stage is a plain callable, typed frames in and out. A pipeline is a plain
  function. Configs are frozen dataclasses whose hash goes into every run record. No DAG framework,
  no YAML.
- **LLM layer:** one protocol (messages + optional JSON schema in; text, parsed object, usage, cache
  hit out), adapters for OpenAI-compatible APIs, Anthropic, and CLI harnesses as subprocesses. A disk
  cache keyed on the full effective request makes benchmark reruns free and replay exact.
- **Stores:** one store protocol taking a `Viewer` (principals, as-of valid time, as-of recorded
  time). Permission filters run inside the indexes, before ranking; graph kernels run on the viewer's
  visible projection; no community summaries until they can be principal-scoped. Backend one is
  SQLite (FTS5 for BM25, sqlite-vec for vectors, recursive CTEs for bounded traversal, in-memory CSR
  for PageRank).
  RDF (Oxigraph) and property-graph (LadybugDB) arms follow so the same benchmark can compare them.
  DuckDB is an optional analytical arm and can read the SQLite file directly.
- **Evaluation:** EM/F1 and supporting-passage recall where gold exists; BenchmarkQED-style pairwise
  LLM judge where it does not; triple precision/recall, ontology conformance and SHACL for KG
  construction; cost and latency always. Run records live in one SQLite run store, reports are
  Polars frames.
- **Rust:** `triplum-core` (schemas, visibility logic), `triplum-index` (tantivy, usearch, PPR and
  traversal), `triplum-serialize` (GraphML, Turtle, JSON, text), `triplum-py` (PyO3 bindings). Rust
  is added where a Python implementation is the measured bottleneck or where a better crate exists.
- **Notebooks:** marimo (plain `.py`, git-diffable) over the same package; also works in Jupyter.

The full record with alternatives considered is in [`docs/research/design.md`](docs/research/design.md).

## Layout (planned)

```
crates/            Cargo workspace: triplum-core, triplum-index, triplum-serialize, triplum-py
python/triplum/    data, llm, ingest, extract, store, retrieve, generate, eval, bench
notebooks/         marimo notebooks
docs/research/     research foundation: landscape, benchmarks, stack, decisions, paper ledger
research/          SOTA monitor scripts, weekly digests, per-paper notes (planned)
```

## Reference papers

- Liao, Collarana, Pack, Graß, Both, Decker, Beecks. *Best Practices in Graph Retrieval-Augmented
  Generation: A Systematic Evaluation.* SEMANTiCS 2026. The first reproduction target.
- Schmidt, Kharlamov, Paschke. *Better Be Sure: A Verification and Validation Taxonomy for
  Industrial KG Construction.* SGKi workshop at SEMANTiCS 2026. The V&V structure the evaluation
  module maps onto.

See [`docs/research/papers.md`](docs/research/papers.md) for the ledger.

## License

Apache-2.0 for this repository. It is public and research-only, so non-commercial datasets and
models are used where they are the right tool; [`docs/licences.md`](docs/licences.md) maps every
third-party component's terms so a piece can be reused elsewhere with eyes open.
