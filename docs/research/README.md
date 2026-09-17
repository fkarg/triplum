# Research foundation

The research notes behind the [design record](design.md). The first set was assembled on
2026-09-16 at SEMANTiCS 2026 in Ghent, before any code; the benchmark notes were extended on
2026-09-17 as datasets were registered. Each note carries its own snapshot date: versions and
statuses hold as of that date, and anything marked *(unverified)* was reported by a research
pass and not checked against a primary source.

| file | what |
|---|---|
| [design.md](design.md) | Decision record: goals, the ten design decisions with rejected alternatives, sub-project order |
| [landscape.md](landscape.md) | Existing GraphRAG / LLM-KG frameworks, what to take from each, reference-paper status |
| [benchmarks.md](benchmarks.md) | Every registered dataset and what its registration decided; the HippoRAG 1000-question protocol and metrics; reference numbers by generation; candidates not registered, by family, with the reason; loader consequences and open questions |
| [embeddings.md](embeddings.md) | Embedding models 2026, API vs local on Apple Silicon, rerankers, the sweep list |
| [kg-construction.md](kg-construction.md) | Survey of LLM-based ontology and KG construction (2024–2026): approaches, benchmarks, what we implement as variants |
| [kg-construction-nonllm.md](kg-construction-nonllm.md) | Non-LLM extraction stacks as of 2026-09-17 (NER, relations, coreference, resolution, linking, temporal, decomposition) with licences, sizes and speeds; the deterministic baseline the extraction spec adopts |
| [store-comparison.md](store-comparison.md) | Methodology for the SQLite vs Neo4j comparison: workloads, scales, what to measure |
| [temporal-and-permissions.md](temporal-and-permissions.md) | Bi-temporal facts and provenance-derived permissions: literature, pitfalls, schema recommendation |
| [storage-sqlite.md](storage-sqlite.md) | SQLite as first store: FTS5, sqlite-vec, recursive CTEs, temporal/ACL indexing, Arrow interop, proposed DDL |
| [rust-stack.md](rust-stack.md) | Crates and Python packages we build on, with status |
| [sota-discovery.md](sota-discovery.md) | Sources, APIs and the planned monitor for finding new techniques |
| [papers.md](papers.md) | Paper ledger with status |
| [naming.md](naming.md) | Why triplum, and the collision sweep |
| [fact-check-2026-09-16.md](fact-check-2026-09-16.md) | Verification log for claims in the other files |
