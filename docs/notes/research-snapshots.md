# Research snapshots to revisit

Snapshot 2026-09-24. These dated surveys informed the first design. They are historical evidence,
not current implementation contracts or current model recommendations. Read the full version
with `git show dfc0e62:docs/research/<file>.md`. Recheck primary sources at the relevant design
gate, then remove the row. The live decisions are in [design.md](../research/design.md).

| File | Revisit when |
|---|---|
| `benchmarks.md` | selecting a new dataset or evaluation protocol |
| `embeddings.md` | choosing the embedder sweep for layer 2 and sub-project 2d |
| `fact-check-2026-09-16.md` | checking an old source claim |
| `ingestion-sources.md` | designing owner-corpus ingestion or transcription |
| `kg-construction-nonllm.md` | comparing a new extractor with the baseline |
| `kg-construction.md` | designing LLM extraction variants |
| `landscape.md` | comparing framework approaches |
| `llm-adapter-pydantic-ai.md` | designing the layer 3 adapter against its then-current API |
| `naming.md` | reviewing the original naming decision |
| `rust-stack.md` | changing the Rust/Python boundary or build stack |
| `sota-discovery.md` | implementing the research monitor |
| `storage-sqlite.md` | designing a new store boundary; its proposed schema is superseded by D2–D4 |
| `store-comparison.md` | designing the measured SQLite/Neo4j comparison |
| `temporal-and-permissions.md` | implementing temporal/ACL fixtures; its proposed schema is superseded by D2–D4 |
