# Paper ledger

Papers we intend to reproduce, borrow from, or evaluate against. Status values: candidate, reading,
adopting, rejected. The `research/papers/` per-paper notes are planned; until they exist, the notes
column holds the essentials.

| paper | venue | status | notes |
|---|---|---|---|
| Liao, Collarana, Pack, Graß, Both, Decker, Beecks. *Best Practices in Graph Retrieval-Augmented Generation: A Systematic Evaluation* | SEMANTiCS 2026 (Ghent, 16 Sept 2026) | adopting | Reproduction target one. Three stages: graph-based indexing, graph-guided retrieval, graph-enhanced generation. Axes: chunking, embedding model, extraction prompt, entity resolution, retriever, traversal depth, reranker, graph representation format. Findings: hierarchical chunking at 512 tokens, schema-based extraction prompts, combined hypothetical-question + entities retriever with cross-encoder rerank, GraphML (code-like) representation. Datasets: MSMARCO, HotpotQA, a legal corpus; applied to EU CRR/CRD IV. Win rates vs Naive / HyDE / Hybrid RAG: 60.6 / 58.0 / 67.4 % by LLM judge on comprehensiveness, diversity, empowerment, correctness; open-source models. No code found as of 2026-09-16. |
| Schmidt, Kharlamov, Paschke. *Better Be Sure: A Verification and Validation Taxonomy for Industrial KG Construction* | SGKi workshop at SEMANTiCS 2026 (CEUR, CC BY 4.0) | adopting | Five V&V dimensions: evaluation artefact (syntax / ontology / semantic facts), reference basis (dataset / expert review / model- or rule-based), perspective (intrinsic / extrinsic), executive (manual / algorithmic / neural), temporal execution (runtime / post-hoc / iterative). Applied to 50 manufacturing reports. Our `eval` module labels every evaluator with its position in this taxonomy. |
| Tiwari et al. *Ontology-Aware Prompting for KG Construction from Text* | SEMANTiCS 2026, same session as Liao | candidate | Evaluated on Text2KGBench; code reported at anonymous.4open.science (unverified). |
| Edge et al. *From Local to Global: A Graph RAG Approach to Query-Focused Summarization* (arXiv 2404.16130) | 2024 | adopting (judge protocol) | Origin of the pairwise judge on comprehensiveness, diversity, empowerment, with directness as control. Community summaries and global search. |
| Microsoft *BenchmarkQED* | 2025 | adopting (tooling) | AutoQ (local / global / data-linked question synthesis), AutoE (pairwise judge plus correctness with ground truth), AutoD (dataset sampling). Canonical implementation of the head-to-head protocol Liao et al. use. |
| Gutiérrez et al. *HippoRAG 2* | 2025 | adopting | OpenIE to KG plus personalised PageRank; pipeline four in the harness. |
| Zhou et al. *In-depth Analysis of Graph-based RAG in a Unified Framework* (DIGIMON) | VLDB 2025 | reading | 16 operators reproducing nine methods; the operator taxonomy is a checklist for our retrieve module. |
| *GraphRAG-Bench: When to use Graphs in RAG* (GraphRAG-Bench/GraphRAG-Benchmark) | ICLR 2026 (unverified) | candidate | Novel and medical corpora, four task levels, standard eval code. A second, unrelated GraphRAG-Bench (arXiv 2506.02404, 16 disciplines) shares the name; cite by id. |
| Han et al. *RAG vs GraphRAG: A Systematic Evaluation* (arXiv 2502.11371) | 2025, v3 Mar 2026 | reading | Code at haoyuhan1/RAGvsGraphRAG. |
| *Unbiased Evaluation Framework for GraphRAG* (arXiv 2506.06331) | 2025 | candidate | |
| *WildGraphBench* (arXiv 2602.02053) | 2026 | candidate | |
| *Do We Still Need GraphRAG?* (arXiv 2604.09666) | 2026 | candidate | |
| *Use Graph When It Needs* (arXiv 2602.03578) | 2026 | candidate | Reports GraphRAG underperforming vanilla RAG on real queries; motivates the per-corpus auto-benchmark. |
| Rasmussen et al. *Zep: A Temporal Knowledge Graph Architecture for Agent Memory* (arXiv 2501.13956) | 2025 | reading | Bi-temporal edge model with four timestamps and flat episode provenance; what it lacks is in `temporal-and-permissions.md`. |
| Lairgi et al. *ATOM: AdapTive and OptiMized dynamic temporal KG construction using LLMs* (arXiv 2510.22590) | Findings of EACL 2026 | adopting (atomic-fact decomposition) | Dual-time 5-tuples (observation vs validity time), atomic-fact decomposition before extraction, parallel per-document TKGs merged by cosine similarity. Benchmarks against iText2KG and Graphiti. |
| Text2KGBench (ISWC 2023; repo `cenguix/Text2KGBench`, Apache-2.0) and the LettrIA refinement (CEUR Vol-4041 paper 3) | 2023 / 2025 | adopting (V&V) | Wikidata-TekGen (10 ontologies, 13,474 sentences) and DBpedia-WebNLG (19 ontologies, 4,860 sentences); triple P/R/F1, ontology conformance, hallucination. The LettrIA paper documents ontological flaws but links **no** dataset or repo ("available upon request"); ask the authors, else apply their fixes ourselves. Note `GEM/web_nlg` on HF is CC BY-NC. |
| LinearRAG | ICLR 2026 | candidate | Prepackaged multi-hop corpora at HF `Zly0523/linear-rag`. |
| Youtu-GraphRAG | ICLR 2026 | candidate | |

Datasets, HF ids and licenses are in [`benchmarks-multihop-qa.md`](benchmarks-multihop-qa.md).
