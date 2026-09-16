# triplum

Composable, benchmark-first sandbox for LLM knowledge-graph work: KG construction, GraphRAG
retrieval, storage backends and evaluation. Python-first with a Rust core behind an Arrow
boundary. Bi-temporal facts and provenance-derived permissions are first-class and enforced in
the store.

Start here:

- [Flow](flow.md): what a benchmark run does step by step, which modules implement each step,
  and what is implemented versus planned.
- [Modules and interfaces](api/index.md): every module with its status, key symbols and the
  cross-module contracts, plus the API reference generated from the source.
- [Benchmarking and caching](benchmarking.md): the contract for run identity, caching, replay,
  crash recovery and inspection.
- [Design record](research/design.md): the decisions, the alternatives rejected, and the order of
  sub-projects.
- [Licences](licences.md): every third-party dataset, model and dependency with its terms.

Serve these pages locally with `uv run mkdocs serve` and open <http://127.0.0.1:8000>.
