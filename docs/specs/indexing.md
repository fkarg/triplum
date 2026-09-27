# Indexing: data and transformations

**Status: discussion draft. No replacement interface is approved or implemented.**

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

## Follow one chunk through indexing

1. **Read a source.** Obtain document text and identify where it came from.
2. **Choose a chunk.** Keep the entire document or split it into smaller pieces.
3. **Optionally enrich it.** Generate a description, keywords or questions using selected context.
4. **Prepare and embed it.** Use the original text and any selected enrichments to produce one
   vector. How multiple strings contribute to that vector is still open.
5. **Index the result.** Make the vector searchable while retaining its relationship to the chunk.

For example, a chunk might have these associated strings:

```text
Original:    "Returns are accepted within 30 days of purchase."
Description: "The returns policy for purchases from this shop."
Question:    "How long do I have to return a purchase?"
                         ↓ chosen preparation and embedding
                    One chunk vector
```

A basic experiment uses only the original text. An enriched experiment also uses the description
or question. Neither example specifies a record shape, generation prompt or vector-combination
algorithm; those are later review decisions.

## Where the other transformations fit

| Transformation | Data in → data out | Relationship to the walkthrough |
| --- | --- | --- |
| Read/parse | Source → document text and source identity | Establishes the text being processed |
| Split | Document → chunks | May preserve document sections and containment |
| Enrich | Document/chunk plus context → associated generated text | Optional; document enrichment may precede splitting |
| Prepare and embed | Selected text/context → one chunk vector | No enrichment required |
| Extract | Selected source evidence → candidate entities and relations | Can branch from original chunks, independently of embedding preparation |
| Resolve | Candidates → resolved entities and supported facts | May need evidence across the corpus |
| Group and summarize | Chunks or graph → groups and generated summaries | Summary provenance may span several documents |
| Store/index | Selected outputs → searchable text, vectors and/or graph | Persists the relationships needed to retrieve and cite evidence |

A document's section hierarchy and a graph's community membership describe different
relationships. We have not chosen how to represent either. Indexing summaries will also need an
explicit distinction between the summary being retrieved and the sources supporting it.

## Current review: source → initial chunks → embedding text

The owner's current proposal is to call the starting datatype **`Source`**: identified text from a
document, webpage or another origin, potentially carrying external IDs or links. A chunker produces
initial chunks that refer back to it. `Source` versus `Document` naming and the exact fields are
not finalized.

Keep the upstream path in view: dataset → loader for documents/webpages/etc. → optional OCR or
preprocessing → `Source`. The owner explicitly deferred this part for later discussion; no loader,
OCR or preprocessing interface is proposed here.

The next early boundary is independently replaceable preparation from chunk to embedding text:

```text
Source text → chunker → initial chunks with source references
                              ↓ original text + selected descriptions/questions/source context
                        embedding text preparation
                              ↓
                         embedding text
```

The basic preparation returns the chunk's text. Advanced preparation can use associated generated
strings and source context. Its callable signature and the shape of the resulting embedding input
remain open; the one-vector requirement still applies. No new record or Protocol is implied by
these labels.

Before drafting fields or a splitter signature, also settle what its chunk output means:

| Option | Benefit | Cost |
| --- | --- | --- |
| A chunk is an excerpt of one document; generated summaries are separate | Source locations and citations have a straightforward meaning | Shared indexing must eventually accept both source and generated content |
| A chunk is any retrievable text, including generated summaries | Downstream code can accept one general type | Consumers must distinguish source excerpts from generated, potentially multi-source content |

**Recommendation, awaiting owner review:** use “chunk” for a source excerpt and represent
summaries separately. This does not yet commit us to separate classes or storage tables.

Next, draft the exact source/chunk declarations and one chunking callable for review. Review
source identity, the text version used by offsets and optional containment together with a small
usage example. Chunk-to-embedding-text preparation is an early follow-up boundary; embedding and
graph declarations still receive their own reviews.

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
