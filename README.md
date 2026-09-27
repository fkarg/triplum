# triplum

A composable, benchmark-first Python library for document search, knowledge graphs and GraphRAG.
The library is the product: experiments should compose its capabilities directly.
Time, provenance and permissions remain design requirements; evidence must respect source access.

## Current state

The project is being rebuilt on `v2-rewrite`. Much of the earlier code and all of its documentation
were deliberately removed because the architecture and its explanation had become too confusing.
The old benchmark runner, CLI examples and documentation are not working entry points for this
checkout.

Source files remain for data loading, datasets, caching and storage, but some import deleted
modules. Their presence does not mean those subsystems work or that their interfaces are approved
for the rebuild. Existing tests and configuration also retain references to removed code.
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
Do not restore an entire subsystem to make one interface work.

**Current review:** `Embedder`, starting with query and passage encoding. Its signatures and
metadata requirements are still proposals. [The discussion draft](docs/specs/embedding.md) records
the open questions and Opus critique. No replacement interface has been approved yet.

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

[AGENTS.md](AGENTS.md) records the review process and contributor constraints. Documentation and
checks will be re-established alongside the interfaces they describe. Remaining build and test
configuration should not be taken as evidence that the full project currently passes its checks.

## License

[Apache-2.0](LICENSE) for this repository. Third-party datasets, models and code retain their own
terms; record those terms when introducing or restoring a dependency.
