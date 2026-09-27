# Embedding: open interface discussion

**Status: discussion draft. No replacement interface is approved or implemented.**

The current review starts with [source text and initial chunks](indexing.md). The owner proposes
`Source` as the starting datatype and chunk-to-embedding-text preparation as an early boundary.
Those names and declarations remain open. Return here once that boundary
is settled; this page preserves the embedding questions without deciding the next interface early.

## What embedding needs to do

A chunk can have original text, a description, keywords and generated questions. The owner's
requirement is **one indexed vector per chunk for a chosen embedding configuration**.
Multiple associated strings do not mean multiple separately searchable vectors.

The proposed separation is:

```text
Chunk text + selected context or enrichments
    → prepare the embedding input
    → encode
    → one indexed chunk vector
```

For a basic pipeline, preparation passes the original text through unchanged. For an enriched
pipeline, it may render the original text and generated context into one string. Combining
intermediate embeddings is another possibility, not an approved design.

Preparation should be independently replaceable. An ordinary function may be sufficient; we
have not established a need for a preparation Protocol or new supporting record.

## Two boundaries to keep distinct

- **Text encoding:** send strings to an embedding model and receive vectors. A small interface
  here can support familiar model adapters.
- **Chunk embedding:** use source text, context and selected enrichments to produce a chunk's
  vector. Advanced methods may require document context before forming individual chunk vectors.

These describe responsibilities, not two approved interfaces. A simple pipeline can directly use
text encoding. We should not force every advanced technique through isolated chunk strings.
Explicit document context is also different from the unrelated items grouped in an execution batch.

## Decisions for the embedding review

| Question | Options still open |
| --- | --- |
| How do several strings produce one vector? | Render one model input; combine intermediate representations; model-specific contextual encoding |
| Which purposes does the text interface cover? | Query/passage retrieval initially; symmetric entity similarity as well |
| Do signatures match LangChain? | Its query/document methods and list outputs; our own batch/array interface with conversion |
| What output do consumers receive? | Dense vectors initially; any later sparse or multiple-vector output needs an explicit consumer contract |

The exact declaration must then specify ordering, dimensions, similarity comparison,
normalization, empty inputs, finite/zero-vector handling, truncation and batching guarantees.
Configuration identity can be reviewed separately, but caching or persisted-vector compatibility
cannot be promised without it. This is a review checklist, not a requirement for new metadata
classes or additional methods.

## Independent critique

Claude Opus 5.5 (`claude-opus-5-5`) reviewed the initial embedding/reranking proposal via host
`peer-review --mode design`. Neither replacement interface is approved.

**Impact: changed the draft requirements.** Opus identified missing similarity semantics and
batch-independence guarantees, plus unspecified non-finite/zero-vector handling and truncation.
Those questions remain on the checklist above.

Opus checked surviving storage schemas and deleted adapter/cache code in Git history to challenge
float32, dimension metadata and identity deferral. It did not run real models or verify numerical
batch drift. Its claim that public dimension metadata cannot be removed is not accepted as settled:
the old store's needs do not determine the new interface; dimensions can also come from outputs.
This review does not approve the eventual declaration or the subsequent editorial changes here.

External comparisons, not adopted APIs:

- [Sentence Transformers](https://sbert.net/docs/package_reference/sentence_transformer/model.html)
  supports distinct query/document encoding and configurable output behavior.
- [LangChain's embedding interface](https://reference.langchain.com/python/langchain-core/embeddings/embeddings/Embeddings)
  does not require dimension metadata. Matching its signatures remains an open compatibility choice.
