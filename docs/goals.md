<!--
Owner-maintained. Agents: read this page before planning work and whenever a decision depends on
project direction. Do not edit it unless the owner explicitly asks for a change to this page.
-->

# Goals

triplum is a composable, benchmark-first Python library for document ingestion, search,
knowledge graphs and GraphRAG. It exists to answer a research question with measurements:
which indexing and retrieval techniques work, on which data, and at what cost. In particular,
when does a graph help, and when does it not?

## What the library provides

1. **Interfaces** for every relevant step of ingestion, indexing and retrieval: loading and
   conversion, chunking, enrichment, embedding, text/vector/graph indexing, retrieval, reranking,
   evidence formatting and answering. Each step has a small, typed contract.
2. **Blocks** that implement those interfaces and can be combined freely. Composability is the
   core of the library: a pipeline is ordinary Python calling blocks, and replacing one block
   must not require changing the others.
3. **Standard implementations** of each step, so that a working pipeline exists before anyone
   writes their own block. Together they form semi-complete pipelines that an experiment changes
   one step at a time.
4. **Reproductions of common recent papers**, built from the same blocks, so a technique can be
   compared against others and against baselines with little effort.

The library is the product. Every capability is importable and composable without the command
line. The command line is the operator interface for repetitive tasks: downloading and managing
datasets and models, managing the cache, launching benchmark runs, and inspecting results,
stores and the environment. Each command is a thin layer over importable library functions;
pipelines are composed in Python, not configured through command-line options.

## Benchmarks and baselines

Comparisons run on public benchmarks first, especially multi-hop question answering, and later
on the owner's own corpora (papers, then podcast and video transcripts). Baselines come before
novelty: results are compared against closed-book, BM25, dense, fusion, oracle-passage and
non-LLM extraction baselines where applicable. Results report answer quality, retrieval quality
and indexing cost, with everything that can change an answer recorded in the run's identity.

## Rapid experimentation and benchmark runs

These are two different modes with different requirements:

- **Experimentation** uses the optional computation cache. Expensive intermediate results
  (conversion, embeddings, extraction, LLM calls) are reused while one step is being changed, so
  iterating on a step is fast.
- **Benchmark runs** do not use the cache: they neither read nor write it. A benchmark reports
  the full cost of a pipeline, computed from scratch.
- **Stochastic runs** are reproducible. A benchmark may repeat a pipeline several times (for
  example ten runs) with randomness derived deterministically from one seed, so the whole set of
  runs can be repeated exactly. Components that cannot honour a seed, such as some hosted models,
  are recorded as such.

## Requirements that shape the design

- Every expensive step works with an empty cache, and caching never changes a result.
- Evidence respects access: reads are made for a viewer, and derived content never widens the
  access of its sources.
- Facts carry time: history is retained rather than overwritten.
- Provider calls go through one LLM interface; pipeline code does not call provider SDKs directly.
- Python is the user surface. Rust is used only where Python is a measured bottleneck.

## Documentation

High-quality documentation is a goal in its own right, modelled on the
[FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/): one page per concept, introduced in
order, each with a purpose, a small runnable example and then the details a reader needs. An
advanced section may combine concepts or go deeper. Exhaustive signatures belong in the
generated API reference.

## Not goals for now

- Multi-machine deployment or serving infrastructure.
- A graphical or web interface. The command line is the operator interface.
- A public Rust API.
