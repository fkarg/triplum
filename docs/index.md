# triplum

Triplum is a Python library being rebuilt for composable document search, knowledge graphs and
GraphRAG experiments. The aim is to make basic baselines and advanced pipelines understandable,
measurable and easy to customize with your own functions and classes.

## Start here

Read **[Indexing and retrieval](flow.md)** to follow source material into searchable evidence,
then follow a question through retrieval to an answer.

## Rebuild status

Generic data-loading utilities, dataframe batching, caching, access-control helpers and a Rust
core remain. An end-to-end pipeline is not yet available, and no replacement interface is approved.

The current focus is identified source text, initial chunks and preparation of embedding text.
The overview explains those responsibilities and how they connect to retrieval; exact interfaces
are still being defined.
