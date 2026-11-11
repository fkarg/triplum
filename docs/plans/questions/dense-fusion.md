# Dense retrieval and fusion

Questions use the `DF` prefix. Process: [questions index](README.md).

## Open

### DF1. Real embedder and query/passage encoding

`ZeroEmbedder` is a placeholder; `Embedder` has no query/passage distinction, and similarity,
normalization, truncation and batching semantics are open (see the embedding spec).

First decision, prepared after P16: **where query/passage purpose belongs**. Real adapters may
select prompts or model routes, not just prepend strings. Sources: [Sentence Transformers](https://www.sbert.net/examples/sentence_transformer/applications/semantic-search/README.html),
[the E5 author's model card](https://huggingface.co/intfloat/e5-small-v2).

- Session: configure separate query and passage callables, both fitting the existing batch
  `Embedder` shape; symmetric models may use the same callable. Resources can be shared.
  Keeps consumers small and configuration in construction. Risk: callers can pair incompatible
  encoders; equal dimensions do not establish compatibility.
- Alternatives: one callable with a role per batch (one resource, but repeats role at every call);
  one object with query/document methods (discoverable pair, but a larger interface).
- Independent peer: fresh-context GPT-family fallback, exact serving model unavailable. Host
  Claude Opus 5.5 was unavailable after revoked OAuth; this is not cross-model review. Peer
  independently recommends configured callables. Attacks: distinct model routes, symmetric
  encoders, double-loading a model, incompatible pairs, future entity similarity. Prefix-only
  caller preprocessing fails the route case; a paired-method object reduces pairing accidents
  but cannot itself guarantee vector compatibility.
- Disposition: **added verification**: a future adapter must demonstrate resource sharing;
  compatibility remains explicitly unresolved before promising reusable persisted vectors.
  No replacement interface or implementation approved. Numeric/truncation/batching questions
  remain for subsequent decisions. Owner answer pending.

### DF2. Vector storage and search

No vector index or store capability exists. Needs Viewer-aware pre-filtering like the text index.

### DF3. Fusion

Fusion of several retrievers' rankings (RRF, weighted) as a block over retrieval hits.

## Answered
