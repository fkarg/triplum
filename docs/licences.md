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

Re-check upstream terms before relying on a row; Git history records when each entry changed.

## Datasets

| component | licence | commercial reuse | notes |
|---|---|---|---|
| HotpotQA | CC BY-SA 4.0 | yes, share-alike | via the HippoRAG protocol files |
| MuSiQue | CC BY 4.0 | yes | authors note possible single-hop leakage from seed datasets |
| 2WikiMultiHopQA | Apache-2.0 | yes | gold `evidences` triples usable for extraction scoring |
| HippoRAG `reproduce/dataset` files | MIT (repo); content under the three above | yes, per content | our corpora, hashes pinned in `hipporag.py` |
| MoreHopQA (`alabnii/morehopqa`, verified split) | CC BY 4.0 | yes | registered as `morehopqa` |
| ECT-QA (`austinmyc/ECT-QA`) | MIT | yes | registered as `ectqa`; 480 transcripts, local questions only |
| HotpotQA distractor dev (`hotpotqa/hotpot_qa`) | CC BY-SA 4.0 | yes, share-alike | registered as `hotpotqa_full` |
| 2WikiMultiHopQA dev (`xanhho/2WikiMultihopQA`) | Apache-2.0 | yes | registered as `twowiki_full`; mirror keeps `evidences`, drops Wikidata ids |
| MuSiQue full dev (`bdsaglam/musique`) | CC BY 4.0 upstream; mirror card has no licence tag | yes | registered as `musique_full`, with unanswerable twins |
| MultiHop-RAG (`yixuantt/MultiHopRAG`) | ODC-BY | yes, attribution | registered as `multihoprag` |
| PopQA (`akariasai/PopQA`) | none declared | check | registered as `popqa`; no corpus |
| EntityQuestions (Princeton) | MIT | yes | registered as `entityquestions`; test split, no corpus |
| MQuAKE (`princeton-nlp/MQuAKE`) | MIT | yes | registered as `mquake_cf`, `mquake_t`; needs edit ingestion |
| GateMem (`Ray368/GateMem`) | CC BY 4.0 | yes | registered as `gatemem`; needs a viewer per question |
| LongMemEval-cleaned (`xiaowu0162/longmemeval-cleaned`) | MIT | yes | registered as `longmemeval_s`; needs a corpus per question |
| TEMPO (`tempo26/Tempo`) | CC BY 4.0 | yes | registered as `tempo`; 2.4 GB, fetches only when named |
| GraphJudge corpora (`hhy-huang/GraphJudge`) | MIT repo; GenWiki-Hard CC0, SciERC none declared, REBEL subset CC BY-NC-SA 4.0 | GenWiki yes; SciERC check; REBEL **no** | registered as `graphjudge_genwiki`, `graphjudge_scierc`, `graphjudge_rebel` |
| GenWiki (Edmond, MPG) | CC0 1.0 | yes | registered as `genwiki` (test) and `genwiki_fine` |
| CaRB (`dair-iitd/CaRB`) | MIT | yes | registered as `carb` |
| CoNLL04 (`DFKI-SLT/conll04`) | none declared | check | registered as `conll04` |
| SciERC (SpERT release files) | none declared | check | registered as `scierc` |
| pypdf 6 | BSD-3-Clause | yes | PDF text layer for local-file corpora |
| python-docx 1.2 (lxml BSD-3-Clause) | MIT | yes | Word documents for local-file corpora |
| spaCy 3.8 | MIT | yes | `rules` extractor: tokenisation, NER, dependency parse; extra `extract` |
| spaCy `en_core_web_sm` 3.8.0 | MIT | yes | pinned by wheel URL; trained on OntoNotes 5 (LDC terms cover the training data, not the released weights) |
| RapidFuzz 3 | MIT | yes | `fuzzy` entity resolver |
| dateparser 1.4 | BSD-3-Clause | yes | literal date parsing in the `rules` extractor, absolute dates only |
| GLiNER 0.2 and `gliner-community/gliner_small-v2.5` | Apache-2.0 (library and v2.5 weights) | yes | `small_model` extractor spans; extra `extract-models`; revision pinned in `extract/small_model.py` |
| GLiREL 1.2 and `jackboyla/glirel-large-v0` | package Apache-2.0; weights declared CC BY-NC-SA 4.0 in the model prose | **no** for the weights | `small_model` extractor relations; research-only here, recorded per the doctrine in AGENTS.md |
| NQ-Open (`google-research-datasets/nq_open`) | CC BY-SA 3.0 | yes, share-alike | registered as `nq_open`; validation split, no corpus |
| AmbigQA light (UW) | CC BY-SA 3.0 | yes, share-alike | registered as `ambigqa`; dev split, no corpus |
| Bamboogle (`chiayewken/bamboogle`, from ofirpress/self-ask) | MIT | yes | registered as `bamboogle`; 125 questions, no corpus |
| FreshQA (freshllms/freshqa) | Apache-2.0 (repository) | yes | registered as `freshqa`; sheet export, no corpus |
| AI2 ARC (`allenai/ai2_arc`) | CC BY-SA 4.0 | yes, share-alike | registered as `arc_easy`, `arc_challenge`; test splits, no corpus |
| SQuAD 1.1 and 2.0 (`rajpurkar/squad`, `squad_v2`) | CC BY-SA 4.0 | yes, share-alike | registered as `squad`, `squad_v2`; validation splits |
| BoolQ (`google/boolq`) | CC BY-SA 3.0 | yes, share-alike | registered as `boolq`; validation split |
| QuALITY v1.0.1 (NYU) | CC BY 4.0 annotations; articles carry their own licence field (Project Gutenberg, OANC, CC BY) | yes, per article | registered as `quality`; htmlstripped dev split |
| QASPER v0.3 (`allenai/qasper`) | CC BY 4.0 | yes | registered as `qasper`; test split, paper text under arXiv terms |
| MetaQA (yuyuz/MetaQA, vanilla test splits and `kb.txt`) | CC BY 3.0 | yes, attribution | registered as `metaqa`; KB verbalised per entity, triples kept |
| Text2KGBench | Apache-2.0 (`cenguix/Text2KGBench`) | yes | LettrIA refinement: data "upon request", terms unknown |
| `GEM/web_nlg` (HF) | CC BY-NC 4.0 | **no** | non-commercial |
| REBEL dataset | CC BY-NC-SA 4.0 | **no** | non-commercial, share-alike |
| Re-DocRED, DocRED | see HF cards | check | 4 of the 11 HF datasets we looked at declare no licence field |
| GraphRAG-Bench (arXiv 2506.05690, ICLR 2026) | MIT | yes | ships `evidence_relations` |
| GraphRAG-Bench (arXiv 2506.02404) | academic-only, no redistribution | **no** | unrelated benchmark with the same name |
| BrowseComp-Plus (`Tevatron/browsecomp-plus`, `-corpus`) | MIT | yes | registered as `browsecomp_plus`; 4.5 GB, fetches only when named; query shards may need a HF token |
| WildGraphBench | Apache-2.0 | yes | |
| InfoDeepSeek | CC BY-NC | **no** | also live-web, non-reproducible |
| `Zly0523/linear-rag`, `102202132zbz/rag_test` mirrors | none declared / apache-2.0 declared | not authoritative | a mirror cannot relicense CC BY-SA content; not used |

## Models

| component | licence | commercial reuse | notes |
|---|---|---|---|
| OpenAI `text-embedding-3-*`, `gpt-5.6-*` | OpenAI terms of use | yes, under the terms | outputs usable; API keys via environment only |
| Meta Muse Spark contributor tier | Meta API terms; traffic used for training | yes with care | never route private corpora through it |
| `google/gemma-4-31B-it` | Apache-2.0 | yes | Gemma 4 changed to Apache-2.0; earlier Gemma versions are under the Gemma ToU |
| EmbeddingGemma (300M) | Gemma Terms of Use, HF-gated | yes, under the ToU | not Apache |
| `sentence-transformers/all-MiniLM-L6-v2` | Apache-2.0 | yes | test and smoke embedder |
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | Apache-2.0 | yes | test reranker |
| `BAAI/bge-small-en-v1.5`, BGE-M3 | MIT | yes | |
| NV-Embed-v2 | CC BY-NC 4.0 | **no** | the literature's generation-2 reference retriever; fine here, not elsewhere |
| `jinaai/jina-embeddings-v3`, v5 | CC BY-NC 4.0 | **no** | |
| `jinaai/jina-embeddings-v4` | Qwen Research License (card corrects an earlier CC BY-NC tag) | **no** | derived from Qwen-2.5-VL-3B |
| Qwen3-Embedding 0.6B / 4B / 8B, Qwen3-Reranker | Apache-2.0 | yes | the local default tier of the sweep |
| `nvidia/Nemotron-3-Embed-1B` | commercial-friendly per model card | yes, under its terms | historical model comparison in [research snapshots](notes/research-snapshots.md) |
| `BAAI/bge-reranker-v2-m3` | Apache-2.0 | yes | the fixed reranker |
| Snowflake Arctic-Embed 2.0, Nomic Embed v2, granite-embedding, DenseOn, pplx-embed | Apache-2.0 / MIT per card | yes | historical model comparison in [research snapshots](notes/research-snapshots.md) |
| Claude via `claude -p` | Anthropic terms | yes, under the terms | CLI adapter, stateless invocation required |

## Code and infrastructure

| component | licence | commercial reuse | notes |
|---|---|---|---|
| [ty](https://github.com/astral-sh/ty/blob/main/LICENSE) | MIT | yes | development-only Python type checker |
| [Rich](https://github.com/Textualize/rich/blob/main/LICENSE) | MIT | yes | terminal tables, wrapping and capability-aware colors |
| [pytest-cov](https://github.com/pytest-dev/pytest-cov/blob/master/LICENSE) | MIT | yes | development-only branch coverage reporting |
| sqlite-vec | MIT / Apache-2.0 | yes | pre-v1 |
| Oxigraph, `pyoxigraph` | MIT / Apache-2.0 | yes | |
| LadybugDB (`lbug`, `ladybug`) | MIT | yes | Kùzu successor |
| Neo4j Community | GPLv3 | yes as a separate process; not linkable into proprietary code | RBAC/PBAC are Enterprise-only |
| Neo4j Graph Data Science (OpenGDS) | GPLv3; distributed plugin bundles closed code | check the bundled licence | |
| `neo4j` Python driver | Apache-2.0 AND Python-2.0 | yes | |
| `neo4j-graphrag` | Apache-2.0 | yes | |
| polars, pyarrow, PyO3, pyo3-arrow, maturin, arrow-rs | MIT / Apache-2.0 | yes | |
| pydantic, pydantic-settings | MIT | yes | boundary records (documents, questions, triples) and settings |
| sentence-transformers, fastembed | Apache-2.0 | yes | |
| BenchmarkQED | check repo | check | judge protocol we adopt; cite the source code |
| DIGIMON (JayLZhou/GraphRAG) | **no licence file** | **no** (read only) | operator taxonomy read for ideas only |
| KG-Gen | MIT in `pyproject.toml`, no LICENSE file | ambiguous | |
| HippoRAG code | MIT | yes | |
| LightRAG, Microsoft GraphRAG, Cognee, Graphiti, ATOM/iText2KG | MIT / MIT / Apache-2.0 / Apache-2.0 / Apache-2.0 | yes | |
| rudof (`pyrudof`) | MIT / Apache-2.0 | yes | |
| marimo, paper-qa | Apache-2.0 | yes | |

## How results record this

A results table that used a non-commercial component carries a footnote naming it. The run store
does not track licences; the component identity it records (model id, corpus hash, embedding spec)
is enough to look the row up here.
