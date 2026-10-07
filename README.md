# triplum

A composable, benchmark-first Python library for document search, knowledge graphs and GraphRAG.
The library is the product: experiments should compose its capabilities directly.
Time, provenance and permissions remain design requirements; evidence must respect source access.

## Current state

The rebuild continues on `main` after starting on `v2-rewrite`. Much of the earlier code and all
of its documentation were deliberately removed because the architecture and its explanation had
become too confusing.
The old benchmark runner, CLI examples and documentation are not working entry points for this
checkout.

The Python library includes data-loading utilities, source and chunk records, indexing steps,
memory and SQL record stores, and a disk cache with an explicit cache directory. The package uses
`uv_build`. The Rust core remains in an independent Cargo workspace; installing the Python package
does not build or link it.

Retaining a utility does not approve its interface for the rebuild. The previous implementation
is available in Git history; it is reference material, not a restore list.

## How we are rebuilding

We review **one interface at a time**, keeping the owner closely involved:

1. Explain the step's purpose and where it fits in the data flow.
2. Draft its exact Python signature, input/output types and behavioral guarantees.
3. Explain each necessary supporting type at first use and show a small usage example.
4. Have Claude Opus critique the draft; record disagreements and what changed.
5. Have the owner review the documentation and interface declaration in detail.
6. Proceed to implementations or the next interface only after the owner's approval.

Keep drafts clearly marked as proposals. Prefer simple functions and independent protocols;
add classes, records or inheritance only when a concrete requirement warrants them.
Do not restore an entire subsystem to make one interface work. Commit coherent, verified changes
periodically as the work progresses.

**Current review:** [indexing data and transformations](docs/specs/indexing.md), starting with
source content and initial chunks. The owner proposes `Source` for identified input text, followed
by chunking and independently replaceable preparation of embedding text; names and declarations
remain open. A chunk can have separate original text, descriptions and generated questions, but
has one embedding vector for a chosen configuration. The owner has decided to keep `Source` and
`Chunk` in separate files as backend-agnostic Pydantic records and develop barebones pipelines
incrementally. The indexing steps are `Protocol` contracts in `triplum.steps` (`Converter`,
`Chunker`, `EmbeddingText`, `Embedder` with batched numpy vectors), each with a trivial reference
implementation. Storage mappings live separately from the records; see the
[store guide](docs/infrastructure/store.md) for the current implementations and guarantees.

Keep the upstream flow in view: dataset → loader for documents/webpages/etc. → optional OCR or
preprocessing → `Source`. Its interfaces are deferred for a later discussion.

## Indexing and retrieval

[Indexing and retrieval](docs/flow.md) explains how source material becomes searchable and how
queries become answers. It covers basic pipelines, optional enrichment, graph construction and
summaries, and distinguishes the intended boundaries from implemented functionality.

## Development

[AGENTS.md](AGENTS.md) records the review process and contributor constraints;
[CONTRIBUTING.md](CONTRIBUTING.md) lists the checks. Use `uv sync` for Python, then run tests with
coverage, type checking and Ruff. Check and test the independent Rust workspace with Cargo.
Use the check output and CI results for current test counts, coverage and verification status.

Build the documentation with `uv run mkdocs build --strict`, or preview it with
`uv run mkdocs serve`. New documentation and coverage accompany each reviewed interface.

## License

[Apache-2.0](LICENSE) for this repository. Third-party datasets, models and code retain their own
terms; record those terms when introducing or restoring a dependency.
