# triplum

A composable, benchmark-first Python library for document search, knowledge graphs and GraphRAG.
The library is the product: experiments should compose its capabilities directly.
Time, provenance and permissions remain design requirements; evidence must respect source access.

## Current state

The project is being rebuilt on `v2-rewrite`. Much of the earlier code and all of its documentation
were deliberately removed because the architecture and its explanation had become too confusing.
The old benchmark runner, CLI examples and documentation are not working entry points for this
checkout.

The retained foundation is generic data-loading utilities, `FrameDataset` for dataframe batches,
a disk cache with an explicit cache directory, access-control helpers and the Rust core. Orphaned
dataset adapters, store interfaces and backend, examples and the CLI entry point have been removed
along with obsolete tests. Retaining a utility does not approve its interface for the rebuild.
The previous implementation is available in Git history; it is reference material, not a restore list.

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
has one embedding vector for a chosen configuration. The
[embedding discussion](docs/specs/embedding.md) remains open. No replacement interface has been
approved yet.

Keep the upstream flow in view: dataset → loader for documents/webpages/etc. → optional OCR or
preprocessing → `Source`. Its interfaces are deferred for a later discussion.

## Intended flow

This is a map of responsibilities, not a claim that these stages are implemented or that every
step needs its own Protocol.

```text
Indexing:
Documents → Chunking → Chunks → Embedding → Vectors → Store
                          └→ Extraction → Entity resolution → Graph → Store

Answering:
Question + Store → Retrieval → Evidence → Reranking → Formatting → LLM → Answer
```

The shape of graph evidence and the contracts between these steps will be reviewed separately.
Embedding and LLM calls are shared capabilities that can be used by several steps.

## Development

[AGENTS.md](AGENTS.md) records the review process and contributor constraints. The retained suite
has 42 passing tests and 96% Python coverage with branch measurement enabled. It covers data
loading, caching, access-control helpers, pre-commit behavior and the retained Rust extension
exports. The actual pre-commit hook passes Cargo, ty, Ruff lint and formatting checks against an
isolated index containing the cleanup.

The old MkDocs configuration still refers to removed documentation, so a full documentation build
is not yet a working gate. New documentation and coverage will accompany each reviewed interface.

## License

[Apache-2.0](LICENSE) for this repository. Third-party datasets, models and code retain their own
terms; record those terms when introducing or restoring a dependency.
