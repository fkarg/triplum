# Landscape: GraphRAG and LLM-KG frameworks (September 2026)

What exists, what each is good for, and what we take from it. Snapshot taken 2026-09-16 by a
web research pass; star counts and versions are as seen that day. Items marked *(unverified)* were
reported by the research pass but not re-checked against a primary source; see
[`fact-check-2026-09-16.md`](fact-check-2026-09-16.md) for the verification log.

## Summary

- The niche "composable sandbox with evaluation, temporal facts and permissions" is open. Nothing
  found combines those.
- The two best pipeline designs to learn from are **neo4j-graphrag-python** (component DAG with
  splitter, embedder, schema builder, extractor, resolvers, writer) and **DIGIMON** (19 operators in
  five categories reproducing nine GraphRAG methods, used by GraphRAG-Bench).
- The most-used library, **LightRAG**, is a monolithic class with open data-integrity bugs.
  **Microsoft GraphRAG** is officially in maintenance mode.
- The temporal precedents are **Graphiti** (Zep) and **ATOM** (iText2KG's successor). Worth reading,
  not depending on.
- Rust-based attempts exist (graphrag-rs, oxirs-graphrag) but are solo-author alphas.

## Frameworks

| Framework | Language / license | Status (Sept 2026) | Unit of composition | What we take / what to avoid |
|---|---|---|---|---|
| [Microsoft GraphRAG](https://github.com/microsoft/graphrag) | Python / MIT | README: "largely in maintenance mode, and won't be accepting new PRs or implementing new features" (verified 2026-09-16). v3.x removed NetworkX. | DataFrame "workflows" over table-provider and vector-store abstractions | Reference for community summaries and global search. Full reindex on new documents. LiteLLM supply-chain issue in their tracker (#2289). |
| [LightRAG](https://github.com/HKUDS/LightRAG) | Python / MIT (verified) | ~39.7k stars, EMNLP 2025, continuous merges, no versioned releases | One `LightRAG` class; pluggable KV / vector / graph storage | Read for the local/global dual-level retrieval idea. Sept 2026 issues: embedding-dim change fails open on every backend (#3978), backend-migration inconsistencies (#3963), multi-minute queries beyond ~1k nodes (#2837), sync calls in async paths. |
| [nano-graphrag](https://github.com/gusye1234/nano-graphrag) | Python / MIT | Dormant since v0.0.8 (Oct 2024) | ~1100 lines, async, swappable storage classes | Good to read; LightRAG descends from it. Do not depend on. |
| [HippoRAG 2](https://github.com/OSU-NLP-Group/HippoRAG) | Python / MIT | 2.0.0-alpha.4 on pip; README updated July 2026 | OpenIE, KG, personalised PageRank (igraph); `main.py` reproduction script | The PPR-over-KG pipeline we reproduce. Research code with heavy deps (vllm, gritlm). Known weakness: query-entity extraction errors (per DIGIMON's analysis). |
| [Cognee](https://github.com/topoteretes/cognee) | Python / Apache-2.0 | 1.5.4 (2026-09-04), active | `Task` + `run_pipeline` (add, cognify, memify, search); pydantic graph models | Closest existing "pipeline-first" design, positioned as agent memory. |
| [Graphiti](https://github.com/getzep/graphiti) | Python / Apache-2.0 | v0.30.2 (2026-09-08); Zep concentrated its open-source effort here after stopping Zep CE (the `getzep/zep` repo is repurposed for cloud examples, not archived) | Episodes into a bi-temporal KG on Neo4j 5.26+, FalkorDB, Amazon Neptune; Kùzu backend deprecated | Bi-temporal edge model; see `temporal-and-permissions.md` for what it lacks. ATOM (Findings of EACL 2026, arXiv 2510.22590) benchmarks against it. |
| [kotaemon](https://github.com/Cinnamon/kotaemon) | Python / Apache-2.0 | v0.12.0 (May 2026), slow | UI app wrapping nano-graphrag, LightRAG, MS GraphRAG | An app, not a library. |
| [LlamaIndex PropertyGraphIndex](https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/) | Python / MIT | Active | `kg_extractors` (TransformComponent) + sub-retrievers + `PropertyGraphStore` | Cleanest extractor/retriever separation in a mainstream framework; tied to the LlamaIndex node model. |
| LangChain `LLMGraphTransformer` | Python / MIT | `langchain-experimental` archived 2026-05-26; lives on in [`langchain-neo4j`](https://reference.langchain.com/python/langchain-neo4j/graph_transformers/llm/LLMGraphTransformer) | Document to GraphDocument | Migrate imports if ever used. |
| [neo4j-graphrag-python](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html) | Python / Apache-2.0 | 1.19.0 (2026-08-26); Neo4j 2026.02, Cypher 25 | `Pipeline` DAG of components; `SimpleKGPipeline`; YAML/JSON config | Best-designed KG-construction pipeline. Entity resolvers: exact, fuzzy (RapidFuzz), spaCy semantic. Neo4j-only sink. |
| [iText2KG / ATOM](https://github.com/AuvaLab/itext2kg) | Python / Apache-2.0 | Active (last push 2026-09-04); hosts iText2KG (WISE 2024), ATOM (Findings of EACL 2026) and C-Unseen | Atomic-fact distiller, extractor, matcher; dual-time 5-tuples | Temporal extraction reference; the atomic-fact decomposition step is adopted (design D3). |
| [KG-Gen](https://github.com/stair-lab/kg-gen) | Python / MIT declared in `pyproject.toml` only, **no LICENSE file** | NeurIPS 2025; PyPI 0.4.0 from 2025-09-30, repo last push 2026-03-24 | DSPy + LiteLLM; ships the MINE evaluation dataset | Simple text-to-KG baseline with its own eval set. |
| [RAGFlow](https://github.com/infiniflow/ragflow) | Python / Apache-2.0 | ~90k stars, very active | Monolith platform (Elasticsearch or Infinity, Redis, MySQL, MinIO) | Not composable. Sept 2026: KG toggle regression in 0.27 (#19379). |
| [DIGIMON](https://github.com/JayLZhou/GraphRAG) ([VLDB 2025](https://www.vldb.org/pvldb/vol18/p5623-zhou.pdf)) | Python / **no LICENSE file** (all rights reserved by default; verified 2026-09-16) | ~1.5k stars; last commit 2025-07-01 | 19 operators (entity, relationship, chunk, subgraph, community) composed via YAML to reproduce RAPTOR, KGP, DALK, HippoRAG, G-Retriever, ToG, LightRAG, MS GraphRAG, FastGraphRAG | The closest academic precedent for "one framework, many methods". Used by GraphRAG-Bench. **Do not copy code**: no licence means no permission. Read for the operator taxonomy only. |
| Newer entrants | | | | [ApeRAG](https://github.com/apecloud/ApeRAG) (Apache-2.0, modified LightRAG plus entity normalisation), [fast-graphrag](https://github.com/circlemind-ai/fast-graphrag) (MIT, PPR), LinearRAG (ICLR 2026), [Youtu-GraphRAG](https://github.com/TencentCloudADP/youtu-graphrag) (Tencent, ICLR 2026), LazyGraphRAG is an experimental internal-only Microsoft fork; the public repo offers fast indexing plus DRIFT search instead. *(licences, venues and the LazyGraphRAG status checked against the primary pages on 2026-09-17)* |

## Rust-based

- [graphrag-rs / graphrag-core](https://github.com/automataIA/graphrag-rs): MIT, ~520 stars, five-crate
  workspace, eight embedding providers, LanceDB/Qdrant/Neo4j sinks, `graphrag-py` via maturin. Solo
  author; marketing claims ("99% cost savings") to be treated sceptically. Useful as a layout
  reference for a Rust workspace with Python bindings.
- [oxirs-graphrag](https://crates.io/crates/oxirs-graphrag): RDF/SPARQL-native, Louvain/Leiden, part of
  OxiRS, updated July 2026.
- `rune-chain-knowledge-graph`: minimal triple extraction.

None is a composable sandbox with evaluation.

## Reference paper status

**Liao et al., SEMANTiCS 2026.** No code repository found on 2026-09-16 (title returns nothing on
arXiv, OpenAlex or Semantic Scholar; the talk is the day of the search). The same group's Semantic
Web Journal submission "Graph RAG in the Wild" (swj3862, major revision Nov 2025) was criticised by
reviewers for no code or data and LLM-judge-only evaluation, so expect to reconstruct the setup from
the paper text. The first author's GitHub (`noworneverev`) holds `graphrag-visualizer` and
`graphrag-api`, both Microsoft-GraphRAG tooling. Action: ask the authors at the conference for code
and the legal-corpus setup.

**Adjacent talk in the same session:** Tiwari et al., *Ontology-Aware Prompting for KG Construction
from Text*, evaluated on Text2KGBench, code at
the official implementation is [dice-group/ontology-aware-kg-construction](https://github.com/dice-group/ontology-aware-kg-construction) (GPL-3.0; evaluated on Text2KGBench; the anonymous 4open.science link it replaced is no longer reachable). Directly relevant to
the V&V sub-project.

## Awesome lists

- [DEEP-PolyU/Awesome-GraphRAG](https://github.com/DEEP-PolyU/Awesome-GraphRAG)

## Sources

Programme and paper: <https://2026-eu.semantics.cc/page/programme>,
<https://www.semantic-web-journal.net/content/graph-rag-wild-insights-and-best-practices-real-world-applications>,
<https://github.com/noworneverev>.

Framework pages are linked inline. Issue references: LightRAG #3978, #3963, #2837; Microsoft GraphRAG
#2289; RAGFlow #19379; langchain-experimental #87.
