# triplum

Triplum is a Python library being rebuilt for composable document search, knowledge graphs and
GraphRAG experiments. The aim is to make basic baselines and advanced pipelines understandable,
measurable and easy to customize with your own functions and classes.

## Start here

Read **[Indexing and retrieval](flow.md)** to follow source material into searchable evidence,
then follow a question through retrieval to an answer.

## Rebuild status

The retained Python foundation provides generic data loading, dataframe batching and caching.
The Rust core is separate; the Python package does not build or link a Rust extension. An
end-to-end pipeline is not yet available.

The current focus is identified source text, initial chunks and preparation of embedding text.
The overview explains those responsibilities and how they connect to retrieval. The indexing steps
have first Protocol contracts with trivial reference implementations; see Core Concepts.
