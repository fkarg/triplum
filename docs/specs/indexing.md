# Indexing: data and transformations

**Status:** boundary discussion. Initial step contracts exist; broader replacements and enrichment
interfaces remain under owner review.

Start here to follow how source content becomes searchable. We are reviewing one boundary at a
time, beginning with documents and chunks. The categories below explain the flow; they do not
imply a class or Protocol for every step.

## What the owner has confirmed

- Support basic pipelines with no preprocessing and advanced pipelines with generated context,
  descriptions, keywords and questions.
- A chunk can have several associated strings, but **one indexed vector per chunk for a chosen
  embedding configuration**. Separate question vectors are not the requested design.
- Support knowledge graphs, hierarchical chunks, communities and summaries without requiring
  them for basic retrieval.
- Provide composable functions and classes that users can readily replace with their own.
- Review each interface with the owner after an independent Opus critique, before implementation
  or proceeding to the next interface.

Source lineage and permissions remain project requirements. Generated content must account for
all supporting sources; access cannot be inherited from just one convenient source.

## Boundary under review

The [public overview](../flow.md) owns the indexing/retrieval walkthrough and enrichment example.
Initial Source/Chunk models and conversion/chunking/embedding-text/embedding Protocols now exist;
see [Decision points](../concepts/decisions.md) for their current contracts. This draft records the
broader boundary discussion and does not approve the remaining pipeline.

- Source means identified input text. Upstream document/webpage loading, OCR and preprocessing
  interfaces are deferred; do not infer their design from the converter baseline.
- Initial chunks retain their relationship to source text. Exact immutable identity, earlier
  text versions and hierarchical containment remain open; see [Record types](record-types.md).
- Embedding preparation is independently replaceable. The initial `EmbeddingText` takes a Chunk
  and returns a string; context/enrichment storage and combination remain future decisions.
- Document containment and graph community membership are distinct. Generated content must
  preserve all supporting inputs for provenance and access, including multi-source summaries.

One substantive type decision remains:

| Option | Benefit | Cost |
| --- | --- | --- |
| Chunk means a source excerpt; summaries are separate | Clear source locations and citations | Shared indexing eventually accepts source and generated content |
| Chunk means any retrievable text, including summaries | A common downstream type | Consumers must distinguish excerpts from generated, potentially multi-source content |

**Recommendation, awaiting owner review:** reserve Chunk for a source excerpt and represent
summaries separately. This does not choose storage tables or the final summary declaration.
Embedding's remaining numerical and compatibility questions are in [its draft](embedding.md).

## Research comparisons

These are comparisons, not adopted APIs:

- [Anthropic contextual retrieval](https://www.anthropic.com/engineering/contextual-retrieval)
  prepends generated context before embedding a chunk.
- [Late chunking](https://arxiv.org/abs/2409.04701) contextualizes token embeddings before pooling
  them into chunk vectors. One vector per chunk does not require isolated chunk encoding.
- [GraphRAG indexing](https://microsoft.github.io/graphrag/index/overview/) builds graph communities
  and reports; these differ from a document's section hierarchy.
- [Ragas testset generation](https://docs.ragas.io/en/stable/concepts/test_data_generation/rag/)
  uses transformations and question synthesis for evaluation. Borrowing enrichment ideas does
  not mean putting evaluation questions into our index.

## Independent critique

Claude Opus 5.5 (`claude-opus-5-5`) reviewed this boundary through host `peer-review`.

- **Added verification requirements:** distinguish source text from index text; name the text
  version used by offsets; preserve all inputs to generated content for provenance and access;
  make the combination of index strings an explicit experiment choice. Opus tested the proposal
  against multi-document summaries, text cleaning, document context and late chunking scenarios.
- **Dissent retained:** Opus proposed a universal retrievable-unit record with provenance sets
  and mandatory recipe identity. These are not adopted. Separate source and generated-content
  contracts remain the recommendation, subject to owner review.
- **Rejected as unsupported:** the claim that generated questions work best with separate
  vectors was not measured. It does not override the owner's one-vector-per-chunk requirement.
- **Rejected as overgeneralized:** content-hash identity does not inherently break references;
  explicit immutable versions can retain them. Recipe identity alone also cannot distinguish
  different stochastic outputs of the same recipe. Identity will receive its own review.

The peer performed conceptual counterexamples, not implementation tests or web research. An
independent web-enabled researcher checked the cited designs. This review covers the boundary
proposal, not an exact Python declaration or the subsequent editorial changes to this page.
The earlier embedding review is recorded in [the embedding draft](embedding.md).
