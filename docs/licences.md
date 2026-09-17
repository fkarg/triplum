# Licences

## This repository

triplum is Apache-2.0. Everything here, including benchmark results, is public and used for
research only. That means non-commercial terms on third-party datasets and models are satisfied
*for this repository's own use*. It does not mean every component is free to reuse elsewhere:
the map below records the terms per component so that anyone lifting a piece of this setup into a
commercial or production context can see at a glance what travels and what does not.

Rules:

- A non-commercial or research-only component may be used here. It is marked in the map, and a
  result table that depends on one says so.
- Code with no licence file is read-only (no licence means no permission).
- The reader tier "Meta Muse Spark contributor" trains on submitted traffic; public benchmark
  questions may go through it, private corpora never.

Dates are when the licence was checked; re-check before relying on a row.

## Datasets

| component | licence | commercial reuse | checked | notes |
|---|---|---|---|---|
| HotpotQA | CC BY-SA 4.0 | yes, share-alike | 2026-09-16 | via the HippoRAG protocol files |
| MuSiQue | CC BY 4.0 | yes | 2026-09-16 | authors note possible single-hop leakage from seed datasets |
| 2WikiMultiHopQA | Apache-2.0 | yes | 2026-09-16 | gold `evidences` triples usable for extraction scoring |
| HippoRAG `reproduce/dataset` files | MIT (repo); content under the three above | yes, per content | 2026-09-16 | our corpora, hashes pinned in `hipporag.py` |
| MoreHopQA (`alabnii/morehopqa`, verified split) | CC BY 4.0 | yes | 2026-09-17 | registered as `morehopqa` |
| ECT-QA (`austinmyc/ECT-QA`) | MIT | yes | 2026-09-17 | registered as `ectqa`; 480 transcripts, local questions only |
| HotpotQA distractor dev (`hotpotqa/hotpot_qa`) | CC BY-SA 4.0 | yes, share-alike | 2026-09-17 | registered as `hotpotqa_full` |
| 2WikiMultiHopQA dev (`xanhho/2WikiMultihopQA`) | Apache-2.0 | yes | 2026-09-17 | registered as `twowiki_full`; mirror keeps `evidences`, drops Wikidata ids |
| MuSiQue full dev (`bdsaglam/musique`) | CC BY 4.0 upstream; mirror card has no licence tag | yes | 2026-09-17 | registered as `musique_full`, with unanswerable twins |
| MultiHop-RAG (`yixuantt/MultiHopRAG`) | ODC-BY | yes, attribution | 2026-09-17 | registered as `multihoprag` |
| PopQA (`akariasai/PopQA`) | none declared | check | 2026-09-17 | registered as `popqa`; no corpus |
| EntityQuestions (Princeton) | MIT | yes | 2026-09-17 | registered as `entityquestions`; test split, no corpus |
| MQuAKE (`princeton-nlp/MQuAKE`) | MIT | yes | 2026-09-17 | registered as `mquake_cf`, `mquake_t`; needs edit ingestion |
| GateMem (`Ray368/GateMem`) | CC BY 4.0 | yes | 2026-09-17 | registered as `gatemem`; needs a viewer per question |
| LongMemEval-cleaned (`xiaowu0162/longmemeval-cleaned`) | MIT | yes | 2026-09-17 | registered as `longmemeval_s`; needs a corpus per question |
| TEMPO (`tempo26/Tempo`) | CC BY 4.0 | yes | 2026-09-17 | registered as `tempo`; 2.4 GB, fetches only when named |
| GraphJudge corpora (`hhy-huang/GraphJudge`) | MIT repo; GenWiki-Hard CC0, SciERC none declared, REBEL subset CC BY-NC-SA 4.0 | GenWiki yes; SciERC check; REBEL **no** | 2026-09-17 | registered as `graphjudge_genwiki`, `graphjudge_scierc`, `graphjudge_rebel` |
| GenWiki (Edmond, MPG) | CC0 1.0 | yes | 2026-09-17 | registered as `genwiki` (test) and `genwiki_fine` |
| CaRB (`dair-iitd/CaRB`) | MIT | yes | 2026-09-17 | registered as `carb` |
| CoNLL04 (`DFKI-SLT/conll04`) | none declared | check | 2026-09-17 | registered as `conll04` |
| SciERC (SpERT release files) | none declared | check | 2026-09-17 | registered as `scierc` |
| NQ-Open (`google-research-datasets/nq_open`) | CC BY-SA 3.0 | yes, share-alike | 2026-09-17 | registered as `nq_open`; validation split, no corpus |
| AmbigQA light (UW) | CC BY-SA 3.0 | yes, share-alike | 2026-09-17 | registered as `ambigqa`; dev split, no corpus |
| Bamboogle (`chiayewken/bamboogle`, from ofirpress/self-ask) | MIT | yes | 2026-09-17 | registered as `bamboogle`; 125 questions, no corpus |
| FreshQA (freshllms/freshqa) | Apache-2.0 (repository) | yes | 2026-09-17 | registered as `freshqa`; sheet export of 2026-04-21, no corpus |
| AI2 ARC (`allenai/ai2_arc`) | CC BY-SA 4.0 | yes, share-alike | 2026-09-17 | registered as `arc_easy`, `arc_challenge`; test splits, no corpus |
| SQuAD 1.1 and 2.0 (`rajpurkar/squad`, `squad_v2`) | CC BY-SA 4.0 | yes, share-alike | 2026-09-17 | registered as `squad`, `squad_v2`; validation splits |
| BoolQ (`google/boolq`) | CC BY-SA 3.0 | yes, share-alike | 2026-09-17 | registered as `boolq`; validation split |
| QuALITY v1.0.1 (NYU) | CC BY 4.0 annotations; articles carry their own licence field (Project Gutenberg, OANC, CC BY) | yes, per article | 2026-09-17 | registered as `quality`; htmlstripped dev split |
| QASPER v0.3 (`allenai/qasper`) | CC BY 4.0 | yes | 2026-09-17 | registered as `qasper`; test split, paper text under arXiv terms |
| MetaQA (yuyuz/MetaQA, vanilla test splits and `kb.txt`) | CC BY 3.0 | yes, attribution | 2026-09-17 | registered as `metaqa`; KB verbalised per entity, triples kept |
| Text2KGBench | Apache-2.0 (`cenguix/Text2KGBench`) | yes | 2026-09-16 | LettrIA refinement: data "upon request", terms unknown |
| `GEM/web_nlg` (HF) | CC BY-NC 4.0 | **no** | 2026-09-16 | non-commercial |
| REBEL dataset | CC BY-NC-SA 4.0 | **no** | 2026-09-16 | non-commercial, share-alike |
| Re-DocRED, DocRED | see HF cards | check | 2026-09-16 | 4 of the 11 HF datasets we looked at declare no licence field |
| GraphRAG-Bench (arXiv 2506.05690, ICLR 2026) | MIT | yes | 2026-09-16 | ships `evidence_relations` |
| GraphRAG-Bench (arXiv 2506.02404) | academic-only, no redistribution | **no** | 2026-09-16 | unrelated benchmark with the same name |
| BrowseComp-Plus (`Tevatron/browsecomp-plus`, `-corpus`) | MIT | yes | 2026-09-17 | registered as `browsecomp_plus`; 4.5 GB, fetches only when named; query shards may need a HF token |
| WildGraphBench | Apache-2.0 | yes | 2026-09-16 | |
| InfoDeepSeek | CC BY-NC | **no** | 2026-09-16 | also live-web, non-reproducible |
| `Zly0523/linear-rag`, `102202132zbz/rag_test` mirrors | none declared / apache-2.0 declared | not authoritative | 2026-09-16 | a mirror cannot relicense CC BY-SA content; not used |

## Models

| component | licence | commercial reuse | checked | notes |
|---|---|---|---|---|
| OpenAI `text-embedding-3-*`, `gpt-5.6-*` | OpenAI terms of use | yes, under the terms | 2026-09-16 | outputs usable; API keys via environment only |
| Meta Muse Spark contributor tier | Meta API terms; traffic used for training | yes with care | 2026-09-16 | never route private corpora through it |
| `google/gemma-4-31B-it` | Apache-2.0 | yes | 2026-09-16 | Gemma 4 changed to Apache-2.0; earlier Gemma versions are under the Gemma ToU |
| EmbeddingGemma (300M) | Gemma Terms of Use, HF-gated | yes, under the ToU | 2026-09-16 | not Apache |
| `sentence-transformers/all-MiniLM-L6-v2` | Apache-2.0 | yes | 2026-09-16 | test and smoke embedder |
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | Apache-2.0 | yes | 2026-09-16 | test reranker |
| `BAAI/bge-small-en-v1.5`, BGE-M3 | MIT | yes | 2026-09-16 | |
| NV-Embed-v2 | CC BY-NC 4.0 | **no** | 2026-09-16 | the literature's generation-2 reference retriever; fine here, not elsewhere |
| `jinaai/jina-embeddings-v3`, v5 | CC BY-NC 4.0 | **no** | 2026-09-16 | |
| `jinaai/jina-embeddings-v4` | Qwen Research License (card corrects an earlier CC BY-NC tag) | **no** | 2026-09-16 | derived from Qwen-2.5-VL-3B |
| Qwen3-Embedding 0.6B / 4B / 8B, Qwen3-Reranker | Apache-2.0 | yes | 2026-09-16 | the local default tier of the sweep |
| `nvidia/Nemotron-3-Embed-1B` | commercial-friendly per model card | yes, under its terms | 2026-09-16 | strongest commercially licensed open model fitting 8 GB at fp16, per `embeddings.md` |
| `BAAI/bge-reranker-v2-m3` | Apache-2.0 | yes | 2026-09-16 | the fixed reranker |
| Snowflake Arctic-Embed 2.0, Nomic Embed v2, granite-embedding, DenseOn, pplx-embed | Apache-2.0 / MIT per card | yes | 2026-09-16 | details in `docs/research/embeddings.md` |
| Claude via `claude -p` | Anthropic terms | yes, under the terms | 2026-09-16 | CLI adapter, stateless invocation required |

## Code and infrastructure

| component | licence | commercial reuse | checked | notes |
|---|---|---|---|---|
| [ty](https://github.com/astral-sh/ty/blob/main/LICENSE) | MIT | yes | 2026-09-17 | development-only Python type checker |
| [Rich](https://github.com/Textualize/rich/blob/main/LICENSE) | MIT | yes | 2026-09-17 | terminal tables, wrapping and capability-aware colors |
| [pytest-cov](https://github.com/pytest-dev/pytest-cov/blob/master/LICENSE) | MIT | yes | 2026-09-16 | development-only branch coverage reporting |
| sqlite-vec | MIT / Apache-2.0 | yes | 2026-09-16 | pre-v1 |
| Oxigraph, `pyoxigraph` | MIT / Apache-2.0 | yes | 2026-09-16 | |
| LadybugDB (`lbug`, `ladybug`) | MIT | yes | 2026-09-16 | Kùzu successor |
| Neo4j Community | GPLv3 | yes as a separate process; not linkable into proprietary code | 2026-09-16 | RBAC/PBAC are Enterprise-only |
| Neo4j Graph Data Science (OpenGDS) | GPLv3; distributed plugin bundles closed code | check the bundled licence | 2026-09-16 | |
| `neo4j` Python driver | Apache-2.0 AND Python-2.0 | yes | 2026-09-16 | |
| `neo4j-graphrag` | Apache-2.0 | yes | 2026-09-16 | |
| polars, pyarrow, PyO3, pyo3-arrow, maturin, arrow-rs | MIT / Apache-2.0 | yes | 2026-09-16 | |
| sentence-transformers, fastembed | Apache-2.0 | yes | 2026-09-16 | |
| BenchmarkQED | check repo | check | 2026-09-16 | judge protocol we adopt; cite the source code |
| DIGIMON (JayLZhou/GraphRAG) | **no licence file** | **no** (read only) | 2026-09-16 | operator taxonomy read for ideas only |
| KG-Gen | MIT in `pyproject.toml`, no LICENSE file | ambiguous | 2026-09-16 | |
| HippoRAG code | MIT | yes | 2026-09-16 | |
| LightRAG, Microsoft GraphRAG, Cognee, Graphiti, ATOM/iText2KG | MIT / MIT / Apache-2.0 / Apache-2.0 / Apache-2.0 | yes | 2026-09-16 | |
| rudof (`pyrudof`) | MIT / Apache-2.0 | yes | 2026-09-16 | |
| marimo, paper-qa | Apache-2.0 | yes | 2026-09-16 | |

## How results record this

A results table that used a non-commercial component carries a footnote naming it. The run store
does not track licences; the component identity it records (model id, corpus hash, embedding spec)
is enough to look the row up here.
